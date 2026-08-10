from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any


FEATURE_KEYS = (
    "view_0_mean_pooled_embedding",
    "view_1_mean_pooled_embedding",
    "view_2_mean_pooled_embedding",
    "view_3_mean_pooled_embedding",
)


DEFAULT_EMBEDDING_PATH = Path(
    "/Users/carlosmendez/Projects/SmartSystemsLab/embeddings-model/"
    "park_video_benchmarking_data/multi_view_embeddings/VJEPA2/"
    "VJEPA2_basic_4views_2stride_Features_All_PARK_Videos.pkl"
)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "detach"):
        value = value.detach().cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def _record_filename(record: dict[str, Any]) -> str | None:
    filename = record.get("filename") or record.get("Filename")
    return str(filename) if filename else None


def _find_record(records: Any, filename: str) -> dict[str, Any]:
    candidates = {filename, Path(filename).name}
    if isinstance(records, dict):
        for candidate in candidates:
            record = records.get(candidate)
            if isinstance(record, dict):
                return record
        if _record_filename(records) in candidates:
            return records

    for record in records:
        if isinstance(record, dict) and _record_filename(record) in candidates:
            return record

    raise ValueError(
        "No precomputed VJEPA2 embedding record found for filename "
        f"'{filename}'. The configured pickle bridge only works for videos that "
        "already exist in the embeddings pickle; new app recordings require a "
        "raw-video VJEPA2 exporter."
    )


def export_record(video_path: str, embedding_path: Path) -> dict[str, Any]:
    with embedding_path.open("rb") as file:
        records = pickle.load(file)

    filename = Path(video_path).name
    record = _find_record(records, filename)
    missing = [key for key in FEATURE_KEYS if key not in record]
    if missing:
        raise KeyError(f"VJEPA2 embedding record is missing keys: {missing}")

    return {
        "filename": _record_filename(record) or filename,
        **{key: _jsonable(record[key]) for key in FEATURE_KEYS},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit a VJEPA2 embedding record from the precomputed PARK embeddings pickle."
    )
    parser.add_argument("video_path", nargs="?", help="Video path or filename to look up by basename.")
    parser.add_argument("--video", dest="video_arg", help="Video path or filename to look up by basename.")
    parser.add_argument("--embedding-path", default=str(DEFAULT_EMBEDDING_PATH), help="Path to the VJEPA2 embeddings pickle.")
    parser.add_argument("--model-dir", default=None, help="Accepted for adapter compatibility; unused by this lookup exporter.")
    parser.add_argument("--review-window-seconds", type=float, default=None, help="Accepted for adapter compatibility; unused by this lookup exporter.")
    parser.add_argument("--output", default="-", choices=["-"], help="Only stdout output is supported.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    video_path = args.video_arg or args.video_path
    if not video_path:
        raise SystemExit("Provide a video path via positional argument or --video")
    embedding_path = Path(args.embedding_path).expanduser().resolve(strict=True)
    print(json.dumps(export_record(video_path, embedding_path)))


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
