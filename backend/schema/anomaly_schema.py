from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

AnomalyJobStatusValue = Literal["pending", "processing", "done", "failed"]


class AnomalyChunk(BaseModel):
    start: str = Field(..., description="Chunk start timecode, e.g. '00:15'.")
    end: str = Field(..., description="Chunk end timecode, e.g. '00:19'.")
    confidence: float = Field(..., ge=0.0, le=1.0)


class AnomalyReport(BaseModel):
    chunks: List[AnomalyChunk] = Field(default_factory=list)
    model_version: Optional[str] = None
    generated_at: Optional[str] = None


class AnomalyJobCreateResponse(BaseModel):
    job_id: str
    status: AnomalyJobStatusValue


class AnomalyJobStatusResponse(BaseModel):
    job_id: str
    status: AnomalyJobStatusValue
    result: Optional[AnomalyReport] = None
    error: Optional[str] = None


class AnomalyJobListItem(BaseModel):
    job_id: str
    patient_id: str
    test_name: str
    session_id: str
    recording_file: str
    created_utc: str


class AnomalyJobCompleteRequest(BaseModel):
    result: Optional[AnomalyReport] = None
    error: Optional[str] = None
