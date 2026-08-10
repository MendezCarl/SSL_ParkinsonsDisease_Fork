from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ml.registry import (
    DEFAULT_ANOMALY_MODEL,
    DEFAULT_VIDEO_MODEL,
    get_anomaly_classifier,
    get_video_embedder,
    list_anomaly_models,
    list_video_models,
    selected_anomaly_model_name,
    selected_video_model_name,
)
from ml.schemas import (
    AnomalyEmbeddingRequest,
    AnomalyPredictionResponse,
    AvailableModelsResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    MLPredictionListResponse,
    VideoAnomalyRequest,
)
from patient_manager import SessionLocal
from services.ml_prediction_service import (
    WHOLE_VIDEO_ANOMALY,
    create_ml_prediction,
    predictions_for_patient,
    predictions_for_session,
    predictions_for_test_result,
    serialize_ml_prediction,
)


router = APIRouter()


def _to_prediction_response(
    *,
    raw_result: dict[str, Any],
    anomaly_model: str,
    video_model: str | None = None,
    prediction_id: int | None = None,
    test_result_id: int | None = None,
    persisted: bool = False,
) -> AnomalyPredictionResponse:
    return AnomalyPredictionResponse(
        filename=raw_result.get("filename"),
        predicted_label=raw_result["predicted_label"],
        anomaly_probability=raw_result.get("anomaly_probability"),
        anomaly_score=raw_result.get("anomaly_score"),
        anomaly_model=anomaly_model,
        video_model=video_model,
        model_version=raw_result.get("model_name"),
        model_artifact_path=raw_result.get("model_path"),
        prediction_id=prediction_id,
        test_result_id=test_result_id,
        persisted=persisted,
    )


def _prediction_request_metadata(payload: AnomalyEmbeddingRequest | VideoAnomalyRequest) -> dict[str, Any]:
    data = payload.model_dump(exclude={"embedding"}, exclude_none=True)
    return data or {}


def _persist_prediction(
    *,
    payload: AnomalyEmbeddingRequest | VideoAnomalyRequest,
    response: AnomalyPredictionResponse,
    anomaly_model: str,
    input_video_path: str | None = None,
) -> tuple[int, int]:
    with SessionLocal() as session:
        try:
            row = create_ml_prediction(
                session,
                prediction_type=WHOLE_VIDEO_ANOMALY,
                predicted_label=response.predicted_label,
                test_result_id=payload.test_result_id,
                patient_id=payload.patient_id,
                session_id=payload.session_id,
                test_name=payload.test_name,
                recording_file=getattr(payload, "filename", None),
                probability=response.anomaly_probability,
                score=response.anomaly_score,
                video_model=response.video_model,
                classifier_model=anomaly_model,
                model_version=response.model_version,
                model_artifact_path=response.model_artifact_path,
                input_video_path=input_video_path,
                input_filename=response.filename,
                request_json=_prediction_request_metadata(payload),
                response_json=response.model_dump(exclude_none=True),
            )
            session.commit()
            return row.prediction_id, row.test_result_id
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/models",
    response_model=AvailableModelsResponse,
    summary="List available stateless ML models",
    description="Returns registered video embedding models, registered anomaly classifiers, and their defaults.",
)
async def get_models() -> AvailableModelsResponse:
    return AvailableModelsResponse(
        video_models=list_video_models(),
        anomaly_models=list_anomaly_models(),
        default_video_model=DEFAULT_VIDEO_MODEL,
        default_anomaly_model=DEFAULT_ANOMALY_MODEL,
    )


