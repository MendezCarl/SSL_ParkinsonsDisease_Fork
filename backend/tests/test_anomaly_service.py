from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from uuid import uuid4

import pytest

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import routes.utils_dtw as utils_dtw
import services.anomaly_service as anomaly_service
import services.recording_service as recording_service
from patient_manager import SessionLocal
from repo.anomaly_job_repository import AnomalyJobRepository
from schema.anomaly_schema import AnomalyChunk, AnomalyReport


@pytest.fixture
def dtw_base(tmp_path, monkeypatch):
    base = tmp_path / "dtw_runs"
    base.mkdir()
    monkeypatch.setattr(utils_dtw, "DTW_BASE", base)
    return base


def _make_repo_job(**overrides) -> str:
    with SessionLocal() as session:
        repo = AnomalyJobRepository(session)
        job = repo.create(
            job_id=overrides.pop("job_id", uuid4().hex),
            patient_id=overrides.pop("patient_id", "patient-1"),
            test_name=overrides.pop("test_name", "finger-tapping"),
            session_id=overrides.pop("session_id", f"session-{uuid4().hex[:8]}"),
            recording_file=overrides.pop("recording_file", "clip.mp4"),
        )
        return job.job_id


def test_create_job_raises_when_session_missing(dtw_base):
    with pytest.raises(anomaly_service.AnomalySessionNotFound):
        anomaly_service.create_job("patient-1", "finger-tapping", "no-such-session")


def test_create_job_raises_when_no_recording_found(dtw_base, monkeypatch):
    session_id = "session-abc123"
    (dtw_base / "finger-tapping" / session_id).mkdir(parents=True)
    monkeypatch.setattr(anomaly_service, "_find_recording_file", lambda *_: None)

    with pytest.raises(anomaly_service.AnomalySessionNotFound):
        anomaly_service.create_job("patient-1", "finger-tapping", session_id)


def test_create_job_dedupes_active_job_for_same_session(dtw_base, monkeypatch):
    session_id = "session-dedup01"
    (dtw_base / "finger-tapping" / session_id).mkdir(parents=True)
    monkeypatch.setattr(anomaly_service, "_find_recording_file", lambda *_: "clip.mp4")

    first = anomaly_service.create_job("patient-1", "finger-tapping", session_id)
    second = anomaly_service.create_job("patient-1", "finger-tapping", session_id)

    assert first["job_id"] == second["job_id"]


def test_get_job_missing_raises():
    with pytest.raises(anomaly_service.AnomalyJobNotFound):
        anomaly_service.get_job("does-not-exist")


def test_get_job_reads_result_when_done(tmp_path):
    job_id = _make_repo_job()
    report_path = tmp_path / "anomaly_report.json"
    report_payload = {"chunks": [{"start": "00:01", "end": "00:02", "confidence": 0.5}]}
    report_path.write_text(json.dumps(report_payload))

    with SessionLocal() as session:
        AnomalyJobRepository(session).mark_done(job_id, str(report_path))

    result = anomaly_service.get_job(job_id)
    assert result["status"] == "done"
    assert result["result"] == report_payload
    assert result["error"] is None


def test_get_job_expires_stale_processing_job():
    job_id = _make_repo_job()
    with SessionLocal() as session:
        repo = AnomalyJobRepository(session)
        repo.mark_processing(job_id)
        job = repo.get(job_id)
        job.updated_utc = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        session.commit()

    result = anomaly_service.get_job(job_id)
    assert result["status"] == "failed"
    assert "timed out" in result["error"].lower()


def test_get_job_video_path_marks_processing(tmp_path, monkeypatch):
    monkeypatch.setattr(recording_service, "RECORDINGS_DIR", tmp_path)
    (tmp_path / "clip.mp4").write_bytes(b"fake-mp4")
    job_id = _make_repo_job(recording_file="clip.mp4")

    video_path = anomaly_service.get_job_video_path(job_id)

    assert video_path == tmp_path / "clip.mp4"
    with SessionLocal() as session:
        assert AnomalyJobRepository(session).get(job_id).status == "processing"


def test_get_job_video_path_raises_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(recording_service, "RECORDINGS_DIR", tmp_path)
    job_id = _make_repo_job(recording_file="missing.mp4")

    with pytest.raises(FileNotFoundError):
        anomaly_service.get_job_video_path(job_id)


def test_complete_job_writes_report_and_marks_done(dtw_base):
    session_id = "session-complete01"
    job_id = _make_repo_job(session_id=session_id, test_name="finger-tapping")

    report = AnomalyReport(
        chunks=[AnomalyChunk(start="00:15", end="00:19", confidence=0.92)],
        model_version="stub-v0",
        generated_at="2026-07-11T00:00:00Z",
    )

    result = anomaly_service.complete_job(job_id, report, None)

    assert result["status"] == "done"
    report_path = dtw_base / "finger-tapping" / session_id / "anomaly_report.json"
    assert report_path.is_file()
    saved = json.loads(report_path.read_text())
    assert saved["chunks"][0]["confidence"] == 0.92

    with SessionLocal() as session:
        job = AnomalyJobRepository(session).get(job_id)
        assert job.status == "done"
        assert job.result_path == str(report_path)


def test_complete_job_marks_failed_on_worker_error(dtw_base):
    job_id = _make_repo_job(test_name="finger-tapping")
    result = anomaly_service.complete_job(job_id, None, "worker blew up")

    assert result["status"] == "failed"
    with SessionLocal() as session:
        assert AnomalyJobRepository(session).get(job_id).error_message == "worker blew up"


def test_complete_job_marks_failed_when_neither_result_nor_error(dtw_base):
    job_id = _make_repo_job(test_name="finger-tapping")
    result = anomaly_service.complete_job(job_id, None, None)
    assert result["status"] == "failed"


def test_complete_job_is_idempotent(dtw_base):
    job_id = _make_repo_job(test_name="finger-tapping")
    anomaly_service.complete_job(job_id, None, "first error")
    second = anomaly_service.complete_job(
        job_id,
        AnomalyReport(chunks=[], model_version=None, generated_at=None),
        None,
    )

    assert second["already_completed"] is True
    assert second["status"] == "failed"  # unchanged from the first completion


def test_list_pending_jobs_returns_plain_dicts():
    job_id = _make_repo_job()
    pending = anomaly_service.list_pending_jobs()
    assert any(job["job_id"] == job_id for job in pending)
