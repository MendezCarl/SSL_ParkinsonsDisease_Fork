from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.dtw_migration_service import dtw_migration_service


def test_migration_renames_folders_and_backfills_history(tmp_path):
    dtw_base = tmp_path / "dtw_runs"
    session_dir = dtw_base / "finger-tapping" / "legacy-folder"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "meta.json").write_text(
        json.dumps(
            {
                "testName": "finger-tapping",
                "model": "hands",
                "created_utc": "20260421T182005",
                "session_id": "20260421T182005_b81c945e",
                "patientId": "patient-1",
                "fps": 15,
                "pos_dtw": 123.4,
                "avg_step_pos": 0.25,
                "similarity_overall": 87.6,
            }
        )
    )

    history_path = tmp_path / "test_history.json"
    history_path.write_text(
        json.dumps(
            {
                "patient-1": [
                    {
                        "test_name": "finger-tapping",
                        "date": "2026-04-21T18:20:05.522433+00:00",
                        "recording_file": "ws_recording_2026-04-21_14-20-05_x.mp4",
                        "frame_count": 177,
                    }
                ]
            }
        )
    )

    report = dtw_migration_service.migrate_historical_data(
        dtw_base=dtw_base,
        test_history_path=history_path,
        write_changes=True,
    )

    assert report["renamed_folders"] == 1
    assert report["backfilled_entries"] == 1
    assert (dtw_base / "finger-tapping" / "20260421T182005_b81c945e").is_dir()

    history = json.loads(history_path.read_text())
    entry = history["patient-1"][0]
    assert entry["test_id"] == "20260421T182005_b81c945e"
    assert entry["summary_available"] is True
    assert entry["fps"] == 15
    assert entry["dtw"]["session_id"] == "20260421T182005_b81c945e"
    assert entry["dtw"]["artifacts"]["dir"].endswith("/finger-tapping/20260421T182005_b81c945e")


def test_migration_skips_ambiguous_time_matches(tmp_path):
    dtw_base = tmp_path / "dtw_runs"
    for suffix in ("a", "b"):
        session_dir = dtw_base / "finger-tapping" / f"folder-{suffix}"
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "meta.json").write_text(
            json.dumps(
                {
                    "testName": "finger-tapping",
                    "model": "hands",
                    "created_utc": "20260421T182005",
                    "session_id": f"20260421T182005_{suffix}",
                    "patientId": "patient-1",
                }
            )
        )

    history_path = tmp_path / "test_history.json"
    history_path.write_text(
        json.dumps(
            {
                "patient-1": [
                    {
                        "test_name": "finger-tapping",
                        "date": "2026-04-21T18:20:05+00:00",
                        "recording_file": "ws_recording_2026-04-21_14-20-05_x.mp4",
                    }
                ]
            }
        )
    )

    report = dtw_migration_service.migrate_historical_data(
        dtw_base=dtw_base,
        test_history_path=history_path,
        write_changes=True,
    )

    assert report["skipped_ambiguous_entries"] == 1
    history = json.loads(history_path.read_text())
    assert "test_id" not in history["patient-1"][0]
