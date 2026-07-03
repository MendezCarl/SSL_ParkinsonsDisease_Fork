# backend/routes/dtw_rest.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
import json
import shutil
from datetime import datetime, timezone
import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from storage_paths import DTW_RUNS_DIR, LABELLED_TRAINING_DATA_DIR

router = APIRouter(prefix="/dtw", tags=["dtw"])

DTW_BASE = DTW_RUNS_DIR
DTW_BASE.mkdir(parents=True, exist_ok=True)

print(f"[DTW REST] DTW_BASE = {DTW_BASE}")


class DtwHealthResponse(BaseModel):
    ok: bool
    base: str
    exists: bool


class DtwDiagResponse(BaseModel):
    base: str
    exists: bool
    tests: List[str]


class DtwSessionLookupResponse(BaseModel):
    testName: str
    sessionId: str


class DtwSessionMetaResponse(BaseModel):
    session_id: str
    created_utc: str | None = None
    model: str | None = None
    live_len: int | None = None
    ref_len: int | None = None
    distance_pos: float | None = None
    similarity_overall: float | None = None
    similarity_pos: float | None = None
    similarity_amp: float | None = None
    similarity_spd: float | None = None


class XYSeries(BaseModel):
    x: List[int]
    y: List[float]


class IntPathSeries(BaseModel):
    i: List[int]
    j: List[int]


class WarpedSeries(BaseModel):
    k: List[int]
    live: List[float]
    ref: List[float]


class DtwSeriesCurve(BaseModel):
    local_cost_path: XYSeries
    cumulative_progress: XYSeries
    alignment_map: XYSeries


class DtwSeriesResponse(BaseModel):
    ok: bool
    testName: str
    sessionId: str
    distance_pos: float | None = None
    distance_amp: float | None = None
    distance_spd: float | None = None
    avg_step_pos: float | None = None
    similarity_overall: float | None = None
    similarity_pos: float | None = None
    similarity_amp: float | None = None
    similarity_spd: float | None = None
    series: Dict[str, DtwSeriesCurve]


class DtwDownloadResponse(BaseModel):
    npz: str
    meta: str


class DtwChannelDescriptor(BaseModel):
    landmark: int
    axis: str
    d_index: int


class DtwChannelResponse(BaseModel):
    ok: bool
    model: str
    D: int
    points: int
    dims_per_point: int
    channel: DtwChannelDescriptor
    live: XYSeries
    ref: XYSeries
    warped: WarpedSeries
    path: IntPathSeries


class DtwAxisAggregateResponse(BaseModel):
    ok: bool
    model: str
    D: int
    points: int
    dims_per_point: int
    axis: str
    reduce: str
    landmarks_in: str
    resolved_positions: List[int]
    live: XYSeries
    ref: XYSeries
    warped: WarpedSeries
    path: IntPathSeries


class LabelSessionResponse(BaseModel):
    ok: bool
    session_id: str
    confirmed_stage: int
    label_source: str
    training_copy: str
    patient_updated: bool
    patient_update_error: str | None = None

def _test_dir(test_name: str) -> Path:
    p = DTW_BASE / test_name
    if not p.is_dir():
        raise HTTPException(404, f"Unknown test '{test_name}' at {p}")
    return p

def _session_dir(test_name: str, session_id: str) -> Path:
    p = _test_dir(test_name) / session_id
    if not p.is_dir():
        raise HTTPException(404, f"Session '{session_id}' not found under {p.parent}")
    return p

# --- add these helpers anywhere above the endpoint (e.g., near other helpers) ---
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
    raise HTTPException(400, f"Unsupported reduce='{how}' (use mean|median|sum|min|max)")

def _parse_landmarks_param(landmarks: str | None, model: str, points: int) -> list[int]:
    """
    Accepts:
      - None or "all": all landmarks (0..points-1)
      - CSV like "1,2,3" (0-based indices for pose 0..32; hands 0..20)
    Returns 0-based positions inside the flattened feature vector.
    """
    if landmarks is None or str(landmarks).lower() == "all":
        return list(range(points))

    raw = [s.strip() for s in str(landmarks).split(",") if s.strip() != ""]
    try:
        req = [int(s) for s in raw]
    except ValueError:
        raise HTTPException(400, f"Invalid landmarks list '{landmarks}'. Use 'all' or CSV of integers.")

    for lm in req:
        if not (0 <= lm < points):
            raise HTTPException(400, f"landmark {lm} out of range 0..{points-1} for model {model}")
    return req


