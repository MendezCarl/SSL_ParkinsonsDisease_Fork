from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import logging

import numpy as np
from fastapi import HTTPException

from dtw_models import points_for_model
from routes.utils_dtw import ALLOWED_TESTS, EndOnlyDTW, generate_session_id, normalize_test_name
from services import patient_service
from services.test_history_service import get_patient_tests as load_patient_tests, persist_session_analysis
from storage_paths import DTW_RUNS_DIR, LABELLED_TRAINING_DATA_DIR

logger = logging.getLogger(__name__)


DTW_BASE = DTW_RUNS_DIR
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _normalize_patient_id(patient_id: str | None) -> str:
    return (patient_id or "").strip().lower()


def _meta_patient_id(meta: Dict[str, Any]) -> str:
    return _normalize_patient_id(meta.get("patientId") or meta.get("patient_id"))


def _apply_reduce(arr: np.ndarray, how: str) -> np.ndarray:
    how = (how or "mean").lower()
    if how == "mean":
        return arr.mean(axis=1)
    if how == "median":
        return np.median(arr, axis=1)
    if how == "sum":
        return arr.sum(axis=1)
    if how == "min":
        return arr.min(axis=1)
    if how == "max":
        return arr.max(axis=1)
    if how == "pca1":
        centered = arr - arr.mean(axis=0, keepdims=True)
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        return centered @ vh[0]
    raise HTTPException(400, f"Unsupported reduce='{how}' (use mean|median|sum|min|max|pca1)")


def _parse_landmarks_param(landmarks: str | None, model: str, points: int) -> list[int]:
    if landmarks is None or str(landmarks).lower() == "all":
        return list(range(points))

    raw = [s.strip() for s in str(landmarks).split(",") if s.strip() != ""]
    try:
        req = [int(s) for s in raw]
    except ValueError as exc:
        raise HTTPException(400, f"Invalid landmarks list '{landmarks}'. Use 'all' or CSV of integers.") from exc

    for lm in req:
        if not (0 <= lm < points):
            raise HTTPException(400, f"landmark {lm} out of range 0..{points-1} for model {model}")
    return req


def _infer_points_and_kpp(dimensions: int, model: str) -> Tuple[int, int]:
    points = points_for_model(model)
    if points is None:
        raise HTTPException(500, f"Unknown model '{model}' in meta.json")
    if dimensions % points != 0:
        raise HTTPException(500, f"Template dimension {dimensions} not divisible by {model} points {points}")
    return points, dimensions // points