@router.post(
    "/predict-anomaly-from-embedding",
    response_model=AnomalyPredictionResponse,
    summary="Predict whole-video anomaly from an embedding record",
    description=(
        "Runs the selected whole-video anomaly classifier on a precomputed embedding record. "
        "This predicts normal/anomalous only. If persist=true, the result is stored in "
        "ml_predictions and linked to an existing test history row."
    ),
)
async def predict_anomaly_from_embedding(payload: AnomalyEmbeddingRequest) -> AnomalyPredictionResponse:
    try:
        anomaly_model = selected_anomaly_model_name(payload.anomaly_model)
        classifier = get_anomaly_classifier(anomaly_model)
        record = dict(payload.embedding)
        record["filename"] = payload.filename
        raw_result = classifier.predict_from_record(record)
        response = _to_prediction_response(raw_result=raw_result, anomaly_model=anomaly_model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.persist:
        prediction_id, test_result_id = _persist_prediction(
            payload=payload,
            response=response,
            anomaly_model=anomaly_model,
        )
        response.prediction_id = prediction_id
        response.test_result_id = test_result_id
        response.persisted = True

    return response


@router.post(
    "/embed-video",
    response_model=EmbeddingResponse,
    summary="Generate video embedding metadata",
    description=(
        "Runs the selected video embedding model. The current dummy embedder is a placeholder "
        "and returns 501 until a real embedding model is registered."
    ),
)
async def embed_video(payload: EmbeddingRequest) -> EmbeddingResponse:
    try:
        video_model = selected_video_model_name(payload.video_model)
        embedder = get_video_embedder(video_model)
        embedding = embedder.embed_video(Path(payload.video_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    feature_keys = [key for key in embedding if key != "filename"]
    embedding_dim = sum(len(value) for key, value in embedding.items() if key != "filename" and hasattr(value, "__len__"))
    return EmbeddingResponse(
        filename=str(embedding.get("filename") or Path(payload.video_path).name),
        video_model=video_model,
        embedding_dim=embedding_dim,
        feature_keys=feature_keys,
    )


@router.post(
    "/predict-anomaly-from-video",
    response_model=AnomalyPredictionResponse,
    summary="Predict whole-video anomaly from a saved video",
    description=(
        "Runs the selected video embedding model, then the selected whole-video anomaly classifier. "
        "This predicts normal/anomalous only. The current dummy embedder returns 501 until a real "
        "video embedding model is registered."
    ),
)
async def predict_anomaly_from_video(payload: VideoAnomalyRequest) -> AnomalyPredictionResponse:
    try:
        video_model = selected_video_model_name(payload.video_model)
        anomaly_model = selected_anomaly_model_name(payload.anomaly_model)
        embedder = get_video_embedder(video_model)
        embedding = embedder.embed_video(Path(payload.video_path))
        classifier = get_anomaly_classifier(anomaly_model)
        raw_result = classifier.predict_from_record(embedding)
        response = _to_prediction_response(
            raw_result=raw_result,
            anomaly_model=anomaly_model,
            video_model=video_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    if payload.persist:
        prediction_id, test_result_id = _persist_prediction(
            payload=payload,
            response=response,
            anomaly_model=anomaly_model,
            input_video_path=payload.video_path,
        )
        response.prediction_id = prediction_id
        response.test_result_id = test_result_id
        response.persisted = True

    return response


@router.get(
    "/predictions/test/{test_result_id}",
    response_model=MLPredictionListResponse,
    summary="List ML predictions for a test result",
)
async def get_predictions_for_test(test_result_id: int) -> MLPredictionListResponse:
    with SessionLocal() as session:
        rows = predictions_for_test_result(session, test_result_id)
        return MLPredictionListResponse(predictions=[serialize_ml_prediction(row) for row in rows])


@router.get(
    "/predictions/session/{session_id}",
    response_model=MLPredictionListResponse,
    summary="List ML predictions for a DTW/session id",
)
async def get_predictions_for_session(session_id: str) -> MLPredictionListResponse:
    with SessionLocal() as session:
        rows = predictions_for_session(session, session_id)
        return MLPredictionListResponse(predictions=[serialize_ml_prediction(row) for row in rows])


@router.get(
    "/predictions/patient/{patient_id}",
    response_model=MLPredictionListResponse,
    summary="List recent ML predictions for a patient",
)
async def get_predictions_for_patient(
    patient_id: str,
    limit: int = Query(default=50, ge=1, le=200),
) -> MLPredictionListResponse:
    with SessionLocal() as session:
        rows = predictions_for_patient(session, patient_id, limit=limit)
        return MLPredictionListResponse(predictions=[serialize_ml_prediction(row) for row in rows])
