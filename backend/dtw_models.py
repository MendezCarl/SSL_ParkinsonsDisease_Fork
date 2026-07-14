"""Strategy pattern for per-model DTW feature extraction and landmark counts.

Replaces the duplicated `if model == "hands"/"pose"/"finger"` ladders that used
to live separately in routes/utils_dtw.py and services/dtw_service.py. Adding
a new test/model type means adding one class here, not touching call sites.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional

import numpy as np

from schema.keypoint_contracts import EXPECTED_LANDMARKS, primary_landmarks


class DtwFeatureModel(ABC):
    name: str
    points: int  # landmark count in the flattened feature vector, or 0 if not a fixed grid

    @abstractmethod
    def extract(self, kp: Dict, use_z: bool = False) -> Optional[np.ndarray]:
        """Build a flattened feature vector from one frame's keypoints, or None if missing."""


class HandsModel(DtwFeatureModel):
    name = "hands"
    points = 21

    def extract(self, kp: Dict, use_z: bool = False) -> Optional[np.ndarray]:
        lm = primary_landmarks(kp, "hand")
        if not lm or len(lm) < EXPECTED_LANDMARKS["hands"]:
            return None

        pts = np.array([[p["x"], p["y"]] for p in lm], dtype=np.float32)  # (21,2)
        ref = pts[0]                                  # wrist
        rel = pts - ref                               # translation-invariant
        scale = np.linalg.norm(pts[9] - ref) + 1e-6    # wrist->middle MCP
        return (rel / scale).reshape(-1)               # (42,)


class PoseModel(DtwFeatureModel):
    name = "pose"
    points = 33

    def extract(self, kp: Dict, use_z: bool = False) -> Optional[np.ndarray]:
        pose = primary_landmarks(kp, "pose")
        if not pose or len(pose) < EXPECTED_LANDMARKS["pose"]:
            return None

        if use_z:
            pts = np.array([[p["x"], p["y"], p.get("z", 0.0)] for p in pose], dtype=np.float32)  # (33,3)
        else:
            pts = np.array([[p["x"], p["y"]] for p in pose], dtype=np.float32)  # (33,2)

        mid_hips = (pts[23] + pts[24]) / 2.0
        rel = pts - mid_hips
        shoulder_w = np.linalg.norm(pts[11] - pts[12]) + 1e-6
        return (rel / shoulder_w).reshape(-1)


class FingerModel(DtwFeatureModel):
    """Finger-only subset of the hands model (thumb tip/MCP, index tip/MCP)."""

    name = "finger"
    points = 0  # not a fixed landmark grid; _infer_points_and_kpp doesn't apply to this model

    _FINGER_INDICES = (3, 4, 7, 8)

    def __init__(self) -> None:
        self._hands = HandsModel()

    def extract(self, kp: Dict, use_z: bool = False) -> Optional[np.ndarray]:
        hand_vec = self._hands.extract(kp, use_z=use_z)
        if hand_vec is None:
            return None
        selected = []
        for idx in self._FINGER_INDICES:
            selected.extend([hand_vec[idx * 2], hand_vec[idx * 2 + 1]])
        return np.array(selected, dtype=np.float32)


_MODELS: Dict[str, DtwFeatureModel] = {
    "hands": HandsModel(),
    "pose": PoseModel(),
    "finger": FingerModel(),
}


def get_dtw_model(name: str | None) -> Optional[DtwFeatureModel]:
    return _MODELS.get((name or "").lower())


def points_for_model(name: str | None) -> Optional[int]:
    model = _MODELS.get((name or "").lower())
    if model is None or not model.points:
        return None
    return model.points
