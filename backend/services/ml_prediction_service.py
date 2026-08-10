from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from repo.sql_models import MLPrediction, TestResult


WHOLE_VIDEO_ANOMALY = "whole_video_anomaly"


def resolve_test_result(
    session: Session,
    *,
    test_result_id: int | None = None,
    patient_id: str | None = None,
    session_id: str | None = None,
    test_name: str | None = None,
    recording_file: str | None = None,
) -> TestResult | None:
    if test_result_id is not None:
        return session.get(TestResult, test_result_id)

    scoped_patient_id = (patient_id or "").strip()
    if not scoped_patient_id:
        return None

    scoped_session_id = (session_id or "").strip()
    if scoped_session_id:
        return (
            session.query(TestResult)
            .filter(TestResult.patient_id == scoped_patient_id, TestResult.session_id == scoped_session_id)
            .order_by(TestResult.test_id.desc())
            .first()
        )

    scoped_test_name = (test_name or "").strip()
    scoped_recording_file = (recording_file or "").strip()
    if scoped_test_name and scoped_recording_file:
        return (
            session.query(TestResult)
            .filter(
                TestResult.patient_id == scoped_patient_id,
                TestResult.test_name == scoped_test_name,
                TestResult.recording_file == scoped_recording_file,
            )
            .order_by(TestResult.test_id.desc())
            .first()
        )

    return None


def create_ml_prediction(
    session: Session,
    *,
    prediction_type: str,
    predicted_label: str,
    test_result_id: int | None = None,
    patient_id: str | None = None,
    session_id: str | None = None,
    test_name: str | None = None,
    recording_file: str | None = None,
    probability: float | None = None,
    score: float | None = None,
    video_model: str | None = None,
    classifier_model: str | None = None,
    model_version: str | None = None,
    model_artifact_path: str | None = None,
    input_video_path: str | None = None,
    input_filename: str | None = None,
    embedding_artifact_path: str | None = None,
    request_json: dict[str, Any] | None = None,
    response_json: dict[str, Any] | None = None,
    error_json: dict[str, Any] | None = None,
) -> MLPrediction:
    test_result = resolve_test_result(
        session,
        test_result_id=test_result_id,
        patient_id=patient_id,
        session_id=session_id,
        test_name=test_name,
        recording_file=recording_file,
    )
    if test_result is None:
        raise ValueError("Unable to resolve an existing test result for persisted ML prediction")

    row = MLPrediction(
        test_result_id=test_result.test_id,
        patient_id=test_result.patient_id,
        session_id=test_result.session_id,
        test_name=test_result.test_name,
        prediction_type=prediction_type,
        video_model=video_model,
        classifier_model=classifier_model,
        model_version=model_version,
        model_artifact_path=model_artifact_path,
        predicted_label=predicted_label,
        probability=probability,
        score=score,
        input_video_path=input_video_path,
        input_filename=input_filename or recording_file,
        embedding_artifact_path=embedding_artifact_path,
        request_json=request_json,
        response_json=response_json,
        error_json=error_json,
    )
    session.add(row)
    session.flush()
    return row


def serialize_ml_prediction(row: MLPrediction) -> dict[str, Any]:
    created = row.created_at
    if created.tzinfo is None:
        created_at = created.replace(tzinfo=timezone.utc).isoformat()
    else:
        created_at = created.astimezone(timezone.utc).isoformat()
    return {
        "prediction_id": row.prediction_id,
        "test_result_id": row.test_result_id,
        "patient_id": row.patient_id,
        "session_id": row.session_id,
        "test_name": row.test_name,
        "prediction_type": row.prediction_type,
        "video_model": row.video_model,
        "classifier_model": row.classifier_model,
        "model_version": row.model_version,
        "model_artifact_path": row.model_artifact_path,
        "predicted_label": row.predicted_label,
        "probability": row.probability,
        "score": row.score,
        "input_video_path": row.input_video_path,
        "input_filename": row.input_filename,
        "embedding_artifact_path": row.embedding_artifact_path,
        "request_json": row.request_json,
        "response_json": row.response_json,
        "error_json": row.error_json,
        "created_at": created_at,
    }


def latest_prediction_for_test_result(
    session: Session,
    test_result_id: int,
    prediction_type: str,
) -> MLPrediction | None:
    return (
        session.query(MLPrediction)
        .filter(
            MLPrediction.test_result_id == test_result_id,
            MLPrediction.prediction_type == prediction_type,
        )
        .order_by(MLPrediction.created_at.desc(), MLPrediction.prediction_id.desc())
        .first()
    )


def predictions_for_test_result(session: Session, test_result_id: int) -> list[MLPrediction]:
    return (
        session.query(MLPrediction)
        .filter(MLPrediction.test_result_id == test_result_id)
        .order_by(MLPrediction.created_at.desc(), MLPrediction.prediction_id.desc())
        .all()
    )


def predictions_for_session(session: Session, session_id: str) -> list[MLPrediction]:
    return (
        session.query(MLPrediction)
        .filter(MLPrediction.session_id == session_id)
        .order_by(MLPrediction.created_at.desc(), MLPrediction.prediction_id.desc())
        .all()
    )


def predictions_for_patient(session: Session, patient_id: str, limit: int = 50) -> list[MLPrediction]:
    return (
        session.query(MLPrediction)
        .filter(MLPrediction.patient_id == patient_id)
        .order_by(MLPrediction.created_at.desc(), MLPrediction.prediction_id.desc())
        .limit(limit)
        .all()
    )


def anomaly_summary(row: MLPrediction) -> dict[str, Any]:
    payload = serialize_ml_prediction(row)
    response_json = payload.get("response_json") if isinstance(payload.get("response_json"), dict) else {}
    return {
        "prediction_id": payload["prediction_id"],
        "test_result_id": payload["test_result_id"],
        "predicted_label": payload["predicted_label"],
        "anomaly_probability": payload["probability"],
        "anomaly_score": payload["score"],
        "video_model": payload["video_model"],
        "anomaly_model": payload["classifier_model"],
        "classifier_model": payload["classifier_model"],
        "model_version": payload["model_version"],
        "created_at": payload["created_at"],
        "persisted": True,
        "review_windows": response_json.get("review_windows") or [],
    }
