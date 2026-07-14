from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user
from schema.patient_contracts import PatientUpdate
from routes.utils_dtw import resolve_dtw_session_dir
from services import patient_service
from services.test_history_service import persist_session_analysis
from schema.classifier_schema import (
    APIErrorResponse,
    LSTMCNNPredictAndUpdateResponse,
    LSTMCNNPredictRequest,
    LSTMCNNPredictResponse,
)
from services.lstm_cnn_inference import LSTMCNNInferenceService, get_inference_service

# Hand landmark indices used to build the (T,24) sequence for the ML model.
# 8 landmarks × (x, y from DTW) + z=0  →  8×3 = 24 features
# Chosen: wrist(0), thumb-tip(4), thumb-MCP(5), index-tip(8), index-MCP(9),
#         middle-tip(12), ring-tip(16), pinky-tip(20)
_HAND_LM_IDX = [0, 4, 5, 8, 9, 12, 16, 20]

# Pose landmark indices for stand-and-sit (hip-normalised 66D → 8 landmarks)
# nose(0), l-shoulder(11), r-shoulder(12), l-hip(23), r-hip(24),
# l-knee(25), r-knee(26), l-ankle(27)
_POSE_LM_IDX = [0, 11, 12, 23, 24, 25, 26, 27]


def _session_to_ml_sequence(test_name: str, session_id: str) -> np.ndarray:
    """
    Load the DTW session for *test_name/session_id*, extract X_live,
    and return a (T, 24) float32 array suitable for the ML model.

    X_live shape depends on the test:
      hands model → (T, 42)  [21 landmarks × xy, wrist-normalised]
      pose  model → (T, 66)  [33 landmarks × xy, hip-normalised]

    Strategy: take 8 key landmark (x, y) pairs and pad z=0 → (T, 24).
    """
    try:
        session_dir = resolve_dtw_session_dir(test_name, session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not session_dir.is_dir():
        raise HTTPException(
            404,
            f"DTW session '{session_id}' not found for test '{test_name}'. "
            "Run the test first, then request the prediction.",
        )

    npz_path = session_dir / "dtw_artifacts.npz"
    if not npz_path.exists():
        raise HTTPException(404, f"DTW artifacts not found at {npz_path}.")

    data = np.load(str(npz_path))
    X_live: np.ndarray = data["X_live"].astype(np.float32)  # (T, D)
    T, D = X_live.shape

    if D == 42:
        # Hands: 21 landmarks × 2 (x, y)
        lm_indices = _HAND_LM_IDX
        coords_per_lm = 2
    elif D == 66:
        # Pose: 33 landmarks × 2 (x, y)
        lm_indices = _POSE_LM_IDX
        coords_per_lm = 2
    else:
        raise HTTPException(
            422,
            f"Unexpected X_live dimension {D}. Expected 42 (hands) or 66 (pose).",
        )

    # Extract the 8 chosen landmarks' (x, y) and add z=0 → (T, 24)
    seq = np.zeros((T, 24), dtype=np.float32)
    for out_i, lm_i in enumerate(lm_indices):
        col = lm_i * coords_per_lm
        seq[:, out_i * 3 + 0] = X_live[:, col]       # x
        seq[:, out_i * 3 + 1] = X_live[:, col + 1]   # y
        seq[:, out_i * 3 + 2] = 0.0                   # z (not recorded in DTW pipeline)

    return seq


router = APIRouter(prefix="/ml", tags=["ml"], dependencies=[Depends(get_current_user)])


@router.post(
    "/updrs/predict",
    response_model=LSTMCNNPredictResponse,
    responses={400: {"model": APIErrorResponse}, 500: {"model": APIErrorResponse}},
)
async def predict_updrs(
    payload: LSTMCNNPredictRequest,
    inference_service: LSTMCNNInferenceService = Depends(get_inference_service),
) -> LSTMCNNPredictResponse:
    try:
        result = inference_service.predict(
            sequence=payload.sequence,
            return_attention=payload.return_attention,
        )
        return LSTMCNNPredictResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run LSTM-CNN inference: {exc}") from exc


@router.post(
    "/updrs/predict/patients/{patient_id}",
    response_model=LSTMCNNPredictAndUpdateResponse,
    responses={400: {"model": APIErrorResponse}, 404: {"model": APIErrorResponse}, 500: {"model": APIErrorResponse}},
)
async def predict_updrs_and_update_patient(
    patient_id: str,
    payload: LSTMCNNPredictRequest,
    persist_update: bool = Query(
        default=True,
        description="When false, return prediction without updating patient severity.",
    ),
    inference_service: LSTMCNNInferenceService = Depends(get_inference_service),
) -> LSTMCNNPredictAndUpdateResponse:
    try:
        result = inference_service.predict(
            sequence=payload.sequence,
            return_attention=payload.return_attention,
        )

        patient_updated = False
        if persist_update:
            update_result = await patient_service.update_patient(
                patient_id,
                PatientUpdate(severity=result["severity"]),
            )
            if not update_result.get("success"):
                error_detail = update_result.get("error", "Failed to update patient severity")
                if error_detail == "Patient not found":
                    raise HTTPException(status_code=404, detail=error_detail)
                raise HTTPException(status_code=400, detail=error_detail)
            patient_updated = True

        return LSTMCNNPredictAndUpdateResponse(
            **result,
            patient_id=patient_id,
            patient_updated=patient_updated,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run LSTM-CNN integration flow: {exc}") from exc


@router.get(
    "/updrs/from_session/{test_name}/{session_id}",
    response_model=LSTMCNNPredictResponse,
    responses={404: {"model": APIErrorResponse}, 422: {"model": APIErrorResponse}, 500: {"model": APIErrorResponse}},
    summary="Predict UPDRS stage from a saved DTW session",
    description=(
        "Loads X_live from a previously saved DTW session, extracts 8 key landmarks "
        "(x, y; z padded to 0) to form a (T, 24) sequence, and runs LSTM-MIL inference. "
        "NOTE: The model was trained on finger-tapping data. Predictions for other test "
        "types are experimental."
    ),
)
async def predict_updrs_from_session(
    test_name: str,
    session_id: str,
    inference_service: LSTMCNNInferenceService = Depends(get_inference_service),
) -> LSTMCNNPredictResponse:
    seq = _session_to_ml_sequence(test_name, session_id)
    try:
        result = inference_service.predict(sequence=seq, return_attention=False)
        persist_session_analysis(
            session_id,
            ml_prediction={
                "predicted_updrs_stage": result.get("predicted_updrs_stage"),
                "probabilities": result.get("probabilities"),
                "severity": result.get("severity"),
                "severity_stage": result.get("severity_stage"),
                "prediction": result.get("prediction"),
                "confidence": result.get("confidence"),
                "model_version": result.get("model_version"),
                "preprocessing_version": result.get("preprocessing_version"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return LSTMCNNPredictResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ML inference failed: {exc}") from exc
