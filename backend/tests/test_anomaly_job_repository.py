from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from patient_manager import SessionLocal
from repo.anomaly_job_repository import AnomalyJobRepository


def _create_job(repo: AnomalyJobRepository, **overrides):
    defaults = dict(
        job_id=uuid4().hex,
        patient_id="patient-1",
        test_name="finger-tapping",
        session_id=f"session-{uuid4().hex[:8]}",
        recording_file="clip.mp4",
    )
    defaults.update(overrides)
    return repo.create(**defaults)


def test_create_and_get_round_trip():
    with SessionLocal() as session:
        repo = AnomalyJobRepository(session)
        job = _create_job(repo)

        fetched = repo.get(job.job_id)
        assert fetched is not None
        assert fetched.status == "pending"
        assert fetched.patient_id == "patient-1"


def test_get_missing_job_returns_none():
    with SessionLocal() as session:
        repo = AnomalyJobRepository(session)
        assert repo.get("does-not-exist") is None


def test_find_active_for_session_matches_pending_and_processing_only():
    with SessionLocal() as session:
        repo = AnomalyJobRepository(session)
        session_id = f"session-{uuid4().hex[:8]}"
        job = _create_job(repo, session_id=session_id)

        active = repo.find_active_for_session(session_id)
        assert active is not None
        assert active.job_id == job.job_id

        repo.mark_done(job.job_id, "/tmp/report.json")
        assert repo.find_active_for_session(session_id) is None


def test_list_pending_excludes_other_statuses():
    with SessionLocal() as session:
        repo = AnomalyJobRepository(session)
        pending_job = _create_job(repo)
        processing_job = _create_job(repo)
        repo.mark_processing(processing_job.job_id)

        pending_ids = {job.job_id for job in repo.list_pending()}
        assert pending_job.job_id in pending_ids
        assert processing_job.job_id not in pending_ids


def test_mark_processing_then_done_updates_status_and_result_path():
    with SessionLocal() as session:
        repo = AnomalyJobRepository(session)
        job = _create_job(repo)

        repo.mark_processing(job.job_id)
        assert repo.get(job.job_id).status == "processing"

        repo.mark_done(job.job_id, "/tmp/report.json")
        updated = repo.get(job.job_id)
        assert updated.status == "done"
        assert updated.result_path == "/tmp/report.json"
        assert updated.error_message is None


def test_mark_failed_records_error_message():
    with SessionLocal() as session:
        repo = AnomalyJobRepository(session)
        job = _create_job(repo)

        repo.mark_failed(job.job_id, "boom")
        updated = repo.get(job.job_id)
        assert updated.status == "failed"
        assert updated.error_message == "boom"
