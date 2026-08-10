from __future__ import annotations

import os
from typing import Any

from ml.anomaly_detection.anomaly_predictor import AnomalyPredictor
from ml.video_embeddings.dummy_embedder import DummyVideoEmbedder


DEFAULT_VIDEO_MODEL = os.getenv("DEFAULT_VIDEO_MODEL", "dummy")
DEFAULT_ANOMALY_MODEL = os.getenv("DEFAULT_ANOMALY_MODEL", "logistic_vjepa2")

VIDEO_EMBEDDERS = {
    "dummy": DummyVideoEmbedder,
}

ANOMALY_CLASSIFIERS = {
    "logistic_vjepa2": AnomalyPredictor,
}

_video_embedder_instances: dict[str, Any] = {}
_anomaly_classifier_instances: dict[str, Any] = {}


def list_video_models() -> list[str]:
    return sorted(VIDEO_EMBEDDERS)


def list_anomaly_models() -> list[str]:
    return sorted(ANOMALY_CLASSIFIERS)


def get_video_embedder(name: str | None = None) -> Any:
    selected = name or DEFAULT_VIDEO_MODEL
    model_class = VIDEO_EMBEDDERS.get(selected)
    if model_class is None:
        raise ValueError(f"Unknown video model: {selected}")
    if selected not in _video_embedder_instances:
        _video_embedder_instances[selected] = model_class()
    return _video_embedder_instances[selected]


def get_anomaly_classifier(name: str | None = None) -> Any:
    selected = name or DEFAULT_ANOMALY_MODEL
    model_class = ANOMALY_CLASSIFIERS.get(selected)
    if model_class is None:
        raise ValueError(f"Unknown anomaly model: {selected}")
    if selected not in _anomaly_classifier_instances:
        _anomaly_classifier_instances[selected] = model_class()
    return _anomaly_classifier_instances[selected]


def selected_video_model_name(name: str | None = None) -> str:
    selected = name or DEFAULT_VIDEO_MODEL
    if selected not in VIDEO_EMBEDDERS:
        raise ValueError(f"Unknown video model: {selected}")
    return selected


def selected_anomaly_model_name(name: str | None = None) -> str:
    selected = name or DEFAULT_ANOMALY_MODEL
    if selected not in ANOMALY_CLASSIFIERS:
        raise ValueError(f"Unknown anomaly model: {selected}")
    return selected
