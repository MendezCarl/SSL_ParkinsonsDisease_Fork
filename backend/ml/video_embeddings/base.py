from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class VideoEmbedder(Protocol):
    model_name: str

    def embed_video(self, video_path: Path) -> dict[str, Any]:
        ...
