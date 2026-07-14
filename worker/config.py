from __future__ import annotations

import os


class WorkerConfig:
    def __init__(self) -> None:
        self.api_base_url = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
        self.worker_token = os.environ.get("ANOMALY_WORKER_TOKEN")
        self.poll_interval_seconds = float(os.environ.get("POLL_INTERVAL_SECONDS", "10"))
        self.request_timeout_seconds = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30"))

    def validate(self) -> None:
        if not self.worker_token:
            raise RuntimeError(
                "ANOMALY_WORKER_TOKEN is not set. It must match the backend's "
                "ANOMALY_WORKER_TOKEN environment variable."
            )


def load_config() -> WorkerConfig:
    return WorkerConfig()
