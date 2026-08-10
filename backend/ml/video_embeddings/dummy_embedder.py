from __future__ import annotations

from pathlib import Path
from typing import Any


class DummyVideoEmbedder:
    model_name = "dummy"

    def embed_video(self, video_path: Path) -> dict[str, Any]:
        raise NotImplementedError(
            "The dummy video embedder is a placeholder. Use predict-anomaly-from-embedding "
            "until a real video embedding model is registered."
        )
