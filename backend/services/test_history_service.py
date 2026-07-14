from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from sqlalchemy.orm import Session

from patient_manager import SessionLocal
from repo.sql_models import Patient, TestResult


_KNOWN_TEST_FIELDS = {
    "test_id",
    "test_name",
    "date",
    "recording_file",
    "frame_count",
    "fps",
    "summary_available",
    "dtw",
    "analysis",
}


def _parse_history_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _serialize_history_datetime(value: datetime | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_session_id(entry: Dict[str, Any]) -> str | None:
    dtw = entry.get("dtw") or {}
    for candidate in (dtw.get("session_id"), entry.get("test_id")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _entry_extra(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in entry.items() if key not in _KNOWN_TEST_FIELDS}


def _apply_entry_to_row(row: TestResult, patient_id: str, entry: Dict[str, Any]) -> None:
    row.patient_id = patient_id or "unknown"
    row.test_name = str(entry.get("test_name") or "unknown")
    row.test_date = _parse_history_datetime(entry.get("date"))
    row.recording_file = entry.get("recording_file")
    row.frame_count = _coerce_int(entry.get("frame_count"))
    row.session_id = _extract_session_id(entry)
    row.fps = _coerce_int(entry.get("fps"))
    row.summary_available = entry.get("summary_available")
    row.dtw = entry.get("dtw") or None
    extra = _entry_extra(entry)
    if isinstance(entry.get("analysis"), dict):
        extra["analysis"] = entry["analysis"]
    row.extra = extra or None


def _matching_test_result(session: Session, patient_id: str, entry: Dict[str, Any]) -> TestResult | None:
    scoped_patient_id = patient_id or "unknown"
    session_id = _extract_session_id(entry)
    if session_id:
        return (
            session.query(TestResult)
            .filter(TestResult.patient_id == scoped_patient_id, TestResult.session_id == session_id)
            .order_by(TestResult.test_id.asc())
            .first()
        )

    query = session.query(TestResult).filter(
        TestResult.patient_id == scoped_patient_id,
        TestResult.test_name == str(entry.get("test_name") or "unknown"),
    )

    test_date = _parse_history_datetime(entry.get("date"))
    if test_date is None:
        query = query.filter(TestResult.test_date.is_(None))
    else:
        query = query.filter(TestResult.test_date == test_date)

    recording_file = entry.get("recording_file")
    if recording_file is None:
        query = query.filter(TestResult.recording_file.is_(None))
    else:
        query = query.filter(TestResult.recording_file == recording_file)

    return query.order_by(TestResult.test_id.asc()).first()


def _serialize_test_result(row: TestResult) -> Dict[str, Any]:
    payload = dict(row.extra or {})
    payload.update(
        {
            "test_id": row.session_id or str(row.test_id),
            "test_name": str(row.test_name or "unknown"),
            "date": _serialize_history_datetime(row.test_date),
            "recording_file": row.recording_file,
            "frame_count": row.frame_count,
            "fps": row.fps,
            "summary_available": row.summary_available,
            "dtw": row.dtw,
        }
    )
    return payload


def _analysis_container(extra: Dict[str, Any] | None) -> Dict[str, Any]:
    container = dict(extra or {})
    analysis = container.get("analysis")
    if not isinstance(analysis, dict):
        analysis = {}
    else:
        analysis = dict(analysis)
    container["analysis"] = analysis
    return container


def _prune_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _prune_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_prune_none(item) for item in value]
    return value


def _merge_dict(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _upsert_patient_test(session: Session, patient_id: str, entry: Dict[str, Any]) -> str:
    existing = _matching_test_result(session, patient_id, entry)
    if existing is None:
        existing = TestResult()
        session.add(existing)
        action = "inserted"
    else:
        action = "updated"

    _apply_entry_to_row(existing, patient_id, entry)
    session.flush()
    return action


def patient_exists(patient_id: str) -> bool:
    with SessionLocal() as session:
        return (
            session.query(Patient.patient_id)
            .filter(Patient.patient_id == patient_id)
            .first()
            is not None
        )


def persist_session_analysis(
    session_id: str,
    *,
    dtw_metrics: Dict[str, Any] | None = None,
    ml_prediction: Dict[str, Any] | None = None,
    anomaly_report: Dict[str, Any] | None = None,
) -> bool:
    scoped_session_id = (session_id or "").strip()
    if not scoped_session_id:
        return False

    changed = False
    with SessionLocal() as session:
        rows = (
            session.query(TestResult)
            .filter(TestResult.session_id == scoped_session_id)
            .all()
        )
        if not rows:
            return False

        for row in rows:
            extra = _analysis_container(row.extra)
            analysis = extra["analysis"]

            if dtw_metrics:
                pruned_metrics = _prune_none(dict(dtw_metrics))
                existing_metrics = analysis.get("dtw_metrics") if isinstance(analysis.get("dtw_metrics"), dict) else {}
                analysis["dtw_metrics"] = _merge_dict(existing_metrics, pruned_metrics)

                row.summary_available = True
                dtw_row = dict(row.dtw or {})
                dtw_row.update(
                    {
                        "session_id": scoped_session_id,
                        "distance": dtw_metrics.get("distance_pos", dtw_metrics.get("distance")),
                        "avg_step_cost": dtw_metrics.get("avg_step_pos", dtw_metrics.get("avg_step_cost")),
                        "similarity": dtw_metrics.get("similarity_overall", dtw_metrics.get("similarity")),
                    }
                )
                row.dtw = _prune_none(dtw_row) or None

            if ml_prediction:
                pruned_prediction = _prune_none(dict(ml_prediction))
                existing_prediction = analysis.get("ml_prediction") if isinstance(analysis.get("ml_prediction"), dict) else {}
                analysis["ml_prediction"] = _merge_dict(existing_prediction, pruned_prediction)

            if anomaly_report:
                pruned_report = _prune_none(dict(anomaly_report))
                existing_report = analysis.get("anomaly_report") if isinstance(analysis.get("anomaly_report"), dict) else {}
                analysis["anomaly_report"] = _merge_dict(existing_report, pruned_report)

            row.extra = extra
            changed = True

        if changed:
            session.commit()

    return changed


def build_completed_test_history_entry(
    *,
    test_name: str,
    session_id: str,
    recording_file: str,
    frame_count: int,
    fps: int | float | None,
    similarity: float | None,
    similarity_pos: float | None,
    similarity_amp: float | None,
    similarity_spd: float | None,
    distance: float | None,
    avg_step_cost: float | None,
    model: str | None,
    artifacts: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "test_id": session_id,
        "test_name": test_name,
        "date": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "recording_file": recording_file,
        "frame_count": frame_count,
        "fps": int(fps) if fps is not None else None,
        "summary_available": True,
        "model": model,
        "dtw": {
            "session_id": session_id,
            "distance": distance,
            "avg_step_cost": avg_step_cost,
            "similarity": similarity,
            "artifacts": artifacts or {},
        },
        "analysis": {
            "dtw_metrics": {
                "session_id": session_id,
                "distance_pos": distance,
                "distance": distance,
                "avg_step_pos": avg_step_cost,
                "avg_step_cost": avg_step_cost,
                "similarity_overall": similarity,
                "similarity": similarity,
                "similarity_pos": similarity_pos,
                "similarity_amp": similarity_amp,
                "similarity_spd": similarity_spd,
            }
        },
        "indicator": {
            "color": "success",
            "label": "Completed",
            "description": "Recording captured successfully.",
        },
    }


def append_patient_test(patient_id: str, entry: Dict[str, Any]) -> None:
    if not patient_exists(patient_id):
        raise ValueError(f"Patient '{patient_id}' not found")
    with SessionLocal() as session:
        _upsert_patient_test(session, patient_id or "unknown", entry)
        session.commit()


def get_patient_tests(patient_id: str) -> list[dict]:
    with SessionLocal() as session:
        rows = (
            session.query(TestResult)
            .filter(TestResult.patient_id == patient_id)
            .order_by(TestResult.test_id.asc())
            .all()
        )
        return [_serialize_test_result(row) for row in rows]


def migrate_test_history_file(test_history_path: Path) -> Dict[str, int]:
    report = {
        "patients": 0,
        "inserted": 0,
        "updated": 0,
        "skipped_invalid": 0,
        "skipped_missing_patient": 0,
    }
    if not test_history_path.exists():
        return report

    history = json.loads(test_history_path.read_text())
    if not isinstance(history, dict):
        raise ValueError("Expected top-level patient history mapping")

    with SessionLocal() as session:
        for patient_id, entries in history.items():
            report["patients"] += 1
            if not patient_exists(patient_id):
                report["skipped_missing_patient"] += len(entries) if isinstance(entries, list) else 1
                continue
            if not isinstance(entries, list):
                report["skipped_invalid"] += 1
                continue

            for entry in entries:
                if not isinstance(entry, dict):
                    report["skipped_invalid"] += 1
                    continue
                action = _upsert_patient_test(session, patient_id or "unknown", entry)
                report[action] += 1

        session.commit()

    return report


def build_uploaded_video_test_history_entry(
    *,
    test_name: str,
    session_id: str,
    recording_file: str,
) -> Dict[str, Any]:
    return {
        "test_id": session_id,
        "test_name": test_name,
        "date": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "recording_file": recording_file,
        "summary_available": True,
        "indicator": {
            "color": "success",
            "label": "Completed",
            "description": "Video uploaded successfully.",
        },
    }