def _downsample_xy(x: np.ndarray, y: np.ndarray, max_points: int) -> Tuple[List[int], List[float]]:
    total = int(len(x))
    if total <= max_points:
        return x.astype(int).tolist(), y.astype(float).tolist()
    step = max(1, total // max_points)
    return x[::step].astype(int).tolist(), y[::step].astype(float).tolist()


def _safe_path_join(base_dir: Path, *parts: str) -> Path:
    base_resolved = base_dir.resolve(strict=False)
    candidate = base_dir.joinpath(*parts).resolve(strict=False)
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise HTTPException(400, "Invalid storage path") from exc
    return candidate


class DtwService:
    def normalize_test_name(self, value: str | None) -> str:
        return normalize_test_name(value)

    def new_session_id(self) -> str:
        return generate_session_id()

    def create_live_session(self, test_name: str, model: str, session_id: str | None = None) -> EndOnlyDTW:
        return EndOnlyDTW(test_name, model, session_id)

    def health(self) -> Dict[str, Any]:
        return {"ok": True, "base": str(DTW_BASE), "exists": DTW_BASE.exists()}

    def diag(self) -> Dict[str, Any]:
        return {
            "base": str(DTW_BASE),
            "exists": DTW_BASE.exists(),
            "tests": sorted([d.name for d in DTW_BASE.iterdir() if d.is_dir()]) if DTW_BASE.exists() else [],
        }

    def list_tests(self) -> List[str]:
        if not DTW_BASE.exists():
            return []
        return sorted([d.name for d in DTW_BASE.iterdir() if d.is_dir()])

    def lookup_session(self, session_id: str, patient_id: str | None = None) -> Dict[str, str]:
        if not DTW_BASE.exists():
            raise HTTPException(404, "DTW base not found")

        for test_dir in DTW_BASE.iterdir():
            if not test_dir.is_dir():
                continue
            try:
                session_dir, meta = self._resolve_session_dir_and_meta(test_dir.name, session_id)
            except HTTPException:
                continue

            canonical_session_id = self._canonical_session_id(session_dir, meta)
            if patient_id and not self._matches_patient(meta, patient_id, test_dir.name, session_dir.name):
                continue
            return {"testName": test_dir.name, "sessionId": canonical_session_id}

        raise HTTPException(404, {"error": str(DTW_BASE)})

    def list_sessions(self, test_name: str, patient_id: str | None = None) -> List[Dict[str, Any]]:
        root = self._test_dir(test_name)
        out: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for session_dir in sorted(root.iterdir()):
            if not session_dir.is_dir():
                continue
            try:
                meta = self._read_meta(session_dir / "meta.json")
            except HTTPException:
                continue

            if patient_id and not self._matches_patient(meta, patient_id, test_name, session_dir.name):
                continue

            canonical_session_id = self._canonical_session_id(session_dir, meta)
            if canonical_session_id in seen:
                continue
            seen.add(canonical_session_id)

            out.append(
                {
                    "session_id": canonical_session_id,
                    "created_utc": meta.get("created_utc"),
                    "model": meta.get("model"),
                    "live_len": meta.get("live_len"),
                    "ref_len": meta.get("ref_len"),
                    "distance_pos": meta.get("pos_dtw", meta.get("distance")),
                    "similarity_overall": meta.get("similarity_overall", meta.get("similarity")),
                    "similarity_pos": meta.get("similarity_pos"),
                    "similarity_amp": meta.get("similarity_amp"),
                    "similarity_spd": meta.get("similarity_spd"),
                }
            )

        return sorted(out, key=lambda item: item.get("created_utc") or "", reverse=True)

    def get_series(self, test_name: str, session_id: str, max_points: int) -> Dict[str, Any]:
        _, npz, meta = self._load_session_artifacts(test_name, session_id)

        pos_local = npz.get("pos_local_costs")
        pos_align = npz.get("pos_aligned_ref_by_live")
        amp_local = npz.get("amp_local_costs")
        amp_align = npz.get("amp_aligned_ref_by_live")
        spd_local = npz.get("spd_local_costs")
        spd_align = npz.get("spd_aligned_ref_by_live")

        if pos_local is None or pos_align is None:
            raise HTTPException(500, "Corrupt artifacts: missing position arrays")
        if amp_local is None or amp_align is None:
            raise HTTPException(500, "Corrupt artifacts: missing amplitude arrays")
        if spd_local is None or spd_align is None:
            raise HTTPException(500, "Corrupt artifacts: missing speed arrays")

        def _downsample(arr: np.ndarray, limit: int) -> Tuple[List[int], List[float]]:
            total = int(arr.shape[0])
            if total <= limit:
                return list(range(total)), arr.astype(float).tolist()
            step = max(1, total // limit)
            return list(range(0, total, step)), arr[::step].astype(float).tolist()

        def _series_bundle(local: np.ndarray, align: np.ndarray) -> Dict[str, Any]:
            x_local, y_local = _downsample(local, max_points)
            cumulative = (np.cumsum(local, dtype=np.float64) / (float(local.sum()) + 1e-9)).astype(float)
            return {
                "local_cost_path": {"x": x_local, "y": y_local},
                "cumulative_progress": {
                    "x": list(range(len(cumulative))),
                    "y": cumulative.tolist(),
                },
                "alignment_map": {
                    "x": list(range(len(align))),
                    "y": align.astype(int).tolist(),
                },
            }

        canonical_test_name = self.normalize_test_name(test_name)
        canonical_session_id = str(meta.get("session_id") or session_id)
        response = {
            "ok": True,
            "testName": canonical_test_name,
            "sessionId": canonical_session_id,
            "distance_pos": meta.get("pos_dtw", meta.get("distance")),
            "distance_amp": meta.get("amp_dtw"),
            "distance_spd": meta.get("spd_dtw"),
            "avg_step_pos": meta.get("avg_step_pos", meta.get("avg_step_cost")),
            "similarity_overall": meta.get("similarity_overall", meta.get("similarity")),
            "similarity_pos": meta.get("similarity_pos"),
            "similarity_amp": meta.get("similarity_amp"),
            "similarity_spd": meta.get("similarity_spd"),
            "series": {
                "position": _series_bundle(pos_local, pos_align),
                "amplitude": _series_bundle(amp_local, amp_align),
                "speed": _series_bundle(spd_local, spd_align),
            },
        }
        persist_session_analysis(
            canonical_session_id,
            dtw_metrics={
                "session_id": canonical_session_id,
                "distance_pos": response.get("distance_pos"),
                "distance_amp": response.get("distance_amp"),
                "distance_spd": response.get("distance_spd"),
                "avg_step_pos": response.get("avg_step_pos"),
                "avg_step_cost": response.get("avg_step_pos"),
                "similarity_overall": response.get("similarity_overall"),
                "similarity_pos": response.get("similarity_pos"),
                "similarity_amp": response.get("similarity_amp"),
                "similarity_spd": response.get("similarity_spd"),
                "distance": response.get("distance_pos"),
                "similarity": response.get("similarity_overall"),
            },
        )
        return response

    def download_paths(self, test_name: str, session_id: str) -> Dict[str, str]:
        session_dir, _ = self._resolve_session_dir_and_meta(test_name, session_id)
        return {
            "npz": str(session_dir / "dtw_artifacts.npz"),
            "meta": str(session_dir / "meta.json"),
        }

    def get_channel_series(
        self,
        test_name: str,
        session_id: str,
        landmark: int,
        axis: str,
        max_points: int,
    ) -> Dict[str, Any]:
        _, npz, meta = self._load_session_artifacts(test_name, session_id)
        x_live = npz["X_live"]
        y_ref = npz["Y_ref"]
        path = npz["pos_path"]

        model = (meta.get("model") or "pose").lower()
        total_live, dimensions = int(x_live.shape[0]), int(x_live.shape[1])
        total_ref = int(y_ref.shape[0])
        points, dims_per_point = _infer_points_and_kpp(dimensions, model)

        if not (0 <= landmark < points):
            raise HTTPException(400, f"landmark index {landmark} out of range 0..{points-1}")

        axis_index = {"x": 0, "y": 1, "z": 2}.get(axis, 0)
        if dims_per_point <= axis_index:
            raise HTTPException(400, f"axis '{axis}' not available (dims-per-point={dims_per_point})")

        d_index = landmark * dims_per_point + axis_index
        live_y = x_live[:, d_index]
        ref_y = y_ref[:, d_index]
        live_x = np.arange(total_live, dtype=np.int32)
        ref_x = np.arange(total_ref, dtype=np.int32)

        i_idx = path[:, 0].astype(np.int32)
        j_idx = path[:, 1].astype(np.int32)
        k_idx = np.arange(len(path), dtype=np.int32)

        warped_live = live_y[i_idx]
        warped_ref = ref_y[j_idx]

        live_x_ds, live_y_ds = _downsample_xy(live_x, live_y, max_points)
        ref_x_ds, ref_y_ds = _downsample_xy(ref_x, ref_y, max_points)

        if len(k_idx) > max_points:
            step = max(1, len(k_idx) // max_points)
            k_idx_ds = k_idx[::step]
            i_idx_ds = i_idx[::step]
            j_idx_ds = j_idx[::step]
            warped_live_ds = warped_live[::step]
            warped_ref_ds = warped_ref[::step]
        else:
            k_idx_ds = k_idx
            i_idx_ds = i_idx
            j_idx_ds = j_idx
            warped_live_ds = warped_live
            warped_ref_ds = warped_ref

        return {
            "ok": True,
            "model": model,
            "D": dimensions,
            "points": points,
            "dims_per_point": dims_per_point,
            "channel": {"landmark": landmark, "axis": axis, "d_index": int(d_index)},
            "live": {"x": [int(v) for v in live_x_ds], "y": [float(v) for v in live_y_ds]},
            "ref": {"x": [int(v) for v in ref_x_ds], "y": [float(v) for v in ref_y_ds]},
            "warped": {
                "k": [int(v) for v in k_idx_ds],
                "live": [float(v) for v in warped_live_ds],
                "ref": [float(v) for v in warped_ref_ds],
            },
            "path": {
                "i": [int(v) for v in i_idx_ds],
                "j": [int(v) for v in j_idx_ds],
            },
        }

    def get_axis_aggregate(
        self,
        test_name: str,
        session_id: str,
        axis: str,
        landmarks: str | None,
        reduce: str,
        max_points: int,
    ) -> Dict[str, Any]:
        _, npz, meta = self._load_session_artifacts(test_name, session_id)
        x_live = npz["X_live"]
        y_ref = npz["Y_ref"]
        path = npz["pos_path"]

        model = (meta.get("model") or "pose").lower()
        total_live, dimensions = int(x_live.shape[0]), int(x_live.shape[1])
        total_ref = int(y_ref.shape[0])
        points, dims_per_point = _infer_points_and_kpp(dimensions, model)

        axis_index = {"x": 0, "y": 1, "z": 2}.get(axis, 0)
        if dims_per_point <= axis_index:
            raise HTTPException(400, f"axis '{axis}' not available (dims-per-point={dims_per_point})")

        landmark_positions = _parse_landmarks_param(landmarks, model, points)
        if not landmark_positions:
            raise HTTPException(400, "No valid landmarks selected for aggregation")

        d_indices = np.asarray([lm * dims_per_point + axis_index for lm in landmark_positions], dtype=np.int32)
        live_matrix = x_live[:, d_indices]
        ref_matrix = y_ref[:, d_indices]
        live_series = _apply_reduce(live_matrix, reduce).astype(np.float32)
        ref_series = _apply_reduce(ref_matrix, reduce).astype(np.float32)

        live_x = np.arange(total_live, dtype=np.int32)
        ref_x = np.arange(total_ref, dtype=np.int32)

        i_idx = path[:, 0].astype(np.int32)
        j_idx = path[:, 1].astype(np.int32)
        k_idx = np.arange(len(path), dtype=np.int32)
        warped_live = live_series[i_idx]
        warped_ref = ref_series[j_idx]

        live_x_ds, live_y_ds = _downsample_xy(live_x, live_series, max_points)
        ref_x_ds, ref_y_ds = _downsample_xy(ref_x, ref_series, max_points)

        if len(k_idx) > max_points:
            step = max(1, len(k_idx) // max_points)
            k_idx_ds = k_idx[::step]
            i_idx_ds = i_idx[::step]
            j_idx_ds = j_idx[::step]
            warped_live_ds = warped_live[::step]
            warped_ref_ds = warped_ref[::step]
        else:
            k_idx_ds = k_idx
            i_idx_ds = i_idx
            j_idx_ds = j_idx
            warped_live_ds = warped_live
            warped_ref_ds = warped_ref

        return {
            "ok": True,
            "model": model,
            "D": dimensions,
            "points": points,
            "dims_per_point": dims_per_point,
            "axis": axis,
            "reduce": reduce,
            "landmarks_in": "all" if (landmarks is None or str(landmarks).lower() == "all") else landmarks,
            "resolved_positions": [int(v) for v in landmark_positions],
            "live": {"x": [int(v) for v in live_x_ds], "y": [float(v) for v in live_y_ds]},
            "ref": {"x": [int(v) for v in ref_x_ds], "y": [float(v) for v in ref_y_ds]},
            "warped": {
                "k": [int(v) for v in k_idx_ds],
                "live": [float(v) for v in warped_live_ds],
                "ref": [float(v) for v in warped_ref_ds],
            },
            "path": {
                "i": [int(v) for v in i_idx_ds],
                "j": [int(v) for v in j_idx_ds],
            },
        }

    def _write_doctor_label(
        self,
        session_dir: Path,
        meta: Dict[str, Any],
        confirmed_stage: int,
        notes: str | None,
    ) -> Dict[str, Any]:
        meta_path = _safe_path_join(session_dir, "meta.json")
        meta["doctor_confirmed_stage"] = confirmed_stage
        meta["doctor_label_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if notes:
            meta["doctor_notes"] = notes

        ml_stage = meta.get("ml_predicted_stage")
        was_corrected = ml_stage is not None and int(ml_stage) != confirmed_stage
        meta["label_source"] = "doctor_correction" if was_corrected else "doctor_confirmed"
        meta_path.write_text(json.dumps(meta, indent=2))
        return meta

    def _copy_to_labelled_training_data(
        self,
        session_dir: Path,
        canonical_test_name: str,
        confirmed_stage: int,
        canonical_session_id: str,
    ) -> Path:
        training_dir = _safe_path_join(
            LABELLED_TRAINING_DATA_DIR,
            canonical_test_name,
            f"stage_{confirmed_stage}",
            canonical_session_id,
        )
        training_dir.mkdir(parents=True, exist_ok=True)
        for src in session_dir.iterdir():
            dst = _safe_path_join(training_dir, src.name)
            if not dst.exists():
                shutil.copy2(src, dst)
        return training_dir

    async def _update_patient_severity(
        self, patient_id: str, confirmed_stage: int
    ) -> Tuple[bool, str | None]:
        try:
            from schema.patient_contracts import PatientUpdate

            result = await patient_service.update_patient(
                patient_id,
                PatientUpdate(severity=f"Stage {confirmed_stage}"),
            )
            return bool(result.get("success", False)), None
        except Exception:
            logger.exception("Failed to update patient %s severity after doctor label", patient_id)
            return False, "Failed to update patient severity"

    async def label_session(
        self,
        test_name: str,
        session_id: str,
        confirmed_stage: int,
        patient_id: str | None,
        notes: str | None,
    ) -> Dict[str, Any]:
        session_dir, meta = self._resolve_session_dir_and_meta(test_name, session_id)
        canonical_session_id = self._canonical_session_id(session_dir, meta)
        canonical_test_name = self._canonical_test_name(test_name)

        meta = self._write_doctor_label(session_dir, meta, confirmed_stage, notes)
        training_dir = self._copy_to_labelled_training_data(
            session_dir, canonical_test_name, confirmed_stage, canonical_session_id
        )

        patient_updated = False
        patient_update_error = None
        if patient_id:
            patient_updated, patient_update_error = await self._update_patient_severity(
                patient_id, confirmed_stage
            )

        return {
            "ok": True,
            "session_id": canonical_session_id,
            "confirmed_stage": confirmed_stage,
            "label_source": meta["label_source"],
            "training_copy": str(training_dir),
            "patient_updated": patient_updated,
            "patient_update_error": patient_update_error,
        }

    def _test_dir(self, test_name: str) -> Path:
        canonical_test_name = self._canonical_test_name(test_name)
        test_dir = _safe_path_join(DTW_BASE, canonical_test_name)
        if not test_dir.is_dir():
            raise HTTPException(404, f"Unknown test '{canonical_test_name}'")
        return test_dir

    def _canonical_test_name(self, test_name: str | None) -> str:
        canonical_test_name = normalize_test_name(test_name)
        if canonical_test_name not in ALLOWED_TESTS:
            raise HTTPException(404, "Unknown test")
        return canonical_test_name

    def _validated_session_id(self, session_id: str | None) -> str:
        candidate = (session_id or "").strip()
        if not _SESSION_ID_RE.fullmatch(candidate):
            raise HTTPException(400, "Invalid session id")
        return candidate

    def _canonical_session_id(self, session_dir: Path, meta: Dict[str, Any]) -> str:
        return str(meta.get("session_id") or session_dir.name)

    def _read_meta(self, meta_path: Path) -> Dict[str, Any]:
        if not meta_path.is_file():
            raise HTTPException(404, "Missing metadata")
        try:
            return json.loads(meta_path.read_text())
        except Exception as exc:
            raise HTTPException(500, "Failed to read metadata") from exc

    def _history_session_ids_for_patient(self, patient_id: str, test_name: str | None = None) -> set[str]:
        target_test_name = self.normalize_test_name(test_name) if test_name else ""
        session_ids: set[str] = set()

        for entry in load_patient_tests(patient_id):
            entry_test_name = self.normalize_test_name(entry.get("test_name"))
            if target_test_name and entry_test_name != target_test_name:
                continue
            dtw = entry.get("dtw") or {}
            for candidate in (dtw.get("session_id"), entry.get("test_id")):
                if isinstance(candidate, str) and candidate.strip():
                    session_ids.add(candidate.strip())
        return session_ids

    def _matches_patient(
        self,
        meta: Dict[str, Any],
        patient_id: str,
        test_name: str,
        folder_name: str,
    ) -> bool:
        normalized_target = _normalize_patient_id(patient_id)
        if not normalized_target:
            return True

        if _meta_patient_id(meta) == normalized_target:
            return True

        known_session_ids = self._history_session_ids_for_patient(patient_id, test_name)
        return folder_name in known_session_ids or str(meta.get("session_id") or "") in known_session_ids

    def _resolve_session_dir_and_meta(self, test_name: str, session_id: str) -> Tuple[Path, Dict[str, Any]]:
        root = self._test_dir(test_name)
        validated_session_id = self._validated_session_id(session_id)

        direct = _safe_path_join(root, validated_session_id)
        if direct.is_dir():
            return direct, self._read_meta(_safe_path_join(direct, "meta.json"))

        for session_dir in root.iterdir():
            if not session_dir.is_dir():
                continue
            try:
                meta = self._read_meta(_safe_path_join(session_dir, "meta.json"))
            except HTTPException:
                continue
            if self._canonical_session_id(session_dir, meta) == validated_session_id:
                return session_dir, meta

        raise HTTPException(404, "Session not found")

    def _load_session_artifacts(self, test_name: str, session_id: str) -> Tuple[Path, Any, Dict[str, Any]]:
        session_dir, meta = self._resolve_session_dir_and_meta(test_name, session_id)
        npz_path = _safe_path_join(session_dir, "dtw_artifacts.npz")
        if not npz_path.is_file():
            raise HTTPException(404, "Artifacts missing")

        try:
            npz = np.load(npz_path, allow_pickle=False)
        except Exception as exc:
            raise HTTPException(500, f"Failed to load artifacts: {exc}") from exc

        return session_dir, npz, meta


dtw_service = DtwService()


def get_dtw_service() -> DtwService:
    """FastAPI dependency provider; lets routes/tests override the singleton."""
    return dtw_service
