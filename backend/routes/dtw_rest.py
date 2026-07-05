# backend/routes/dtw_rest.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from services.dtw_service import DTW_BASE, dtw_service

router = APIRouter(prefix="/dtw", tags=["dtw"])
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
    if how == "pca1":
        centered = arr - arr.mean(axis=0, keepdims=True)
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        return centered @ vh[0]
    raise HTTPException(400, f"Unsupported reduce='{how}' (use mean|median|sum|min|max|pca1)")

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
    return dtw_service.health()

@router.get("/diag", response_model=DtwDiagResponse, summary="DTW storage diagnostics")
def diag() -> DtwDiagResponse:
    return dtw_service.diag()

@router.get("/tests", response_model=List[str])
def list_tests() -> List[str]:
    return dtw_service.list_tests()

@router.get("/sessions/lookup/{session_id}", response_model=DtwSessionLookupResponse, summary="Resolve a DTW session id to its test")
def lookup_session(
    session_id: str,
    patient_id: str | None = Query(None, description="Optional patient scope for session lookup"),
) -> DtwSessionLookupResponse:
    return dtw_service.lookup_session(session_id, patient_id)

@router.get("/sessions/{test_name}", response_model=List[DtwSessionMetaResponse], summary="List saved DTW sessions for a test")
def list_sessions(
    test_name: str,
    patient_id: str | None = Query(None, description="Optional patient scope for session listing"),
) -> List[DtwSessionMetaResponse]:
    return dtw_service.list_sessions(test_name, patient_id)

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
    return dtw_service.get_series(test_name, session_id, max_points)

@router.get(
    "/sessions/{test_name}/{session_id}/download",
    response_model=DtwDownloadResponse,
    summary="Get file paths for saved DTW artifacts",
)
def download_paths(test_name: str, session_id: str) -> DtwDownloadResponse:
    return dtw_service.download_paths(test_name, session_id)

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
    axis: str = Query("x", pattern="^(x|y|z)$"),
    max_points: int = Query(400, ge=50, le=3000),
) -> Dict[str, Any]:
    return dtw_service.get_channel_series(test_name, session_id, landmark, axis, max_points)

   
# --- Aggregate one axis across many (or all) landmarks into a 1D series ---
@router.get(
    "/sessions/{test_name}/{session_id}/axis_agg",
    response_model=DtwAxisAggregateResponse,
    summary="Aggregate one axis across selected landmarks for a DTW session",
)
def get_axis_aggregate(
    test_name: str,
    session_id: str,
    axis: str = Query("x", pattern="^(x|y|z)$"),
    landmarks: str | None = Query(
        None,
        description="Use 'all' or CSV (e.g., '0,1,2'). Hands: 0..20. Pose: 0..32."
    ),
    reduce: str = Query("mean", description="Aggregation over selected landmarks per frame: mean|median|sum|min|max"),
    max_points: int = Query(600, ge=50, le=5000),
) -> Dict[str, Any]:
    return dtw_service.get_axis_aggregate(test_name, session_id, axis, landmarks, reduce, max_points)

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
    return await dtw_service.label_session(
        test_name,
        session_id,
        body.confirmed_stage,
        body.patient_id,
        body.notes,
    )
