from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any


FEATURE_KEYS = (
    "view_0_mean_pooled_embedding",
    "view_1_mean_pooled_embedding",
    "view_2_mean_pooled_embedding",
    "view_3_mean_pooled_embedding",
)


class VJEPA2VideoEmbedder:
    """Adapter for an installed V-JEPA2 embedding runtime.

    The backend owns routing, persistence, and validation. The heavy model runtime is
    configured separately through VJEPA2_EMBEDDING_COMMAND so checkpoints stay out of
    the web app and can be swapped without changing API code.
    """

    model_name = "vjepa2"

    def __init__(
        self,
        command_template: str | None = None,
        model_dir: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.command_template = command_template or os.getenv("VJEPA2_EMBEDDING_COMMAND")
        self.model_dir = model_dir or os.getenv("VJEPA2_MODEL_DIR", "")
        self.timeout_seconds = timeout_seconds or int(os.getenv("VJEPA2_EMBEDDING_TIMEOUT_SECONDS", "300"))

    def _build_command(self, video_path: Path, *, review_window_seconds: float | None = None) -> list[str]:
        if not self.command_template:
            raise NotImplementedError(
                "VJEPA2 video embedding is registered but not configured. Set "
                "VJEPA2_EMBEDDING_COMMAND and DEFAULT_VIDEO_MODEL=vjepa2."
            )

        if "{video_path}" in self.command_template or "{model_dir}" in self.command_template:
            command = self.command_template.format(
                video_path=shlex.quote(str(video_path)),
                model_dir=shlex.quote(self.model_dir),
                review_window_seconds="" if review_window_seconds is None else str(review_window_seconds),
            )
            parts = shlex.split(command)
        else:
            parts = [*shlex.split(self.command_template), str(video_path)]

        if review_window_seconds is not None and review_window_seconds > 0 and "{review_window_seconds}" not in self.command_template:
            parts.extend(["--review-window-seconds", str(review_window_seconds)])
        return parts

    @staticmethod
    def _coerce_record(payload: Any, video_path: Path) -> dict[str, Any]:
        if isinstance(payload, list):
            if not payload or not isinstance(payload[0], dict):
                raise ValueError("VJEPA2 embedding command returned an invalid JSON list")
            record = payload[0]
        elif isinstance(payload, dict):
            metadata: dict[str, Any] = {}
            if isinstance(payload.get("review_window_embeddings"), list):
                metadata["review_window_embeddings"] = payload["review_window_embeddings"]
            if isinstance(payload.get("embedding"), dict):
                record = payload["embedding"]
            elif isinstance(payload.get("record"), dict):
                record = payload["record"]
            else:
                record = payload
        else:
            raise ValueError("VJEPA2 embedding command must return a JSON object or list")

        missing = [key for key in FEATURE_KEYS if key not in record]
        if missing:
            raise KeyError(f"VJEPA2 embedding output is missing keys: {missing}")

        return {"filename": record.get("filename") or video_path.name, **record, **metadata}

    def embed_video(self, video_path: Path, *, review_window_seconds: float | None = None) -> dict[str, Any]:
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        command = self._build_command(video_path, review_window_seconds=review_window_seconds)
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            raise RuntimeError(f"VJEPA2 embedding command failed: {detail}")

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("VJEPA2 embedding command did not return valid JSON") from exc

        return self._coerce_record(payload, video_path)
