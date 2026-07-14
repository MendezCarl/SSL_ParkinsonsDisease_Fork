from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from patient_manager import SessionLocal
from repo.anomaly_job_repository import AnomalyJobRepository
from repo.sql_models import AnomalyJob
from routes.utils_dtw import resolve_dtw_session_dir
from schema.anomaly_schema import AnomalyReport
from services.dtw_service import dtw_service
from services.recording_service import resolve_recording_path
from services.test_history_service import get_patient_tests as load_patient_tests, persist_session_analysis

logger = logging.getLogger(__name__)

STALE_JOB_TIMEOUT = timedelta(hours=2)


class AnomalyJobNotFound(Exception):
    pass


class AnomalySessionNotFound(Exception):
    pass


def _job_to_dict(job: AnomalyJob) -> Dict[str, Any]:
    return {
        "job_id": job.job_id,
        "patient_id": job.patient_id,
        "test_name": job.test_name,
        "session_id": job.session_id,
        "recording_file": job.recording_file,
        "status": job.status,
        "created_utc": job.created_utc,
    }


def _find_recording_file(patient_id: str, session_id: str) -> Optional[str]:
    for entry in load_patient_tests(patient_id):
        dtw = entry.get("dtw") or {}
        candidate_ids = (dtw.get("session_id"), entry.get("test_id"))
        if session_id in candidate_ids:
            recording_file = entry.get("recording_file")
            if recording_file:
                return recording_file
    return None


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _expire_if_stale(repo: AnomalyJobRepository, job: AnomalyJob) -> AnomalyJob:
    if job.status != "processing":
        return job
    updated = _parse_iso(job.updated_utc)
    if updated is None:
        return job
    if datetime.now(timezone.utc) - updated > STALE_JOB_TIMEOUT:
        expired = repo.mark_failed(job.job_id, "Job timed out waiting for the worker")
        return expired or job
    return job


def create_job(patient_id: str, test_name: str, session_id: str) -> Dict[str, Any]:
    canonical_test_name = dtw_service.normalize_test_name(test_name)

    try:
        session_dir = resolve_dtw_session_dir(canonical_test_name, session_id)
    except ValueError as exc:
        raise AnomalySessionNotFound(str(exc)) from exc
    if not session_dir.is_dir():
        raise AnomalySessionNotFound(f"DTW session '{session_id}' not found for test '{canonical_test_name}'")

    recording_file = _find_recording_file(patient_id, session_id)
    if not recording_file:
        raise AnomalySessionNotFound("No recording found in test history for this session")

    with SessionLocal() as db_session:
        repo = AnomalyJobRepository(db_session)
        existing = repo.find_active_for_session(session_id)
        if existing is not None:
            return {"job_id": existing.job_id, "status": existing.status}

        job = repo.create(
            job_id=uuid4().hex,
            patient_id=patient_id,
            test_name=canonical_test_name,
            session_id=session_id,
            recording_file=recording_file,
        )
        return {"job_id": job.job_id, "status": job.status}


def get_job(job_id: str) -> Dict[str, Any]:
    with SessionLocal() as db_session:
        repo = AnomalyJobRepository(db_session)
        job = repo.get(job_id)
        if job is None:
            raise AnomalyJobNotFound(job_id)

        job = _expire_if_stale(repo, job)

        result = None
        if job.status == "done" and job.result_path:
            result_path = Path(job.result_path)
            if result_path.is_file():
                try:
                    result = json.loads(result_path.read_text())
                except Exception:
                    logger.exception("Failed to read anomaly report at %s", result_path)

        return {
            "job_id": job.job_id,
            "status": job.status,
            "result": result,
            "error": job.error_message,
        }


def list_pending_jobs() -> List[Dict[str, Any]]:
    with SessionLocal() as db_session:
        repo = AnomalyJobRepository(db_session)
        return [_job_to_dict(job) for job in repo.list_pending()]


def get_job_video_path(job_id: str) -> Path:
    with SessionLocal() as db_session:
        repo = AnomalyJobRepository(db_session)
        job = repo.get(job_id)
        if job is None:
            raise AnomalyJobNotFound(job_id)

        video_path = resolve_recording_path(job.recording_file)
        if not video_path.is_file():
            raise FileNotFoundError(f"Recording '{job.recording_file}' missing on disk")

        repo.mark_processing(job_id)
        return video_path


def complete_job(
    job_id: str,
    result: AnomalyReport | None,
    error: str | None,
) -> Dict[str, Any]:
    with SessionLocal() as db_session:
        repo = AnomalyJobRepository(db_session)
        job = repo.get(job_id)
        if job is None:
            raise AnomalyJobNotFound(job_id)

        if job.status in ("done", "failed"):
            return {"job_id": job.job_id, "status": job.status, "already_completed": True}

        if error:
            repo.mark_failed(job_id, error)
            return {"job_id": job_id, "status": "failed", "already_completed": False}

        if result is None:
            repo.mark_failed(job_id, "Worker reported completion with neither a result nor an error")
            return {"job_id": job_id, "status": "failed", "already_completed": False}

        session_dir = resolve_dtw_session_dir(job.test_name, job.session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        result_path = session_dir / "anomaly_report.json"
        report_dict = result.model_dump()
        result_path.write_text(json.dumps(report_dict, indent=2))

        repo.mark_done(job_id, str(result_path))
        persist_session_analysis(job.session_id, anomaly_report=report_dict)

        return {"job_id": job_id, "status": "done", "already_completed": False}
