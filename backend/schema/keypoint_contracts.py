from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict


KeypointModel = Literal["hands", "pose"]
DetectionKind = Literal["hand", "pose"]

_CONTRACT_PATH = Path(__file__).resolve().parents[2] / "shared" / "keypoint-contract.json"
_RAW_CONTRACT = json.loads(_CONTRACT_PATH.read_text())

EXPECTED_LANDMARKS: dict[KeypointModel, int] = {
    "hands": int(_RAW_CONTRACT["models"]["hands"]["expectedLandmarks"]),
    "pose": int(_RAW_CONTRACT["models"]["pose"]["expectedLandmarks"]),
}

HAND_CONNECTION_CHAINS: tuple[tuple[int, ...], ...] = tuple(
    tuple(int(v) for v in chain)
    for chain in _RAW_CONTRACT["models"]["hands"]["connections"]
)

POSE_CONNECTIONS: tuple[tuple[int, int], ...] = tuple(
    (int(pair[0]), int(pair[1]))
    for pair in _RAW_CONTRACT["models"]["pose"]["connections"]
)


class LandmarkPoint(TypedDict, total=False):
    x: float
    y: float
    z: float
    visibility: float


class KeypointDetection(TypedDict):
    kind: DetectionKind
    label: str | None
    landmarks: List[LandmarkPoint]


class KeypointPayload(TypedDict):
    model: KeypointModel
    detections: List[KeypointDetection]


def build_hand_payload(hands: List[List[Dict[str, float]]], labels: List[str | None]) -> KeypointPayload:
    detections: List[KeypointDetection] = []
    for index, hand_landmarks in enumerate(hands):
        detections.append(
            {
                "kind": "hand",
                "label": labels[index] if index < len(labels) else None,
                "landmarks": [
                    {
                        "x": float(point["x"]),
                        "y": float(point["y"]),
                        "z": float(point.get("z", 0.0)),
                    }
                    for point in hand_landmarks
                ],
            }
        )
    return {"model": "hands", "detections": detections}


def build_pose_payload(pose_landmarks: List[Dict[str, float]]) -> KeypointPayload:
    detections: List[KeypointDetection] = []
    if pose_landmarks:
        detections.append(
            {
                "kind": "pose",
                "label": None,
                "landmarks": [
                    {
                        "x": float(point["x"]),
                        "y": float(point["y"]),
                        "z": float(point.get("z", 0.0)),
                        "visibility": float(point.get("visibility", 0.0)),
                    }
                    for point in pose_landmarks
                ],
            }
        )
    return {"model": "pose", "detections": detections}


def primary_landmarks(payload: Dict[str, Any], kind: DetectionKind) -> Optional[List[LandmarkPoint]]:
    detections = payload.get("detections")
    if not isinstance(detections, list):
        return None

    for detection in detections:
        if not isinstance(detection, dict) or detection.get("kind") != kind:
            continue
        landmarks = detection.get("landmarks")
        if isinstance(landmarks, list):
            return landmarks
    return None
