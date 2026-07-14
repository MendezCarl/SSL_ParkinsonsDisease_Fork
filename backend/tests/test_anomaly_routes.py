from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import auth
import routes.utils_dtw as utils_dtw
import services.anomaly_service as anomaly_service
import services.recording_service as recording_service
from auth import get_current_user
from main import app

WORKER_TOKEN = "test-worker-secret"


def _worker_headers():
    return {"Authorization": f"Bearer {WORKER_TOKEN}"}


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "_ANOMALY_WORKER_TOKEN", WORKER_TOKEN)
    dtw_base = tmp_path / "dtw_runs"
    dtw_base.mkdir()
    monkeypatch.setattr(utils_dtw, "DTW_BASE", dtw_base)
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir()
    monkeypatch.setattr(recording_service, "RECORDINGS_DIR", recordings_dir)
    return dtw_base, recordings_dir


def _create_patient(client: TestClient) -> str:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/patients/",
        json={
            "name": f"Anomaly Test {suffix}",
            "age": 65,
            "birthDate": "1960-01-01",
            "height": 170,
            "weight": 70,
            "severity": "Stage 2",
            "lab_results_history": [],
            "doctors_notes_history": [],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["patient_id"]


def test_submit_job_requires_doctor_auth():
    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app)
    response = client.post("/ml/anomaly/sessions/finger-tapping/some-session?patient_id=whoever")
    assert response.status_code == 401


def test_submit_and_poll_job_end_to_end(tmp_path, monkeypatch):
    dtw_base, recordings_dir = _setup(tmp_path, monkeypatch)
    client = TestClient(app)

    patient_id = _create_patient(client)
    session_id = "session-e2e-1"
    (dtw_base / "finger-tapping" / session_id).mkdir(parents=True)
    monkeypatch.setattr(anomaly_service, "_find_recording_file", lambda *_: "clip.mp4")
    (recordings_dir / "clip.mp4").write_bytes(b"fake-mp4")

    submit = client.post(f"/ml/anomaly/sessions/finger-tapping/{session_id}?patient_id={patient_id}")
    assert submit.status_code == 200, submit.text
    job_id = submit.json()["job_id"]
    assert submit.json()["status"] == "pending"

    status = client.get(f"/ml/anomaly/jobs/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "pending"
    assert status.json()["result"] is None


def test_submit_job_missing_session_returns_404(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    client = TestClient(app)
    patient_id = _create_patient(client)

    response = client.post(f"/ml/anomaly/sessions/finger-tapping/no-such-session?patient_id={patient_id}")
    assert response.status_code == 404


def test_worker_routes_reject_missing_or_wrong_token(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    client = TestClient(app)

    assert client.get("/ml/anomaly/jobs").status_code == 401
    assert client.get("/ml/anomaly/jobs", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_worker_routes_reject_doctor_jwt(tmp_path, monkeypatch):
    # A real doctor bearer token must not satisfy worker auth, even once the
    # worker secret is configured -- the two auth paths must stay separate.
    _setup(tmp_path, monkeypatch)
    client = TestClient(app)

    token_response = client.post(
        "/token",
        data={"username": "doctor@hospital.com", "password": "Demo123!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert token_response.status_code == 200
    doctor_token = token_response.json()["access_token"]

    response = client.get("/ml/anomaly/jobs", headers={"Authorization": f"Bearer {doctor_token}"})
    assert response.status_code == 401


def test_worker_can_list_fetch_and_complete_job(tmp_path, monkeypatch):
    dtw_base, recordings_dir = _setup(tmp_path, monkeypatch)
    client = TestClient(app)

    patient_id = _create_patient(client)
    session_id = "session-worker-1"
    (dtw_base / "finger-tapping" / session_id).mkdir(parents=True)
    monkeypatch.setattr(anomaly_service, "_find_recording_file", lambda *_: "clip.mp4")
    (recordings_dir / "clip.mp4").write_bytes(b"fake-mp4")

    submit = client.post(f"/ml/anomaly/sessions/finger-tapping/{session_id}?patient_id={patient_id}")
    job_id = submit.json()["job_id"]

    pending = client.get("/ml/anomaly/jobs", headers=_worker_headers())
    assert pending.status_code == 200
    assert any(job["job_id"] == job_id for job in pending.json())

    video = client.get(f"/ml/anomaly/jobs/{job_id}/video", headers=_worker_headers())
    assert video.status_code == 200
    assert video.content == b"fake-mp4"

    mid_status = client.get(f"/ml/anomaly/jobs/{job_id}")
    assert mid_status.json()["status"] == "processing"

    complete = client.post(
        f"/ml/anomaly/jobs/{job_id}/complete",
        headers=_worker_headers(),
        json={"result": {"chunks": [{"start": "00:01", "end": "00:02", "confidence": 0.4}]}},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "done"

    final_status = client.get(f"/ml/anomaly/jobs/{job_id}")
    assert final_status.json()["status"] == "done"
    assert final_status.json()["result"]["chunks"][0]["confidence"] == 0.4
