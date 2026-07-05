from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
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


def test_get_series_persists_dtw_snapshot(monkeypatch, tmp_path):
    captured: dict = {}
    monkeypatch.setattr(dtw_service_module, "DTW_BASE", tmp_path)
    monkeypatch.setattr(
        dtw_service_module,
        "persist_session_analysis",
        lambda session_id, **payload: captured.update({"session_id": session_id, **payload}) or True,
    )

    session_dir = tmp_path / "finger-tapping" / "session-123"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "meta.json").write_text(
        json.dumps(
            {
                "testName": "finger-tapping",
                "model": "hands",
                "session_id": "session-123",
                "pos_dtw": 1.5,
                "amp_dtw": 2.5,
                "spd_dtw": 3.5,
                "avg_step_pos": 0.25,
                "similarity_overall": 0.8,
                "similarity_pos": 0.7,
                "similarity_amp": 0.6,
                "similarity_spd": 0.5,
            }
        )
    )
    np.savez(
        session_dir / "dtw_artifacts.npz",
        pos_local_costs=np.array([0.1, 0.2, 0.3]),
        pos_aligned_ref_by_live=np.array([0, 1, 2]),
        amp_local_costs=np.array([0.2, 0.3, 0.4]),
        amp_aligned_ref_by_live=np.array([0, 1, 2]),
        spd_local_costs=np.array([0.3, 0.4, 0.5]),
        spd_aligned_ref_by_live=np.array([0, 1, 2]),
    )

    client = TestClient(app)
    response = client.get("/dtw/sessions/finger-tapping/session-123/series")

    assert response.status_code == 200
    assert captured["session_id"] == "session-123"
    assert captured["dtw_metrics"]["distance_pos"] == 1.5
    assert captured["dtw_metrics"]["similarity_overall"] == 0.8