@router.get("/health", response_model=DtwHealthResponse, summary="DTW service health")
def health() -> DtwHealthResponse:
    return {"ok": True, "base": str(DTW_BASE), "exists": DTW_BASE.exists()}

@router.get("/diag", response_model=DtwDiagResponse, summary="DTW storage diagnostics")
def diag() -> DtwDiagResponse:
    return {
        "base": str(DTW_BASE),
        "exists": DTW_BASE.exists(),
        "tests": sorted([d.name for d in DTW_BASE.iterdir() if d.is_dir()]) if DTW_BASE.exists() else []
    }

@router.get("/tests", response_model=List[str])
def list_tests() -> List[str]:
    if not DTW_BASE.exists():
        return []
    return sorted([d.name for d in DTW_BASE.iterdir() if d.is_dir()])

@router.get("/sessions/lookup/{session_id}", response_model=DtwSessionLookupResponse, summary="Resolve a DTW session id to its test")
def lookup_session(session_id: str) -> DtwSessionLookupResponse:
    if not DTW_BASE.exists():
        raise HTTPException(404, "DTW base not found")
    for t in DTW_BASE.iterdir():
        if not t.is_dir():
            continue
        if (t / session_id).is_dir():
            return {"testName": t.name, "sessionId": session_id}
    raise HTTPException(404, {"error": str(DTW_BASE)})

@router.get("/sessions/{test_name}", response_model=List[DtwSessionMetaResponse], summary="List saved DTW sessions for a test")
def list_sessions(test_name: str) -> List[DtwSessionMetaResponse]:
    root = _test_dir(test_name)
    out: List[Dict[str, Any]] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text())
            out.append({
                "session_id": d.name,
                "created_utc": meta.get("created_utc"),
                "model": meta.get("model"),
                "live_len": meta.get("live_len"),
                "ref_len": meta.get("ref_len"),
                # backward-compatible distance/similarity
                "distance_pos": meta.get("pos_dtw", meta.get("distance")),
                "similarity_overall": meta.get("similarity_overall", meta.get("similarity")),
                "similarity_pos": meta.get("similarity_pos"),
                "similarity_amp": meta.get("similarity_amp"),
                "similarity_spd": meta.get("similarity_spd"),
            })
        except Exception:
            continue
    # newest first by timestamp string
    return sorted(out, key=lambda x: x.get("created_utc") or "", reverse=True)

