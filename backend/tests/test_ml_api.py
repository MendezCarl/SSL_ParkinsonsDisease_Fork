from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from repo.sql_models import Base, MLPrediction, Patient, TestResult, User
from scripts.migrate_ml_predictions import migrate_ml_predictions
import routes.ml as ml_routes
import services.test_history_service as test_history_service


class _FakeAnomalyClassifier:
    required_keys = {
        "view_0_mean_pooled_embedding",
        "view_1_mean_pooled_embedding",
        "view_2_mean_pooled_embedding",
        "view_3_mean_pooled_embedding",
    }

    def predict_from_record(self, record: dict) -> dict:
        missing = sorted(self.required_keys - set(record))
        if missing:
            raise KeyError(f"Embedding record is missing keys: {missing}")
        return {
            "filename": record.get("filename"),
            "predicted_label": "anomalous",
            "anomaly_probability": 0.87,
            "model_name": "fake_logistic_vjepa2",
            "model_path": "/tmp/fake-model.joblib",
        }


def _embedding() -> dict:
    return {
        "view_0_mean_pooled_embedding": [0.1, 0.2],
        "view_1_mean_pooled_embedding": [0.3, 0.4],
        "view_2_mean_pooled_embedding": [0.5, 0.6],
        "view_3_mean_pooled_embedding": [0.7, 0.8],
    }


def _set_temp_ml_db(monkeypatch, db_path: Path):
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    event.listen(engine, "connect", lambda dbapi_conn, _: dbapi_conn.execute("PRAGMA foreign_keys = ON;"))
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(ml_routes, "SessionLocal", session_local)
    monkeypatch.setattr(test_history_service, "SessionLocal", session_local)
    return session_local


def _seed_test_result(session_local, *, patient_id="patient-ml", session_id="session-ml") -> int:
    with session_local() as session:
        owner = User(
            username=f"{patient_id}@example.com",
            full_name="ML Test Owner",
            email=None,
            hashed_password="test",
            location="Test",
            title="Tester",
            speciality="Test",
        )
        session.add(owner)
        session.flush()
        session.add(
            Patient(
                patient_id=patient_id,
                record_number=f"REC-{patient_id[-6:]}",
                user_id=owner.id,
                name=patient_id,
            )
        )
        session.flush()
        row = TestResult(
            patient_id=patient_id,
            test_name="finger-tapping",
            recording_file="finger-tapping.mp4",
            session_id=session_id,
        )
        session.add(row)
        session.commit()
        return row.test_id


def _client_with_fake_classifier(monkeypatch) -> TestClient:
    monkeypatch.setattr(ml_routes, "get_anomaly_classifier", lambda _name: _FakeAnomalyClassifier())
    return TestClient(app)


def test_ml_models_returns_registered_models():
    response = TestClient(app).get("/ml/models")

    assert response.status_code == 200
    body = response.json()
    assert "dummy" in body["video_models"]
    assert "logistic_vjepa2" in body["anomaly_models"]
    assert body["default_video_model"] == "dummy"
    assert body["default_anomaly_model"] == "logistic_vjepa2"


def test_invalid_anomaly_model_returns_400():
    response = TestClient(app).post(
        "/ml/predict-anomaly-from-embedding",
        json={"filename": "sample.mp4", "embedding": _embedding(), "anomaly_model": "missing-model"},
    )

    assert response.status_code == 400
    assert "Unknown anomaly model" in response.json()["detail"]


def test_missing_embedding_key_returns_400(monkeypatch):
    client = _client_with_fake_classifier(monkeypatch)
    embedding = _embedding()
    embedding.pop("view_3_mean_pooled_embedding")

    response = client.post(
        "/ml/predict-anomaly-from-embedding",
        json={"filename": "sample.mp4", "embedding": embedding},
    )

    assert response.status_code == 400
    assert "missing keys" in response.json()["detail"]


def test_predict_anomaly_from_video_returns_501_for_dummy_embedder():
    response = TestClient(app).post(
        "/ml/predict-anomaly-from-video",
        json={"video_path": "/tmp/sample.mp4", "video_model": "dummy"},
    )

    assert response.status_code == 501
    assert "dummy video embedder" in response.json()["detail"]


def test_persist_false_does_not_insert_prediction(monkeypatch, tmp_path):
    session_local = _set_temp_ml_db(monkeypatch, tmp_path / "ml.db")
    test_result_id = _seed_test_result(session_local)
    client = _client_with_fake_classifier(monkeypatch)

    response = client.post(
        "/ml/predict-anomaly-from-embedding",
        json={
            "filename": "sample.mp4",
            "embedding": _embedding(),
            "persist": False,
            "test_result_id": test_result_id,
        },
    )

    assert response.status_code == 200
    assert response.json()["persisted"] is False
    with session_local() as session:
        assert session.query(MLPrediction).count() == 0


