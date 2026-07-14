# repo/anomaly_job_repository.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from repo.sql_models import AnomalyJob

ACTIVE_STATUSES = ("pending", "processing")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnomalyJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        job_id: str,
        patient_id: str,
        test_name: str,
        session_id: str,
        recording_file: str,
    ) -> AnomalyJob:
        now = _now_iso()
        job = AnomalyJob(
            job_id=job_id,
            patient_id=patient_id,
            test_name=test_name,
            session_id=session_id,
            recording_file=recording_file,
            status="pending",
            created_utc=now,
            updated_utc=now,
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def get(self, job_id: str) -> Optional[AnomalyJob]:
        return self.session.get(AnomalyJob, job_id)

    def find_active_for_session(self, session_id: str) -> Optional[AnomalyJob]:
        return (
            self.session.execute(
                select(AnomalyJob).where(
                    AnomalyJob.session_id == session_id,
                    AnomalyJob.status.in_(ACTIVE_STATUSES),
                )
            )
            .scalars()
            .first()
        )

    def list_pending(self) -> List[AnomalyJob]:
        return (
            self.session.execute(
                select(AnomalyJob).where(AnomalyJob.status == "pending").order_by(AnomalyJob.created_utc.asc())
            )
            .scalars()
            .all()
        )

    def mark_processing(self, job_id: str) -> Optional[AnomalyJob]:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = "processing"
        job.updated_utc = _now_iso()
        self.session.commit()
        return job

    def mark_done(self, job_id: str, result_path: str) -> Optional[AnomalyJob]:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = "done"
        job.result_path = result_path
        job.error_message = None
        job.updated_utc = _now_iso()
        self.session.commit()
        return job

    def mark_failed(self, job_id: str, error_message: str) -> Optional[AnomalyJob]:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = "failed"
        job.error_message = error_message
        job.updated_utc = _now_iso()
        self.session.commit()
        return job