@router.get(
    "/sessions/{test_name}/{session_id}/series",
    response_model=DtwSeriesResponse,
    summary="Get DTW metrics and plotted series for a session",
)
def get_series(
    test_name: str,
    session_id: str,
    max_points: int = Query(200, ge=50, le=2000)
) -> Dict[str, Any]:
    folder = _session_dir(test_name, session_id)
    npz_path, meta_path = folder / "dtw_artifacts.npz", folder / "meta.json"
    if not npz_path.is_file() or not meta_path.is_file():
        raise HTTPException(404, "Artifacts missing")

    try:
        npz = np.load(npz_path, allow_pickle=False)
    except Exception as e:
        raise HTTPException(500, f"Failed to load artifacts: {e}")

    # --- load new arrays from NPZ ---
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

    try:
        meta = json.loads(meta_path.read_text())
    except Exception as e:
        raise HTTPException(500, f"Failed to read meta.json: {e}")

    def _downsample(arr: np.ndarray, kmax: int = 200) -> Tuple[List[int], List[float]]:
        n = int(arr.shape[0])
        if n <= kmax:
            return list(range(n)), arr.astype(float).tolist()
        step = max(1, n // kmax)
        return list(range(0, n, step)), arr[::step].astype(float).tolist()

    def _series_bundle(local: np.ndarray, align: np.ndarray) -> Dict[str, Any]:
        x_lc, y_lc = _downsample(local, max_points)
        # normalized cumulative progress along this path
        cum = (np.cumsum(local, dtype=np.float64) /
               (float(local.sum()) + 1e-9)).astype(float)
        return {
            "local_cost_path": {"x": x_lc, "y": y_lc},
            "cumulative_progress": {
                "x": list(range(len(cum))),
                "y": cum.tolist(),
            },
            "alignment_map": {
                "x": list(range(len(align))),
                "y": align.astype(int).tolist(),
            },
        }

    return {
        "ok": True,
        "testName": test_name,
        "sessionId": session_id,
        # meta: distances & similarities
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

@router.get(
    "/sessions/{test_name}/{session_id}/download",
    response_model=DtwDownloadResponse,
    summary="Get file paths for saved DTW artifacts",
)
def download_paths(test_name: str, session_id: str) -> DtwDownloadResponse:
    folder = _session_dir(test_name, session_id)
    return {
        "npz": str(folder / "dtw_artifacts.npz"),
        "meta": str(folder / "meta.json"),
    }

def _infer_points_and_kpp(D: int, model: str) -> Tuple[int, int]:
    """
    Infer (#points, dims-per-point) from feature dimension D and model.
    - pose: 33 points
    - hands: 21 points (full Mediapipe hand)
    """
    model = (model or "").lower()
    if model == "pose":
        points = 33
        if D % points != 0:
            raise HTTPException(500, f"Template dimension {D} not divisible by pose points {points}")
        return points, D // points

    if model == "hands":
        points = 21
        if D % points != 0:
            raise HTTPException(500, f"Template dimension {D} not divisible by hands points {points}")
        return points, D // points

    raise HTTPException(500, f"Unknown model '{model}' in meta.json")

def _downsample_xy(x: np.ndarray, y: np.ndarray, kmax: int) -> Tuple[List[int], List[float]]:
    n = int(len(x))
    if n <= kmax:
        return x.astype(int).tolist(), y.astype(float).tolist()
    step = max(1, n // kmax)
    return x[::step].astype(int).tolist(), y[::step].astype(float).tolist()

@router.get(
    "/sessions/{test_name}/{session_id}/channel",
    response_model=DtwChannelResponse,
    summary="Get DTW channel series for one landmark and axis",
)
def get_channel_series(
    test_name: str,
    session_id: str,
    landmark: int = Query(0, ge=0, description="0..20 for hands; 0..32 for pose"),
    axis: str = Query("x", regex="^(x|y|z)$"),
    max_points: int = Query(400, ge=50, le=3000),
) -> Dict[str, Any]:
    """
    Returns original live/ref series for a single channel (landmark+axis),
    along with the DTW path and the aligned (warped) pair series.
    """
    folder = _session_dir(test_name, session_id)
    npz_path, meta_path = folder / "dtw_artifacts.npz", folder / "meta.json"
    if not npz_path.is_file() or not meta_path.is_file():
        raise HTTPException(404, "Artifacts missing")

    try:
        npz = np.load(npz_path, allow_pickle=False)
        X_live = npz["X_live"]          # (T_live, D)
        Y_ref  = npz["Y_ref"]           # (T_ref, D)
        path   = npz["pos_path"]            # (L, 2) int32
    except Exception as e:
        raise HTTPException(500, f"Failed to load artifacts: {e}")

    try:
        meta = json.loads(meta_path.read_text())
        model = (meta.get("model") or "pose").lower()
    except Exception as e:
        raise HTTPException(500, f"Failed to read meta.json: {e}")

    T_live, D = int(X_live.shape[0]), int(X_live.shape[1])
    T_ref     = int(Y_ref.shape[0])
    points, kpp = _infer_points_and_kpp(D, model)

    if not (0 <= landmark < points):
        raise HTTPException(400, f"landmark index {landmark} out of range 0..{points-1}")

    axis_idx = {"x": 0, "y": 1, "z": 2}.get(axis, 0)
    if kpp <= axis_idx:
        # z requested but features are 2D, or bad axis
        raise HTTPException(400, f"axis '{axis}' not available (dims-per-point={kpp})")

    d_index = landmark * kpp + axis_idx

    # Original series (indices are frame numbers)
    live_y = X_live[:, d_index]
    ref_y  = Y_ref[:,  d_index]
    live_x = np.arange(T_live, dtype=np.int32)
    ref_x  = np.arange(T_ref,  dtype=np.int32)

    # Aligned (warped) pairs along the DTW path
    i_idx = path[:, 0].astype(np.int32)
    j_idx = path[:, 1].astype(np.int32)
    k_idx = np.arange(len(path), dtype=np.int32)

    warped_live = live_y[i_idx]
    warped_ref  = ref_y[j_idx]

    # Downsample for plotting
    live_x_ds, live_y_ds = _downsample_xy(live_x, live_y, max_points)
    ref_x_ds,  ref_y_ds  = _downsample_xy(ref_x,  ref_y,  max_points)

    if len(k_idx) > max_points:
        step = max(1, len(k_idx) // max_points)
        k_idx_ds = k_idx[::step]
        i_idx_ds = i_idx[::step]
        j_idx_ds = j_idx[::step]
        warped_live_ds = warped_live[::step]
        warped_ref_ds  = warped_ref[::step]
    else:
        k_idx_ds = k_idx
        i_idx_ds = i_idx
        j_idx_ds = j_idx
        warped_live_ds = warped_live
        warped_ref_ds  = warped_ref

    return {
        "ok": True,
        "model": model,
        "D": D,
        "points": points,
        "dims_per_point": kpp,
        "channel": {"landmark": landmark, "axis": axis, "d_index": int(d_index)},
        "live": {"x": [int(v) for v in live_x_ds], "y": [float(v) for v in live_y_ds]},
        "ref":  {"x": [int(v) for v in ref_x_ds],  "y": [float(v) for v in ref_y_ds]},
        "warped": {
            "k":  [int(v) for v in k_idx_ds],
            "live": [float(v) for v in warped_live_ds],
            "ref":  [float(v) for v in warped_ref_ds],
        },
        "path": {
            "i": [int(v) for v in i_idx_ds],
            "j": [int(v) for v in j_idx_ds],
        }
    }

   
# --- Aggregate one axis across many (or all) landmarks into a 1D series ---
@router.get(
    "/sessions/{test_name}/{session_id}/axis_agg",
    response_model=DtwAxisAggregateResponse,
    summary="Aggregate one axis across selected landmarks for a DTW session",
)
def get_axis_aggregate(
    test_name: str,
    session_id: str,
    axis: str = Query("x", regex="^(x|y|z)$"),
    landmarks: str | None = Query(
        None,
        description="Use 'all' or CSV (e.g., '0,1,2'). Hands: 0..20. Pose: 0..32."
    ),
    reduce: str = Query("mean", description="Aggregation over selected landmarks per frame: mean|median|sum|min|max"),
    max_points: int = Query(600, ge=50, le=5000),
) -> Dict[str, Any]:
    folder = _session_dir(test_name, session_id)
    npz_path, meta_path = folder / "dtw_artifacts.npz", folder / "meta.json"
    if not npz_path.is_file() or not meta_path.is_file():
        raise HTTPException(404, "Artifacts missing")

    try:
        npz = np.load(npz_path, allow_pickle=False)
        X_live = npz["X_live"]          # (T_live, D)
        Y_ref  = npz["Y_ref"]           # (T_ref, D)
        path   = npz["pos_path"]            # (L, 2) int32
    except Exception as e:
        raise HTTPException(500, f"Failed to load artifacts: {e}")

    try:
        meta = json.loads(meta_path.read_text())
        model = (meta.get("model") or "pose").lower()
    except Exception as e:
        raise HTTPException(500, f"Failed to read meta.json: {e}")

    T_live, D = int(X_live.shape[0]), int(X_live.shape[1])
    T_ref     = int(Y_ref.shape[0])
    points, kpp = _infer_points_and_kpp(D, model)

    axis_idx = {"x": 0, "y": 1, "z": 2}.get(axis, 0)
    if kpp <= axis_idx:
        raise HTTPException(400, f"axis '{axis}' not available (dims-per-point={kpp})")

    # Resolve landmarks (supports 'all' and CSV)
    lm_positions = _parse_landmarks_param(landmarks, model, points)
    if len(lm_positions) == 0:
        raise HTTPException(400, "No valid landmarks selected for aggregation")

    # Compute channel indices for chosen axis and aggregate per frame
    d_indices = np.asarray([lm * kpp + axis_idx for lm in lm_positions], dtype=np.int32)
    live_mat = X_live[:, d_indices]
    ref_mat  = Y_ref[:,  d_indices]
    live_series = _apply_reduce(live_mat, reduce).astype(np.float32)
    ref_series  = _apply_reduce(ref_mat,  reduce).astype(np.float32)

    # Original x-axes
    live_x = np.arange(T_live, dtype=np.int32)
    ref_x  = np.arange(T_ref,  dtype=np.int32)

    # Warped series along DTW path
    i_idx = path[:, 0].astype(np.int32)
    j_idx = path[:, 1].astype(np.int32)
    k_idx = np.arange(len(path), dtype=np.int32)
    warped_live = live_series[i_idx]
    warped_ref  = ref_series[j_idx]

    # Downsample for plotting
    live_x_ds, live_y_ds = _downsample_xy(live_x, live_series, max_points)
    ref_x_ds,  ref_y_ds  = _downsample_xy(ref_x,  ref_series,  max_points)

    if len(k_idx) > max_points:
        step = max(1, len(k_idx) // max_points)
        k_idx_ds = k_idx[::step]
        i_idx_ds = i_idx[::step]
        j_idx_ds = j_idx[::step]
        warped_live_ds = warped_live[::step]
        warped_ref_ds  = warped_ref[::step]
    else:
        k_idx_ds = k_idx
        i_idx_ds = i_idx
        j_idx_ds = j_idx
        warped_live_ds = warped_live
        warped_ref_ds  = warped_ref

    return {
        "ok": True,
        "model": model,
        "D": D,
        "points": points,
        "dims_per_point": kpp,
        "axis": axis,
        "reduce": reduce,
        "landmarks_in": "all" if (landmarks is None or str(landmarks).lower()=="all") else landmarks,
        "resolved_positions": [int(v) for v in lm_positions],
        "live": {"x": [int(v) for v in live_x_ds], "y": [float(v) for v in live_y_ds]},
        "ref":  {"x": [int(v) for v in ref_x_ds],  "y": [float(v) for v in ref_y_ds]},
        "warped": {
            "k":  [int(v) for v in k_idx_ds],
            "live": [float(v) for v in warped_live_ds],
            "ref":  [float(v) for v in warped_ref_ds],
        },
        "path": {
            "i": [int(v) for v in i_idx_ds],
            "j": [int(v) for v in j_idx_ds],
        }
    }

# ─────────────────────────── Doctor label endpoint ───────────────────────────

class LabelSessionRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "confirmed_stage": 3,
                "patient_id": "janes1720462800",
                "notes": "Clinician review confirms Stage 3 after observing reduced amplitude.",
            }
        }
    )
    confirmed_stage: int = Field(
        ...,
        ge=1,
        le=5,
        description="Doctor-confirmed UPDRS stage (1–5).",
    )
    patient_id: str | None = Field(
        None,
        description="If provided, updates the patient's severity field to this stage.",
    )
    notes: str | None = Field(
        None,
        max_length=1000,
        description="Optional free-text note from the reviewing clinician.",
    )

    @field_validator("confirmed_stage")
    @classmethod
    def stage_in_range(cls, v: int) -> int:
        if not (1 <= v <= 5):
            raise ValueError("confirmed_stage must be between 1 and 5")
        return v


@router.patch(
    "/sessions/{test_name}/{session_id}/label",
    response_model=LabelSessionResponse,
    summary="Doctor confirms or corrects the AI-predicted UPDRS stage",
)
async def label_session(
    test_name: str,
    session_id: str,
    body: LabelSessionRequest,
) -> LabelSessionResponse:
    folder = _session_dir(test_name, session_id)
    meta_path = folder / "meta.json"

    try:
        meta: dict = json.loads(meta_path.read_text())
    except Exception as e:
        raise HTTPException(500, f"Could not read meta.json: {e}")

    meta["doctor_confirmed_stage"] = body.confirmed_stage
    meta["doctor_label_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if body.notes:
        meta["doctor_notes"] = body.notes

    ml_stage = meta.get("ml_predicted_stage")
    was_corrected = ml_stage is not None and int(ml_stage) != body.confirmed_stage
    meta["label_source"] = "doctor_correction" if was_corrected else "doctor_confirmed"

    meta_path.write_text(json.dumps(meta, indent=2))

    # Archive for future training
    training_dir = LABELLED_TRAINING_DATA_DIR / test_name / f"stage_{body.confirmed_stage}" / session_id
    training_dir.mkdir(parents=True, exist_ok=True)
    for src in folder.iterdir():
        dst = training_dir / src.name
        if not dst.exists():
            shutil.copy2(src, dst)

    # Optionally update patient severity
    patient_updated = False
    if body.patient_id:
        try:
            from patient_manager import async_update_patient_info
            from routes.contracts import PatientUpdate
            severity_str = f"Stage {body.confirmed_stage}"
            result = await async_update_patient_info(
                body.patient_id,
                PatientUpdate(severity=severity_str),
            )
            patient_updated = result.get("success", False)
        except Exception as e:
            return {
                "ok": True,
                "session_id": session_id,
                "confirmed_stage": body.confirmed_stage,
                "label_source": meta["label_source"],
                "training_copy": str(training_dir),
                "patient_updated": False,
                "patient_update_error": str(e),
            }

    return {
        "ok": True,
        "session_id": session_id,
        "confirmed_stage": body.confirmed_stage,
        "label_source": meta["label_source"],
        "training_copy": str(training_dir),
        "patient_updated": patient_updated,
    }
