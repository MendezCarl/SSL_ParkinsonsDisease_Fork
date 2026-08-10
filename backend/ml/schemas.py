from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AvailableModelsResponse(BaseModel):
    video_models: list[str]
    anomaly_models: list[str]
    default_video_model: str
    default_anomaly_model: str


class EmbeddingRequest(BaseModel):
    video_path: str
    video_model: str | None = None


class EmbeddingResponse(BaseModel):
    filename: str
    video_model: str
    embedding_dim: int | None = None
    feature_keys: list[str]


class AnomalyEmbeddingRequest(BaseModel):
    filename: str
    embedding: dict[str, Any]
    anomaly_model: str | None = None
    persist: bool = False
    patient_id: str | None = None
    test_result_id: int | None = None
    test_name: str | None = None
    session_id: str | None = None


class AnomalyReviewWindow(BaseModel):
    start_sec: float
    end_sec: float
    predicted_label: Literal["normal", "anomalous"]
    anomaly_probability: float | None = None
    anomaly_score: float | None = None


class AnomalyPredictionResponse(BaseModel):
    filename: str | None = None
    predicted_label: Literal["normal", "anomalous"]
    anomaly_probability: float | None = None
    anomaly_score: float | None = None
    anomaly_model: str
    video_model: str | None = None
    model_version: str | None = None
    model_artifact_path: str | None = None
    prediction_id: int | None = None
    test_result_id: int | None = None
    persisted: bool = False
    review_windows: list[AnomalyReviewWindow] = Field(default_factory=list)


class VideoAnomalyRequest(BaseModel):
    video_path: str
    video_model: str | None = None
    anomaly_model: str | None = None
    persist: bool = False
    patient_id: str | None = None
    test_result_id: int | None = None
    test_name: str | None = None
    session_id: str | None = None
    review_window_seconds: float | None = Field(default=None, gt=0)


class MLPredictionRecord(BaseModel):
    prediction_id: int
    test_result_id: int
    patient_id: str | None = None
    session_id: str | None = None
    test_name: str | None = None
    prediction_type: str
    video_model: str | None = None
    classifier_model: str | None = None
    model_version: str | None = None
    model_artifact_path: str | None = None
    predicted_label: str
    probability: float | None = None
    score: float | None = None
    input_video_path: str | None = None
    input_filename: str | None = None
    embedding_artifact_path: str | None = None
    request_json: dict[str, Any] | None = None
    response_json: dict[str, Any] | None = None
    error_json: dict[str, Any] | None = None
    created_at: str


class MLPredictionListResponse(BaseModel):
    predictions: list[MLPredictionRecord] = Field(default_factory=list)
