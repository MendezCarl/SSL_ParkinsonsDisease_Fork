from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from patient_manager import TestHistoryManager


def build_completed_test_history_entry(
    *,
    test_name: str,
    session_id: str,
    recording_file: str,
    frame_count: int,
    fps: int | float | None,
    similarity: float | None,
    distance: float | None,
    avg_step_cost: float | None,
    model: str | None,
    artifacts: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "test_id": session_id,
        "test_name": test_name,
        "date": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "recording_file": recording_file,
        "frame_count": frame_count,
        "fps": int(fps) if fps is not None else None,
        "summary_available": True,
        "model": model,
        "dtw": {
            "session_id": session_id,
            "distance": distance,
            "avg_step_cost": avg_step_cost,
            "similarity": similarity,
            "artifacts": artifacts or {},
        },
        "indicator": {
            "color": "success",
            "label": "Completed",
            "description": "Recording captured successfully.",
        },
    }


def append_patient_test(patient_id: str, entry: Dict[str, Any]) -> None:
    TestHistoryManager().add_patient_test(patient_id or "unknown", entry)


def get_patient_tests(patient_id: str) -> list[dict]:
    return TestHistoryManager().get_patient_tests(patient_id)


def build_uploaded_video_test_history_entry(
    *,
    test_name: str,
    session_id: str,
    recording_file: str,
) -> Dict[str, Any]:
    return {
        "test_id": session_id,
        "test_name": test_name,
        "date": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "recording_file": recording_file,
        "summary_available": True,
        "indicator": {
            "color": "success",
            "label": "Completed",
            "description": "Video uploaded successfully.",
        },
    }
