from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, List
from uuid import uuid4

import numpy as np

from storage_paths import RECORDINGS_DIR


_ALLOWED_RECORDING_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
_RECORDING_FILENAME_RE = re.compile(r"^[a-z0-9_-]+\.(mp4|mov|webm|avi|mkv)$")


def _cv2():
    try:
        import cv2
        return cv2
    except Exception as exc:
        raise RuntimeError("OpenCV not available. Install opencv-python-headless.") from exc


def _safe_token(value: str | None, fallback: str) -> str:
    raw = (value or "").strip().lower()
    sanitized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw)
    sanitized = sanitized.strip("-")
    return sanitized or fallback


def _validate_recording_filename(filename: str) -> str:
    candidate_name = Path(filename).name.lower()
    if candidate_name != filename.lower():
        raise ValueError("Invalid recording filename")
    if not _RECORDING_FILENAME_RE.fullmatch(candidate_name):
        raise ValueError("Invalid recording filename")
    return candidate_name


def _safe_recording_path(filename: str) -> Path:
    candidate_name = _validate_recording_filename(filename)

    base_resolved = RECORDINGS_DIR.resolve(strict=False)
    candidate = (RECORDINGS_DIR / candidate_name).resolve(strict=False)
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError("Invalid recording path") from exc
    return candidate


def build_recording_filename(
    *,
    patient_id: str | None,
    test_name: str | None,
    session_id: str | None = None,
    extension: str,
) -> str:
    # File paths should not depend on user-controlled patient/test identifiers.
    # Record linkage lives in test history and DTW metadata, not the filename itself.
    _ = patient_id, test_name, session_id
    timestamp_token = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    unique_token = uuid4().hex[:12]
    ext = (extension if extension.startswith(".") else f".{extension}").lower()
    if ext not in _ALLOWED_RECORDING_EXTENSIONS:
        raise ValueError(f"Unsupported recording extension: {ext}")
    return _validate_recording_filename(f"recording_{timestamp_token}_{unique_token}{ext}")


def save_frames_to_mp4(
    frames: List[np.ndarray],
    *,
    fps: float = 30.0,
    patient_id: str | None,
    test_name: str | None,
    session_id: str | None,
) -> str:
    if not frames:
        raise ValueError("No frames to save.")

    cv2 = _cv2()
    h, w = frames[0].shape[:2]
    filename = build_recording_filename(
        patient_id=patient_id,
        test_name=test_name,
        session_id=session_id or uuid4().hex,
        extension=".mp4",
    )
    path = _safe_recording_path(filename)

    for fourcc_str in ("avc1", "H264", "mp4v"):
        fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
        writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
        if writer.isOpened():
            break
    else:
        raise RuntimeError("Could not open VideoWriter with any codec")

    for frame in frames:
        writer.write(frame)
    writer.release()
    return filename


def _pick_upload_extension(filename: str | None, content_type: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in _ALLOWED_RECORDING_EXTENSIONS:
        return suffix

    content_map = {
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/webm": ".webm",
        "video/x-msvideo": ".avi",
    }
    return content_map.get((content_type or "").lower(), ".mp4")


def save_uploaded_video(
    *,
    patient_id: str,
    test_name: str,
    upload_file: BinaryIO,
    original_filename: str | None,
    content_type: str | None,
    session_id: str | None = None,
) -> str:
    extension = _pick_upload_extension(original_filename, content_type)
    filename = build_recording_filename(
        patient_id=patient_id,
        test_name=test_name,
        session_id=session_id,
        extension=extension,
    )
    filepath = _safe_recording_path(filename)
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(upload_file, buffer)
    return filename
