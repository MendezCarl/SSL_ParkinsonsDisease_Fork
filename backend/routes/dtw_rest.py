# backend/routes/dtw_rest.py
from __future__ import annotations
from typing import List, Dict, Any
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator

from auth import get_current_user
from services.dtw_service import DTW_BASE, DtwService, get_dtw_service

router = APIRouter(prefix="/dtw", tags=["dtw"], dependencies=[Depends(get_current_user)])
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

@router.get("/health", response_model=DtwHealthResponse, summary="DTW service health")
def health(svc: DtwService = Depends(get_dtw_service)) -> DtwHealthResponse:
    return svc.health()

@router.get("/diag", response_model=DtwDiagResponse, summary="DTW storage diagnostics")
def diag(svc: DtwService = Depends(get_dtw_service)) -> DtwDiagResponse:
    return svc.diag()

@router.get("/tests", response_model=List[str])
def list_tests(svc: DtwService = Depends(get_dtw_service)) -> List[str]:
    return svc.list_tests()

@router.get("/sessions/lookup/{session_id}", response_model=DtwSessionLookupResponse, summary="Resolve a DTW session id to its test")
def lookup_session(
    session_id: str,
    patient_id: str | None = Query(None, description="Optional patient scope for session lookup"),
    svc: DtwService = Depends(get_dtw_service),
) -> DtwSessionLookupResponse:
    return svc.lookup_session(session_id, patient_id)

@router.get("/sessions/{test_name}", response_model=List[DtwSessionMetaResponse], summary="List saved DTW sessions for a test")
def list_sessions(
    test_name: str,
    patient_id: str | None = Query(None, description="Optional patient scope for session listing"),
    svc: DtwService = Depends(get_dtw_service),
) -> List[DtwSessionMetaResponse]:
    return svc.list_sessions(test_name, patient_id)

@router.get(
    "/sessions/{test_name}/{session_id}/series",
    response_model=DtwSeriesResponse,
    summary="Get DTW metrics and plotted series for a session",
)
def get_series(
    test_name: str,
    session_id: str,
    max_points: int = Query(200, ge=50, le=2000),
    svc: DtwService = Depends(get_dtw_service),
) -> Dict[str, Any]:
    return svc.get_series(test_name, session_id, max_points)

@router.get(
    "/sessions/{test_name}/{session_id}/download",
    response_model=DtwDownloadResponse,
    summary="Get file paths for saved DTW artifacts",
)
def download_paths(
    test_name: str,
    session_id: str,
    svc: DtwService = Depends(get_dtw_service),
) -> DtwDownloadResponse:
    return svc.download_paths(test_name, session_id)

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
    svc: DtwService = Depends(get_dtw_service),
) -> Dict[str, Any]:
    return svc.get_channel_series(test_name, session_id, landmark, axis, max_points)


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
    svc: DtwService = Depends(get_dtw_service),
) -> Dict[str, Any]:
    return svc.get_axis_aggregate(test_name, session_id, axis, landmarks, reduce, max_points)

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
    svc: DtwService = Depends(get_dtw_service),
) -> LabelSessionResponse:
    return await svc.label_session(
        test_name,
        session_id,
        body.confirmed_stage,
        body.patient_id,
        body.notes,
    )
