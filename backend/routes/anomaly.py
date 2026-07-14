from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from auth import get_current_user, get_worker_auth
from schema.anomaly_schema import (
    AnomalyJobCompleteRequest,
    AnomalyJobCreateResponse,
    AnomalyJobListItem,
    AnomalyJobStatusResponse,
)
from services import anomaly_service
from services.test_history_service import patient_exists

router = APIRouter(prefix="/ml/anomaly", tags=["anomaly"], dependencies=[Depends(get_current_user)])
worker_router = APIRouter(prefix="/ml/anomaly", tags=["anomaly-worker"], dependencies=[Depends(get_worker_auth)])


@router.post(
    "/sessions/{test_name}/{session_id}",
    response_model=AnomalyJobCreateResponse,
    summary="Submit a DTW session for offline anomaly-detection analysis",
)
def submit_anomaly_job(test_name: str, session_id: str, patient_id: str) -> AnomalyJobCreateResponse:
    if not patient_exists(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        result = anomaly_service.create_job(patient_id, test_name, session_id)
    except anomaly_service.AnomalySessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AnomalyJobCreateResponse(**result)


@router.get(
    "/jobs/{job_id}",
    response_model=AnomalyJobStatusResponse,
    summary="Get anomaly-detection job status/result",
)
def get_anomaly_job(job_id: str) -> AnomalyJobStatusResponse:
    try:
        result = anomaly_service.get_job(job_id)
    except anomaly_service.AnomalyJobNotFound as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return AnomalyJobStatusResponse(job_id=result["job_id"], status=result["status"], result=result["result"], error=result["error"])


@worker_router.get(
    "/jobs",
    response_model=list[AnomalyJobListItem],
    summary="List pending anomaly-detection jobs (worker poll target)",
)
def list_pending_anomaly_jobs(status: str = "pending") -> list[AnomalyJobListItem]:
    if status != "pending":
        raise HTTPException(status_code=400, detail="Only status=pending is supported")
    return [AnomalyJobListItem(**job) for job in anomaly_service.list_pending_jobs()]


@worker_router.get(
    "/jobs/{job_id}/video",
    response_class=FileResponse,
    summary="Fetch the recording for a job (transitions it to processing)",
)
def get_anomaly_job_video(job_id: str) -> FileResponse:
    try:
        video_path = anomaly_service.get_job_video_path(job_id)
    except anomaly_service.AnomalyJobNotFound as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(video_path)


@worker_router.post(
    "/jobs/{job_id}/complete",
    summary="Report an anomaly-detection job result or error",
)
def complete_anomaly_job(job_id: str, body: AnomalyJobCompleteRequest) -> dict:
    try:
        return anomaly_service.complete_job(job_id, body.result, body.error)
    except anomaly_service.AnomalyJobNotFound as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
