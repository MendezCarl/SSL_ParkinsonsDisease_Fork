from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dtw_models import FingerModel, HandsModel, PoseModel, get_dtw_model, points_for_model
from routes.utils_dtw import extract_features
from schema.keypoint_contracts import build_hand_payload, build_pose_payload


def _hand_payload():
    hand_landmarks = [
        {"x": float(i) / 100.0, "y": float(i + 1) / 100.0, "z": float(i + 2) / 100.0}
        for i in range(21)
    ]
    return build_hand_payload([hand_landmarks], ["Right"])


def test_get_dtw_model_returns_expected_strategy_types():
    assert isinstance(get_dtw_model("hands"), HandsModel)
    assert isinstance(get_dtw_model("pose"), PoseModel)
    assert isinstance(get_dtw_model("finger"), FingerModel)
    assert isinstance(get_dtw_model("HANDS"), HandsModel)  # case-insensitive
    assert get_dtw_model("unknown-model") is None


def test_points_for_model_matches_landmark_counts():
    assert points_for_model("hands") == 21
    assert points_for_model("pose") == 33
    assert points_for_model("finger") is None  # not a fixed landmark grid
    assert points_for_model("unknown-model") is None


def test_extract_features_finger_model_is_subset_of_hands_model():
    payload = _hand_payload()

    hand_features = extract_features("hands", payload)
    finger_features = extract_features("finger", payload)

    assert isinstance(finger_features, np.ndarray)
    assert finger_features.shape == (8,)  # 4 landmarks * (x, y)
    # Finger model reuses the hands model's normalized coordinates verbatim.
    assert finger_features[0] == hand_features[3 * 2]
    assert finger_features[1] == hand_features[3 * 2 + 1]


def test_extract_features_unknown_model_returns_none():
    assert extract_features("not-a-real-model", _hand_payload()) is None
