from __future__ import annotations

import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import services.dtw_service as dtw_service_module
from main import app


def _write_session(
    base: Path,
    *,
    test_name: str,
    folder_name: str,
    canonical_session_id: str,
    patient_id: str,
    created_utc: str,
) -> None:
    session_dir = base / test_name / folder_name
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "meta.json").write_text(
        json.dumps(
            {
                "testName": test_name,
                "model": "hands",
                "created_utc": created_utc,
                "session_id": canonical_session_id,
                "live_len": 10,
                "ref_len": 12,
                "patientId": patient_id,
                "pos_dtw": 1.5,
                "similarity_overall": 0.8,
            }
        )
    )


def test_list_sessions_can_be_scoped_to_patient(monkeypatch, tmp_path):
    monkeypatch.setattr(dtw_service_module, "DTW_BASE", tmp_path)
    _write_session(
        tmp_path,
        test_name="finger-tapping",
        folder_name="folder-a",
        canonical_session_id="canonical-a",
        patient_id="patient-a",
        created_utc="2026-07-04T10:00:00Z",
    )
    _write_session(
        tmp_path,
        test_name="finger-tapping",
        folder_name="folder-b",
        canonical_session_id="canonical-b",
        patient_id="patient-b",
        created_utc="2026-07-04T11:00:00Z",
    )

    client = TestClient(app)
    response = client.get("/dtw/sessions/finger-tapping", params={"patient_id": "patient-a"})

    assert response.status_code == 200
    body = response.json()
    assert [entry["session_id"] for entry in body] == ["canonical-a"]


def test_lookup_session_can_resolve_canonical_id_with_patient_scope(monkeypatch, tmp_path):
    monkeypatch.setattr(dtw_service_module, "DTW_BASE", tmp_path)
    _write_session(
        tmp_path,
        test_name="finger-tapping",
        folder_name="legacy-folder-name",
        canonical_session_id="canonical-session-id",
        patient_id="patient-a",
        created_utc="2026-07-04T10:00:00Z",
    )

    client = TestClient(app)

    success = client.get(
        "/dtw/sessions/lookup/canonical-session-id",
        params={"patient_id": "patient-a"},
    )
    assert success.status_code == 200
    assert success.json() == {
        "testName": "finger-tapping",
        "sessionId": "canonical-session-id",
    }

    wrong_patient = client.get(
        "/dtw/sessions/lookup/canonical-session-id",
        params={"patient_id": "patient-b"},
    )
    assert wrong_patient.status_code == 404
