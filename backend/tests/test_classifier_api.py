from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import routes.classifier as classifier_routes
from main import app


def _valid_payload() -> dict:
    return {
        "sequence": [[0.1] * 24 for _ in range(30)],
        "return_attention": False,
    }


def _mock_prediction() -> dict:
    return {
        "predicted_updrs_stage": 2,
        "probabilities": {"0": 0.1, "1": 0.2, "2": 0.6, "3": 0.1},
        "severity": "Stage 3",
        "severity_stage": 3,
        "prediction": "Stage 3",
        "confidence": 0.6,
        "lstm_output": [0.1, 0.2, 0.6, 0.1],
        "logits": [0.1, 0.2, 0.8, 0.05],
        "n_windows": 1,
        "window_size": 30,
        "stride": 10,
        "model_version": "lstm_cnn_mil_v1",
        "preprocessing_version": "window30_stride10_features24",
        "checkpoint_path": "checkpoint.pt",
        "attention_weights": None,
    }


def test_predict_and_update_success(monkeypatch):
    def fake_predict(sequence, return_attention=False):
        return _mock_prediction()

    async def fake_update(patient_id, updated_data):
        return {"success": True, "patient_id": patient_id}

    monkeypatch.setattr(classifier_routes.inference_service, "predict", fake_predict)
    monkeypatch.setattr(classifier_routes, "async_update_patient_info", fake_update)

    client = TestClient(app)
    response = client.post("/ml/updrs/predict/patients/patient123", json=_valid_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["patient_id"] == "patient123"
    assert body["patient_updated"] is True
    assert body["severity"] == "Stage 3"


def test_predict_and_update_unknown_patient_returns_404(monkeypatch):
    def fake_predict(sequence, return_attention=False):
        return _mock_prediction()

    async def fake_update(patient_id, updated_data):
        return {"success": False, "error": "Patient not found"}

    monkeypatch.setattr(classifier_routes.inference_service, "predict", fake_predict)
    monkeypatch.setattr(classifier_routes, "async_update_patient_info", fake_update)

    client = TestClient(app)
    response = client.post("/ml/updrs/predict/patients/unknown", json=_valid_payload())

    assert response.status_code == 404
    assert response.json()["detail"] == "Patient not found"


def test_predict_and_update_bad_inference_returns_400(monkeypatch):
    def fake_predict(sequence, return_attention=False):
        raise ValueError("invalid sequence")

    monkeypatch.setattr(classifier_routes.inference_service, "predict", fake_predict)

    client = TestClient(app)
    response = client.post("/ml/updrs/predict/patients/patient123", json=_valid_payload())

    assert response.status_code == 400
    assert "invalid sequence" in response.json()["detail"]


def test_predict_only_mode_with_unknown_patient_returns_200(monkeypatch):
    def fake_predict(sequence, return_attention=False):
        return _mock_prediction()

    async def fake_update(patient_id, updated_data):
        raise AssertionError("update should not be called when persist_update=false")

    monkeypatch.setattr(classifier_routes.inference_service, "predict", fake_predict)
    monkeypatch.setattr(classifier_routes, "async_update_patient_info", fake_update)

    client = TestClient(app)
    response = client.post(
        "/ml/updrs/predict/patients/unknown?persist_update=false",
        json=_valid_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["patient_id"] == "unknown"
    assert body["patient_updated"] is False


def test_predict_validation_error_returns_422():
    client = TestClient(app)
    payload = {
        "sequence": [[0.1] * 23 for _ in range(30)],  # invalid feature dim
        "return_attention": False,
    }
    response = client.post("/ml/updrs/predict/patients/patient123", json=payload)
    assert response.status_code == 422


def test_predict_checkpoint_missing_returns_500(monkeypatch):
    def fake_predict(sequence, return_attention=False):
        raise FileNotFoundError("checkpoint missing")

    monkeypatch.setattr(classifier_routes.inference_service, "predict", fake_predict)

    client = TestClient(app)
    response = client.post("/ml/updrs/predict/patients/patient123", json=_valid_payload())

    assert response.status_code == 500
    assert "checkpoint missing" in response.json()["detail"]
