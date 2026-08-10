from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.export_vjepa2_embedding_from_pickle import export_record


def test_export_record_returns_matching_embedding(tmp_path):
    embedding_path = tmp_path / "embeddings.pkl"
    with embedding_path.open("wb") as file:
        pickle.dump(
            [
                {
                    "filename": "recording.mp4",
                    "view_0_mean_pooled_embedding": [0.1],
                    "view_1_mean_pooled_embedding": [0.2],
                    "view_2_mean_pooled_embedding": [0.3],
                    "view_3_mean_pooled_embedding": [0.4],
                }
            ],
            file,
        )

    record = export_record("/recordings/recording.mp4", embedding_path)

    assert record["filename"] == "recording.mp4"
    assert record["view_0_mean_pooled_embedding"] == [0.1]


def test_export_record_missing_filename_explains_bridge_limitation(tmp_path):
    embedding_path = tmp_path / "embeddings.pkl"
    with embedding_path.open("wb") as file:
        pickle.dump([], file)

    with pytest.raises(ValueError, match="new app recordings require a raw-video VJEPA2 exporter"):
        export_record("recording_missing.mp4", embedding_path)
