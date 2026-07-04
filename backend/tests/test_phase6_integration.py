from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import uuid

import numpy as np
from fastapi.testclient import TestClient

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main
import patient_manager
import routes.websockets as ws_routes
import services.recording_service as recording_service
import services.test_history_service as test_history_service
from main import app
from schema.keypoint_contracts import build_hand_payload


def _unique_suffix() -> str:
    return uuid.uuid4().hex[:8]


def _patient_create_payload(name: str, severity: str = "Stage 2") -> dict:
    return {
        "name": name,
        "age": 67,
        "birthDate": "1959-01-02",
        "height": 172,
        "weight": 71,
        "severity": severity,
        "lab_results_history": [],
        "doctors_notes_history": [],
    }


def _set_temp_history(monkeypatch, history_path: Path):
    def manager_factory():
        return patient_manager.TestHistoryManager(file_path=str(history_path))

    monkeypatch.setattr(test_history_service, "TestHistoryManager", manager_factory)


def test_phase6_system_and_auth_smoke():
    client = TestClient(app)

    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["message"]

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "Swagger UI" in docs.text

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    assert openapi.json()["openapi"]

    token = client.post(
        "/token",
        data={"username": "doctor@hospital.com", "password": "Demo123!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert token.status_code == 200
    access_token = token.json()["access_token"]

    me = client.get("/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "doctor@hospital.com"


def test_phase6_patient_crud_and_csv_import():
    client = TestClient(app)
    created_patient_ids: list[str] = []
    imported_patient_ids: list[str] = []

    try:
        suffix = _unique_suffix()
        create_response = client.post("/patients/", json=_patient_create_payload(f"Phase6 Patient {suffix}"))
        assert create_response.status_code == 200, create_response.text
        patient_id = create_response.json()["patient_id"]
        created_patient_ids.append(patient_id)

        get_response = client.get(f"/patients/{patient_id}")
        assert get_response.status_code == 200
        assert get_response.json()["patient_id"] == patient_id

        update_response = client.put(
            f"/patients/{patient_id}",
            json={"height": 173, "severity": "Stage 3"},
        )
        assert update_response.status_code == 200

        lab_response = client.post(
            f"/patients/{patient_id}/lab-results",
            json={
                "id": f"lab_{suffix}",
                "date": "2026-07-04T10:00:00Z",
                "results": "Stable labs",
                "added_by": "Dr. Phase6",
            },
        )
        assert lab_response.status_code == 200

        note_response = client.post(
            f"/patients/{patient_id}/doctor-notes",
            json={
                "id": f"note_{suffix}",
                "date": "2026-07-04T10:30:00Z",
                "note": "Follow-up completed",
                "added_by": "Dr. Phase6",
            },
        )
        assert note_response.status_code == 200

        list_response = client.get("/patients/")
        assert list_response.status_code == 200
        assert any(patient["patient_id"] == patient_id for patient in list_response.json()["patients"])

        search_response = client.get(f"/patients/search/{suffix}")
        assert search_response.status_code == 200
        assert any(patient["patient_id"] == patient_id for patient in search_response.json()["patients"])

        filter_response = client.post("/patients/filter/", json={"severity": "Stage 3"})
        assert filter_response.status_code == 200
        assert any(patient["patient_id"] == patient_id for patient in filter_response.json()["patients"])

        csv_text = (
            "name,birthDate,height,weight,severity\n"
            f"CSV Phase6 A {suffix},1958-04-12,165,61,Stage 2\n"
            f"CSV Phase6 B {suffix},1957-03-11,170,68,Stage 4\n"
        )
        import_response = client.post(
            "/patients/import/csv",
            files={"file": ("patients.csv", csv_text.encode("utf-8"), "text/csv")},
        )
        assert import_response.status_code == 200, import_response.text
        imported_patient_ids = import_response.json()["imported_patient_ids"]
        assert import_response.json()["success_count"] == 2
        assert len(imported_patient_ids) == 2
    finally:
        for patient_id in created_patient_ids + imported_patient_ids:
            client.delete(f"/patients/{patient_id}")


def test_phase6_upload_video_and_history_flow(monkeypatch, tmp_path):
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    history_path = tmp_path / "test_history.json"
    history_path.write_text("{}")

    monkeypatch.setattr(main, "RECORDINGS_DIR", recordings_dir)
    monkeypatch.setattr(recording_service, "RECORDINGS_DIR", recordings_dir)
    _set_temp_history(monkeypatch, history_path)

    client = TestClient(app)
    patient_id = f"upload-{_unique_suffix()}"

    upload_response = client.post(
        "/upload-video/",
        data={"patient_id": patient_id, "test_name": "finger-tapping"},
        files={"video": ("clip.webm", b"fake-webm-bytes", "video/webm")},
    )
    assert upload_response.status_code == 200, upload_response.text
    body = upload_response.json()
    assert body["success"] is True

    filename = body["filename"]
    assert (recordings_dir / filename).is_file()

    videos_response = client.get(f"/videos/{patient_id}/finger-tapping")
    assert videos_response.status_code == 200
    assert filename in videos_response.json()["videos"]

    tests_response = client.get(f"/patients/{patient_id}/tests")
    assert tests_response.status_code == 200
    tests = tests_response.json()["tests"]
    assert len(tests) == 1
    assert tests[0]["recording_file"] == filename
    assert tests[0]["summary_available"] is True

    recording_response = client.get(f"/recordings/{filename}")
    assert recording_response.status_code == 200


def test_phase6_websocket_recording_flow(monkeypatch, tmp_path):
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    history_path = tmp_path / "test_history.json"
    history_path.write_text("{}")

    monkeypatch.setattr(main, "RECORDINGS_DIR", recordings_dir)
    monkeypatch.setattr(recording_service, "RECORDINGS_DIR", recordings_dir)
    _set_temp_history(monkeypatch, history_path)

    class FakeExtractor:
        def __init__(self, model: str = "hands"):
            self.model = model

        def process(self, frame_bgr):
            hand_landmarks = [
                {"x": float(i) / 100.0, "y": float(i + 1) / 100.0, "z": 0.0}
                for i in range(21)
            ]
            return build_hand_payload([hand_landmarks], ["Right"])

        def close(self):
            return None

    class FakeLiveSession:
        init_error = None

        def push(self, kp):
            return None

        def finalize_and_save(self, meta_sidecar):
            session_id = "20260704T120000_fake1234"
            return {
                "ok": True,
                "session_id": session_id,
                "artifacts": {
                    "dir": str(tmp_path / "dtw_runs" / "finger-tapping" / session_id),
                    "npz": str(tmp_path / "dtw_runs" / "finger-tapping" / session_id / "dtw_artifacts.npz"),
                    "json": str(tmp_path / "dtw_runs" / "finger-tapping" / session_id / "meta.json"),
                    "test_name": "finger-tapping",
                    "session_id": session_id,
                    "created_utc": "20260704T120000",
                },
                "distance": 123.4,
                "avg_step_cost": 0.25,
                "similarity_overall": 88.8,
                "similarity_pos": 77.7,
                "similarity_amp": 66.6,
                "similarity_spd": 55.5,
            }

    def fake_save_frames_to_mp4(frames, *, fps, patient_id, test_name, session_id):
        filename = f"{patient_id}_{test_name}_{session_id}.mp4"
        (recordings_dir / filename).write_bytes(b"fake-mp4")
        return filename

    monkeypatch.setattr(ws_routes, "MPExtractor", FakeExtractor)
    monkeypatch.setattr(ws_routes, "_decode_base64_image", lambda _: np.zeros((4, 4, 3), dtype=np.uint8))
    monkeypatch.setattr(ws_routes.dtw_service, "new_session_id", lambda: "20260704T120000_fake1234")
    monkeypatch.setattr(ws_routes.dtw_service, "create_live_session", lambda *args, **kwargs: FakeLiveSession())
    monkeypatch.setattr(ws_routes, "save_frames_to_mp4", fake_save_frames_to_mp4)

    client = TestClient(app)
    patient_id = f"ws-{_unique_suffix()}"

    with client.websocket_connect("/ws/camera") as websocket:
        websocket.send_json(
            {
                "type": "init",
                "patientId": patient_id,
                "testType": "finger-tapping",
                "testId": "test-route-id",
                "model": "hands",
                "fps": 15,
            }
        )
        init_msg = websocket.receive_json()
        assert init_msg["type"] == "status"
        assert init_msg["status"] == "initialized"
        assert init_msg["sessionId"] == "20260704T120000_fake1234"

        websocket.send_json({"type": "frame", "data": f"data:image/jpeg;base64,{base64.b64encode(b'fake').decode()}"})
        keypoints_msg = websocket.receive_json()
        assert keypoints_msg["type"] == "keypoints"
        assert keypoints_msg["model"] == "hands"
        assert keypoints_msg["detections"][0]["kind"] == "hand"

        websocket.send_json({"type": "end"})
        dtw_saved = websocket.receive_json()
        assert dtw_saved["type"] == "dtw_saved"
        assert dtw_saved["sessionId"] == "20260704T120000_fake1234"

        complete = websocket.receive_json()
        assert complete["type"] == "complete"
        assert complete["summaryAvailable"] is True
        assert complete["dtw"]["session_id"] == "20260704T120000_fake1234"

    tests_response = client.get(f"/patients/{patient_id}/tests")
    assert tests_response.status_code == 200
    tests = tests_response.json()["tests"]
    assert len(tests) == 1
    assert tests[0]["test_id"] == "20260704T120000_fake1234"
    assert tests[0]["dtw"]["session_id"] == "20260704T120000_fake1234"
    assert tests[0]["summary_available"] is True
