from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from routes.utils_dtw import normalize_test_name
from storage_paths import DTW_RUNS_DIR, TEST_HISTORY_PATH


def _parse_created_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_history_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _completed_indicator(description: str = "Recording captured successfully.") -> Dict[str, str]:
    return {
        "color": "success",
        "label": "Completed",
        "description": description,
    }


@dataclass
class SessionMeta:
    test_name: str
    folder_name: str
    session_id: str
    patient_id: str | None
    created_at: datetime | None
    meta: Dict[str, Any]


class DtwMigrationService:
    def migrate_historical_data(
        self,
        *,
        dtw_base: Path = DTW_RUNS_DIR,
        test_history_path: Path = TEST_HISTORY_PATH,
        max_match_seconds: int = 5,
        write_changes: bool = True,
    ) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "renamed_folders": 0,
            "backfilled_entries": 0,
            "updated_existing_entries": 0,
            "skipped_ambiguous_entries": 0,
            "skipped_unmatched_entries": 0,
            "errors": [],
        }

        sessions_by_test, renames = self._normalize_session_folders(dtw_base, write_changes)
        report["renamed_folders"] = renames

        if not test_history_path.exists():
            return report

        history = json.loads(test_history_path.read_text())
        changed = False

        for patient_id, entries in history.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                status = self._backfill_entry(
                    patient_id,
                    entry,
                    sessions_by_test,
                    max_match_seconds=max_match_seconds,
                )
                if status == "backfilled":
                    report["backfilled_entries"] += 1
                    changed = True
                elif status == "updated":
                    report["updated_existing_entries"] += 1
                    changed = True
                elif status == "ambiguous":
                    report["skipped_ambiguous_entries"] += 1
                elif status == "unmatched":
                    report["skipped_unmatched_entries"] += 1

        if changed and write_changes:
            test_history_path.write_text(json.dumps(history, indent=2))

        return report

    def _normalize_session_folders(self, dtw_base: Path, write_changes: bool) -> Tuple[Dict[str, List[SessionMeta]], int]:
        sessions_by_test: Dict[str, List[SessionMeta]] = {}
        rename_count = 0

        if not dtw_base.exists():
            return sessions_by_test, rename_count

        for test_dir in dtw_base.iterdir():
            if not test_dir.is_dir():
                continue
            canonical_test = normalize_test_name(test_dir.name)
            sessions_by_test.setdefault(canonical_test, [])

            for folder in list(test_dir.iterdir()):
                if not folder.is_dir():
                    continue
                meta_path = folder / "meta.json"
                if not meta_path.is_file():
                    continue
                try:
                    meta = json.loads(meta_path.read_text())
                except Exception:
                    continue

                session_id = str(meta.get("session_id") or folder.name)
                target_folder = test_dir / session_id
                active_folder = folder
                if folder.name != session_id and write_changes and not target_folder.exists():
                    folder.rename(target_folder)
                    active_folder = target_folder
                    rename_count += 1
                elif folder.name != session_id and target_folder.exists():
                    active_folder = target_folder

                sessions_by_test[canonical_test].append(
                    SessionMeta(
                        test_name=canonical_test,
                        folder_name=active_folder.name,
                        session_id=session_id,
                        patient_id=(meta.get("patientId") or meta.get("patient_id")),
                        created_at=_parse_created_utc(meta.get("created_utc")),
                        meta=meta,
                    )
                )

        return sessions_by_test, rename_count

    def _backfill_entry(
        self,
        patient_id: str,
        entry: Dict[str, Any],
        sessions_by_test: Dict[str, List[SessionMeta]],
        *,
        max_match_seconds: int,
    ) -> str | None:
        test_name = normalize_test_name(entry.get("test_name"))
        if not test_name:
            return None

        candidates = [
            session for session in sessions_by_test.get(test_name, [])
            if str(session.patient_id or "").strip().lower() == patient_id.strip().lower()
        ]
        if not candidates:
            return "unmatched"

        matched_session: SessionMeta | None = None
        current_session_id = str((entry.get("dtw") or {}).get("session_id") or entry.get("test_id") or "").strip()
        if current_session_id:
            direct_matches = [
                session for session in candidates
                if session.session_id == current_session_id or session.folder_name == current_session_id
            ]
            if len(direct_matches) == 1:
                matched_session = direct_matches[0]
            elif len(direct_matches) > 1:
                return "ambiguous"

        if matched_session is None:
            entry_time = _parse_history_date(entry.get("date"))
            if entry_time is None:
                return "unmatched"

            ranked: List[Tuple[float, SessionMeta]] = []
            for session in candidates:
                if session.created_at is None:
                    continue
                delta = abs((session.created_at - entry_time).total_seconds())
                if delta <= max_match_seconds:
                    ranked.append((delta, session))
            ranked.sort(key=lambda item: item[0])
            if not ranked:
                return "unmatched"
            if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
                return "ambiguous"
            matched_session = ranked[0][1]

        had_existing = bool((entry.get("dtw") or {}).get("session_id") or entry.get("test_id"))
        updated = self._merge_entry_with_session(entry, matched_session)
        if updated:
            return "updated" if had_existing else "backfilled"
        return None

    def _merge_entry_with_session(self, entry: Dict[str, Any], session: SessionMeta) -> bool:
        meta = session.meta
        changed = False

        artifacts = {
            "dir": str(DTW_RUNS_DIR / session.test_name / session.session_id),
            "npz": str(DTW_RUNS_DIR / session.test_name / session.session_id / "dtw_artifacts.npz"),
            "json": str(DTW_RUNS_DIR / session.test_name / session.session_id / "meta.json"),
            "test_name": session.test_name,
            "session_id": session.session_id,
            "created_utc": meta.get("created_utc"),
        }

        desired_dtw = {
            "session_id": session.session_id,
            "distance": meta.get("pos_dtw", meta.get("distance")),
            "avg_step_cost": meta.get("avg_step_pos", meta.get("avg_step_cost")),
            "similarity": meta.get("similarity_overall", meta.get("similarity")),
            "artifacts": artifacts,
        }

        if entry.get("test_id") != session.session_id:
            entry["test_id"] = session.session_id
            changed = True
        if entry.get("status") != "completed":
            entry["status"] = "completed"
            changed = True
        if entry.get("summary_available") is not True:
            entry["summary_available"] = True
            changed = True

        desired_fps = int(meta["fps"]) if meta.get("fps") is not None else None
        if desired_fps is not None and entry.get("fps") != desired_fps:
            entry["fps"] = desired_fps
            changed = True
        if meta.get("model") and entry.get("model") != meta.get("model"):
            entry["model"] = meta.get("model")
            changed = True

        existing_dtw = entry.get("dtw") or {}
        merged_dtw = {**existing_dtw, **desired_dtw}
        if entry.get("dtw") != merged_dtw:
            entry["dtw"] = merged_dtw
            changed = True

        desired_indicator = entry.get("indicator") or _completed_indicator()
        if entry.get("indicator") != desired_indicator:
            entry["indicator"] = desired_indicator
            changed = True

        return changed


dtw_migration_service = DtwMigrationService()
