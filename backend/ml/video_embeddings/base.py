from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class VideoEmbedder(Protocol):
    model_name: str

    def embed_video(self, video_path: Path, *, review_window_seconds: float | None = None) -> dict[str, Any]:
        ...
