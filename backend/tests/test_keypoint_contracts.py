from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes.utils_dtw import extract_features
from schema.keypoint_contracts import build_hand_payload, build_pose_payload


def test_extract_features_accepts_normalized_hand_payload():
    hand_landmarks = [
        {"x": float(i) / 100.0, "y": float(i + 1) / 100.0, "z": float(i + 2) / 100.0}
        for i in range(21)
    ]
    payload = build_hand_payload([hand_landmarks], ["Right"])

    features = extract_features("hands", payload)

    assert isinstance(features, np.ndarray)
    assert features.shape == (42,)


def test_extract_features_accepts_normalized_pose_payload():
    pose_landmarks = [
        {
            "x": float(i) / 100.0,
            "y": float(i + 1) / 100.0,
            "z": float(i + 2) / 100.0,
            "visibility": 0.9,
        }
        for i in range(33)
    ]
    payload = build_pose_payload(pose_landmarks)

    features = extract_features("pose", payload)

    assert isinstance(features, np.ndarray)
    assert features.shape == (66,)
