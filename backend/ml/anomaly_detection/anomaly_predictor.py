from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np


MODEL_PATH = Path(__file__).resolve().parent / "best_whole_video_anomaly_model.joblib"
FEATURE_KEYS = (
    "view_0_mean_pooled_embedding",
    "view_1_mean_pooled_embedding",
    "view_2_mean_pooled_embedding",
    "view_3_mean_pooled_embedding",
)
NORMAL_LABEL = 0
ANOMALY_LABEL = 1
LABEL_NAMES = {NORMAL_LABEL: "normal", ANOMALY_LABEL: "anomalous"}


def _embedding_to_numpy(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value, dtype=np.float32).reshape(-1)


def build_feature_vector(record: dict[str, Any], feature_keys: Iterable[str] = FEATURE_KEYS) -> np.ndarray:
    missing_keys = [key for key in feature_keys if key not in record]
    if missing_keys:
        raise KeyError(f"Embedding record is missing keys: {missing_keys}")
    return np.concatenate([_embedding_to_numpy(record[key]) for key in feature_keys]).astype(np.float32)


def find_embedding_record(filename: str, embedding_records: Any) -> dict[str, Any]:
    if isinstance(embedding_records, dict):
        record = embedding_records.get(filename)
        if record is None and embedding_records.get("filename") == filename:
            record = embedding_records
        if record is not None:
            return record

    for record in embedding_records:
        if record.get("filename") == filename:
            return record
    raise ValueError(f"No embedding record found for filename: {filename}")


class AnomalyPredictor:
    """Inference wrapper for the whole-video anomaly classifier.

    This model expects precomputed VJEPA2 multi-view embedding records, not raw video.
    """

    def __init__(self, model_path: str | Path = MODEL_PATH) -> None:
        self.model_path = Path(model_path)
        self._bundle: dict[str, Any] | None = None

    def _load_bundle(self) -> dict[str, Any]:
        if self._bundle is None:
            if not self.model_path.exists():
                raise FileNotFoundError(f"Anomaly model not found at {self.model_path}")
            if self.model_path.suffix == ".npz":
                data = np.load(self.model_path, allow_pickle=False)
                self._bundle = {
                    "portable": True,
                    "model_name": str(data["model_name"]),
                    "feature_keys": tuple(str(value) for value in data["feature_keys"]),
                    "classes": data["classes"].astype(int),
                    "scaler_mean": data["scaler_mean"].astype(np.float32),
                    "scaler_scale": data["scaler_scale"].astype(np.float32),
                    "coef": data["coef"].astype(np.float32),
                    "intercept": data["intercept"].astype(np.float32),
                }
                return self._bundle

            loaded = joblib.load(self.model_path)
            if not isinstance(loaded, dict) or "model" not in loaded:
                raise ValueError("Expected a joblib bundle containing a 'model' entry.")
            self._bundle = loaded
        return self._bundle

    @staticmethod
    def _portable_predict_proba(bundle: dict[str, Any], X: np.ndarray) -> tuple[int, float]:
        X_scaled = (X - bundle["scaler_mean"]) / bundle["scaler_scale"]
        logits = X_scaled @ bundle["coef"].T + bundle["intercept"]
        classes = bundle["classes"]

        if logits.shape[1] == 1:
            anomaly_probability = float(1.0 / (1.0 + np.exp(-logits[0, 0])))
            predicted_value = ANOMALY_LABEL if anomaly_probability >= 0.5 else NORMAL_LABEL
            return predicted_value, anomaly_probability

        shifted_logits = logits - logits.max(axis=1, keepdims=True)
        probabilities = np.exp(shifted_logits) / np.exp(shifted_logits).sum(axis=1, keepdims=True)
        predicted_value = int(classes[int(np.argmax(probabilities[0]))])
        anomaly_index = list(classes).index(ANOMALY_LABEL)
        return predicted_value, float(probabilities[0, anomaly_index])

    def predict_from_record(self, record: dict[str, Any]) -> dict[str, Any]:
        bundle = self._load_bundle()
        model_name = bundle.get("model_name", "unknown")
        feature_keys = bundle.get("feature_keys", FEATURE_KEYS)

        X = build_feature_vector(record, feature_keys=feature_keys).reshape(1, -1)

        if bundle.get("portable"):
            predicted_value, anomaly_probability = self._portable_predict_proba(bundle, X)
            result: dict[str, Any] = {
                "filename": record.get("filename"),
                "predicted_label": LABEL_NAMES[predicted_value],
                "anomaly_probability": anomaly_probability,
                "model_name": model_name,
                "model_path": str(self.model_path),
            }
            return result

        model = bundle["model"]
        raw_prediction = model.predict(X)[0]
        if model_name == "isolation_forest":
            predicted_value = ANOMALY_LABEL if raw_prediction == -1 else NORMAL_LABEL
        else:
            predicted_value = int(raw_prediction)

        result: dict[str, Any] = {
            "filename": record.get("filename"),
            "predicted_label": LABEL_NAMES[predicted_value],
            "model_name": model_name,
            "model_path": str(self.model_path),
        }

        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(X)
            classes = list(getattr(model, "classes_", [NORMAL_LABEL, ANOMALY_LABEL]))
            if ANOMALY_LABEL in classes:
                result["anomaly_probability"] = float(probabilities[:, classes.index(ANOMALY_LABEL)][0])
        elif hasattr(model, "decision_function"):
            score = float(np.asarray(model.decision_function(X)).reshape(-1)[0])
            result["anomaly_score"] = -score if model_name == "isolation_forest" else score

        return result

    def predict(self, filename: str, embedding_records: Any) -> dict[str, Any]:
        record = find_embedding_record(filename, embedding_records)
        result = self.predict_from_record(record)
        result["filename"] = filename
        return result


def predict_video_anomaly(
    filename: str,
    embedding_records: Any,
    model_path: str | Path = MODEL_PATH,
) -> dict[str, Any]:
    return AnomalyPredictor(model_path=model_path).predict(filename, embedding_records)
