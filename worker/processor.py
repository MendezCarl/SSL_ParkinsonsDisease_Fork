from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class AnomalyProcessor(ABC):
    """The one seam the real model plugs into.

    Swapping in VideoMAE + the trained autoencoder later means writing one
    new class implementing `process()` and pointing main.py at it -- nothing
    else in the worker (or the backend) needs to change.
    """

    @abstractmethod
    def process(self, video_path: Path) -> Dict[str, Any]:
        """Return an AnomalyReport-shaped dict: {chunks, model_version, generated_at}."""


class StubAnomalyProcessor(AnomalyProcessor):
    """Placeholder used until the real model exists.

    Lets the full poll -> fetch -> process -> post loop run end-to-end today.
    """

    def __init__(self, simulated_latency_seconds: float = 0.0) -> None:
        self._simulated_latency_seconds = simulated_latency_seconds

    def process(self, video_path: Path) -> Dict[str, Any]:
        if self._simulated_latency_seconds:
            time.sleep(self._simulated_latency_seconds)
        return {
            "chunks": [],
            "model_version": "stub-v0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
