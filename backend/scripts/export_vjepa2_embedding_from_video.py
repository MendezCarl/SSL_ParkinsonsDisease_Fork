from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


FEATURE_KEYS = (
    "view_0_mean_pooled_embedding",
    "view_1_mean_pooled_embedding",
    "view_2_mean_pooled_embedding",
    "view_3_mean_pooled_embedding",
)


def _default_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _sample_indices(
    total_frames: int,
    frames_per_view: int,
    stride: int,
    view_count: int,
    *,
    start_frame: int = 0,
    end_frame: int | None = None,
) -> list[np.ndarray]:
    if total_frames <= 0:
        raise ValueError("Video contains no readable frames")
    end_frame = total_frames - 1 if end_frame is None else min(end_frame, total_frames - 1)
    start_frame = max(0, min(start_frame, end_frame))
    window_frames = end_frame - start_frame + 1
    if window_frames <= frames_per_view:
        base = np.linspace(start_frame, end_frame, frames_per_view).round().astype(int)
        return [base for _ in range(view_count)]

    span = (frames_per_view - 1) * stride + 1
    max_start = max(end_frame - span + 1, start_frame)
    starts = np.linspace(start_frame, max_start, view_count).round().astype(int)
    return [np.clip(start + np.arange(frames_per_view) * stride, start_frame, end_frame) for start in starts]


def _window_ranges(total_frames: int, fps: float, window_seconds: float) -> list[tuple[float, float, int, int]]:
    if fps <= 0:
        raise ValueError("Video FPS is unavailable; cannot create timestamp review windows")
    duration = total_frames / fps
    ranges = []
    start_sec = 0.0
    while start_sec < duration:
        end_sec = min(start_sec + window_seconds, duration)
        start_frame = int(round(start_sec * fps))
        end_frame = max(start_frame, int(round(end_sec * fps)) - 1)
        ranges.append((start_sec, end_sec, start_frame, end_frame))
        start_sec = end_sec
    return ranges


def _read_video_view(video_path: Path, indices: np.ndarray) -> Any:
    import cv2
    import torch

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    frames = []
    try:
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                if frames:
                    frame = frames[-1]
                else:
                    raise ValueError(f"Could not read frame {int(index)} from {video_path}")
            else:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(frame)
    finally:
        capture.release()

    # HuggingFace's V-JEPA2 processor accepts T x C x H x W video tensors.
    return torch.from_numpy(np.stack(frames)).permute(0, 3, 1, 2)


def _mean_pool_features(features: Any) -> list[float]:
    import torch

    tensor = features.last_hidden_state if hasattr(features, "last_hidden_state") else features
    if not isinstance(tensor, torch.Tensor):
        raise TypeError("V-JEPA2 model returned an unsupported feature type")
    tensor = tensor.detach().float().cpu()
    if tensor.ndim == 1:
        pooled = tensor
    else:
        if tensor.shape[0] == 1:
            tensor = tensor[0]
        pooled = tensor.reshape(-1, tensor.shape[-1]).mean(dim=0)
    return pooled.numpy().astype(np.float32).tolist()


def export_record(
    video_path: Path,
    *,
    model_name: str,
    frames_per_view: int,
    stride: int,
    view_count: int,
    device: str,
    expected_dim: int | None,
    review_window_seconds: float | None = None,
) -> dict[str, Any]:
    import cv2
    import torch
    from transformers import AutoModel, AutoVideoProcessor

    video_path = video_path.expanduser().resolve(strict=True)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    capture.release()

    processor = AutoVideoProcessor.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name).to(device).eval()

    def embed_indices(indices_by_view: list[np.ndarray]) -> dict[str, Any]:
        embedding: dict[str, Any] = {}
        for key, indices in zip(FEATURE_KEYS[:view_count], indices_by_view):
            video = _read_video_view(video_path, indices)
            inputs = processor(video, return_tensors="pt").to(device)
            with torch.no_grad():
                features = model.get_vision_features(**inputs)
            vector = _mean_pool_features(features)
            if expected_dim is not None and len(vector) != expected_dim:
                raise ValueError(
                    f"Expected {expected_dim} V-JEPA2 features for {key}, got {len(vector)}. "
                    "Use the same backbone/dimensionality used to train the anomaly classifier."
                )
            embedding[key] = vector
        return embedding

    record: dict[str, Any] = {
        "filename": video_path.name,
        **embed_indices(_sample_indices(total_frames, frames_per_view, stride, view_count)),
    }
    if review_window_seconds is not None and review_window_seconds > 0:
        windows = []
        for start_sec, end_sec, start_frame, end_frame in _window_ranges(total_frames, fps, review_window_seconds):
            window_record = {
                "start_sec": start_sec,
                "end_sec": end_sec,
                **embed_indices(
                    _sample_indices(
                        total_frames,
                        frames_per_view,
                        stride,
                        view_count,
                        start_frame=start_frame,
                        end_frame=end_frame,
                    )
                ),
            }
            windows.append(window_record)
        record["review_window_embeddings"] = windows

    missing = [key for key in FEATURE_KEYS if key not in record]
    if missing:
        raise ValueError(f"Exporter did not produce all required VJEPA2 views: {missing}")
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate VJEPA2 mean-pooled embeddings from a raw video.")
    parser.add_argument("video_path", nargs="?", help="Video path to embed.")
    parser.add_argument("--video", dest="video_arg", help="Video path to embed.")
    parser.add_argument("--model", default="facebook/vjepa2-vitg-fpc64-256", help="HuggingFace V-JEPA2 model id.")
    parser.add_argument("--frames-per-view", type=int, default=64)
    parser.add_argument("--stride", type=int, default=2)
    parser.add_argument("--view-count", type=int, default=4)
    parser.add_argument("--review-window-seconds", type=float, default=None)
    parser.add_argument("--device", default=None, help="cuda, mps, or cpu. Defaults to the best available device.")
    parser.add_argument("--expected-dim", type=int, default=1408, help="Expected vector length per view; set 0 to disable.")
    parser.add_argument("--output", default="-", choices=["-"], help="Only stdout output is supported.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    video_path = args.video_arg or args.video_path
    if not video_path:
        raise SystemExit("Provide a video path via positional argument or --video")
    expected_dim = None if args.expected_dim == 0 else args.expected_dim
    record = export_record(
        Path(video_path),
        model_name=args.model,
        frames_per_view=args.frames_per_view,
        stride=args.stride,
        view_count=args.view_count,
        device=args.device or _default_device(),
        expected_dim=expected_dim,
        review_window_seconds=args.review_window_seconds,
    )
    print(json.dumps(record))


if __name__ == "__main__":
    try:
        main()
    except (ImportError, ModuleNotFoundError) as exc:
        print(
            "Missing V-JEPA2 exporter dependency. Install the latest HuggingFace transformers, "
            "torch, and opencv-python in the Python environment used by VJEPA2_EMBEDDING_COMMAND. "
            f"Original error: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
