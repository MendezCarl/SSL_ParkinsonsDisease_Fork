from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from main import run_once
from processor import AnomalyProcessor


class FakeClient:
    def __init__(self, jobs: List[Dict[str, Any]]):
        self._jobs = jobs
        self.fetched: List[str] = []
        self.completed: List[Dict[str, Any]] = []

    def list_pending(self):
        return self._jobs

    def fetch_video(self, job_id: str, dest_path: Path) -> Path:
        self.fetched.append(job_id)
        dest_path.write_bytes(b"fake-video")
        return dest_path

    def post_complete(self, job_id: str, *, result=None, error=None):
        self.completed.append({"job_id": job_id, "result": result, "error": error})
        return {"job_id": job_id, "status": "done" if result else "failed"}


class FakeProcessor(AnomalyProcessor):
    def process(self, video_path: Path):
        assert video_path.exists()
        return {"chunks": [], "model_version": "fake", "generated_at": "now"}


class RaisingProcessor(AnomalyProcessor):
    def process(self, video_path: Path):
        raise RuntimeError("model exploded")


def test_run_once_processes_all_pending_jobs_and_cleans_up(tmp_path):
    jobs = [{"job_id": "job-1"}, {"job_id": "job-2"}]
    client = FakeClient(jobs)
    processor = FakeProcessor()

    count = run_once(client, processor, tmp_path)

    assert count == 2
    assert client.fetched == ["job-1", "job-2"]
    assert [c["job_id"] for c in client.completed] == ["job-1", "job-2"]
    assert all(c["result"] is not None for c in client.completed)
    # temp video files must be cleaned up after each job
    assert list(tmp_path.iterdir()) == []


def test_run_once_reports_processor_failure_back_to_api(tmp_path):
    client = FakeClient([{"job_id": "job-err"}])
    processor = RaisingProcessor()

    run_once(client, processor, tmp_path)

    assert client.completed == [{"job_id": "job-err", "result": None, "error": "model exploded"}]
