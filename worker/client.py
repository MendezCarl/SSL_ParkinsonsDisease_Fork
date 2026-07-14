from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from config import WorkerConfig


class AnomalyApiClient:
    """Thin wrapper around the backend's /ml/anomaly worker-facing endpoints."""

    def __init__(self, config: WorkerConfig) -> None:
        self._config = config
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {config.worker_token}"

    def list_pending(self) -> List[Dict[str, Any]]:
        response = self._session.get(
            f"{self._config.api_base_url}/ml/anomaly/jobs",
            params={"status": "pending"},
            timeout=self._config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def fetch_video(self, job_id: str, dest_path: Path) -> Path:
        response = self._session.get(
            f"{self._config.api_base_url}/ml/anomaly/jobs/{job_id}/video",
            timeout=self._config.request_timeout_seconds,
            stream=True,
        )
        response.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        return dest_path

    def post_complete(
        self,
        job_id: str,
        *,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if result is not None:
            body["result"] = result
        if error is not None:
            body["error"] = error

        response = self._session.post(
            f"{self._config.api_base_url}/ml/anomaly/jobs/{job_id}/complete",
            json=body,
            timeout=self._config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