def test_persist_true_with_test_result_id_inserts_prediction(monkeypatch, tmp_path):
    session_local = _set_temp_ml_db(monkeypatch, tmp_path / "ml.db")
    test_result_id = _seed_test_result(session_local)
    client = _client_with_fake_classifier(monkeypatch)

    response = client.post(
        "/ml/predict-anomaly-from-embedding",
        json={
            "filename": "sample.mp4",
            "embedding": _embedding(),
            "persist": True,
            "test_result_id": test_result_id,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is True
    assert body["test_result_id"] == test_result_id
    assert body["prediction_id"] is not None
    with session_local() as session:
        row = session.query(MLPrediction).one()
        assert row.test_result_id == test_result_id
        assert row.predicted_label == "anomalous"
        assert row.probability == 0.87


def test_persist_true_with_patient_and_session_resolves_test_result(monkeypatch, tmp_path):
    session_local = _set_temp_ml_db(monkeypatch, tmp_path / "ml.db")
    test_result_id = _seed_test_result(session_local, patient_id="patient-resolve", session_id="session-resolve")
    client = _client_with_fake_classifier(monkeypatch)

    response = client.post(
        "/ml/predict-anomaly-from-embedding",
        json={
            "filename": "sample.mp4",
            "embedding": _embedding(),
            "persist": True,
            "patient_id": "patient-resolve",
            "session_id": "session-resolve",
        },
    )

    assert response.status_code == 200
    assert response.json()["test_result_id"] == test_result_id


def test_unresolvable_persist_returns_400(monkeypatch, tmp_path):
    _set_temp_ml_db(monkeypatch, tmp_path / "ml.db")
    client = _client_with_fake_classifier(monkeypatch)

    response = client.post(
        "/ml/predict-anomaly-from-embedding",
        json={
            "filename": "sample.mp4",
            "embedding": _embedding(),
            "persist": True,
            "patient_id": "missing-patient",
            "session_id": "missing-session",
        },
    )

    assert response.status_code == 400
    assert "Unable to resolve" in response.json()["detail"]


def test_predictions_for_test_returns_rows(monkeypatch, tmp_path):
    session_local = _set_temp_ml_db(monkeypatch, tmp_path / "ml.db")
    test_result_id = _seed_test_result(session_local)
    with session_local() as session:
        session.add(
            MLPrediction(
                test_result_id=test_result_id,
                patient_id="patient-ml",
                session_id="session-ml",
                test_name="finger-tapping",
                prediction_type="whole_video_anomaly",
                classifier_model="logistic_vjepa2",
                predicted_label="normal",
                probability=0.12,
            )
        )
        session.commit()

    response = TestClient(app).get(f"/ml/predictions/test/{test_result_id}")

    assert response.status_code == 200
    predictions = response.json()["predictions"]
    assert len(predictions) == 1
    assert predictions[0]["test_result_id"] == test_result_id
    assert predictions[0]["predicted_label"] == "normal"


def test_test_history_includes_latest_anomaly_summary(monkeypatch, tmp_path):
    session_local = _set_temp_ml_db(monkeypatch, tmp_path / "ml.db")
    test_result_id = _seed_test_result(session_local)
    with session_local() as session:
        session.add_all(
            [
                MLPrediction(
                    test_result_id=test_result_id,
                    patient_id="patient-ml",
                    session_id="session-ml",
                    test_name="finger-tapping",
                    prediction_type="whole_video_anomaly",
                    classifier_model="logistic_vjepa2",
                    predicted_label="normal",
                    probability=0.12,
                ),
                MLPrediction(
                    test_result_id=test_result_id,
                    patient_id="patient-ml",
                    session_id="session-ml",
                    test_name="finger-tapping",
                    prediction_type="whole_video_anomaly",
                    classifier_model="logistic_vjepa2",
                    predicted_label="anomalous",
                    probability=0.91,
                ),
            ]
        )
        session.commit()

    tests = test_history_service.get_patient_tests("patient-ml")

    assert tests[0]["analysis"]["anomaly_prediction"]["predicted_label"] == "anomalous"
    assert tests[0]["analysis"]["anomaly_prediction"]["anomaly_probability"] == 0.91


def test_migrate_ml_predictions_is_idempotent(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"

    first_report = migrate_ml_predictions(database_url)
    second_report = migrate_ml_predictions(database_url)

    assert first_report["created"] is True
    assert first_report["missing_indexes"] == []
    assert second_report["created"] is False
    assert second_report["missing_indexes"] == []
