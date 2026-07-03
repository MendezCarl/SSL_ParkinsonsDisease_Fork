from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch

from ml.mil_classifier import MILClassifier


WINDOW = 30
STRIDE = 10
N_FEATURES = 24
N_CLASSES = 4


class LSTMCNNInferenceService:
    def __init__(self) -> None:
        base_dir = Path(__file__).resolve().parents[1]
        self.checkpoint_path = (
            base_dir.parents[1] / "Park-LSTM-Autoencoder" / "checkpoints" / "lstm_mil_classifier.pt"
        )
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model: MILClassifier | None = None

    @staticmethod
    def _to_severity(predicted_updrs_stage: int) -> tuple[str, int]:
        # Existing app uses Stage 1..5 labels. Classifier predicts UPDRS 0..3.
        stage_num = min(max(predicted_updrs_stage + 1, 1), 5)
        return f"Stage {stage_num}", stage_num

    def _validate_sequence(self, sequence: list[list[float]] | np.ndarray) -> np.ndarray:
        seq = np.asarray(sequence, dtype=np.float32)

        if seq.ndim != 2:
            raise ValueError("Input sequence must be 2D with shape (T, 24).")
        if seq.shape[1] != N_FEATURES:
            raise ValueError(f"Feature dimension must be exactly {N_FEATURES}.")
        if seq.shape[0] < WINDOW:
            raise ValueError(f"Sequence length must be at least {WINDOW} frames.")
        if not np.isfinite(seq).all():
            raise ValueError("Input sequence contains NaN or infinite values.")

        return seq

    def _window_sequence(self, seq: np.ndarray) -> np.ndarray:
        windows = []
        t = seq.shape[0]
        for start in range(0, t - WINDOW + 1, STRIDE):
            windows.append(seq[start : start + WINDOW])

        if not windows:
            raise ValueError("No windows were generated from the sequence.")

        return np.stack(windows).astype(np.float32)

    def _load_model(self) -> MILClassifier:
        if self.model is not None:
            return self.model

        if not self.checkpoint_path.exists():
            raise FileNotFoundError(
                f"Locked MIL checkpoint not found at {self.checkpoint_path}. "
                "Place the training checkpoint at that path to run inference."
            )

        checkpoint = torch.load(self.checkpoint_path, map_location=self.device)
        state_dict = checkpoint["model_state_dict"] if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint else checkpoint

        model = MILClassifier(input_size=N_FEATURES, embed_dim=64, n_classes=N_CLASSES).to(self.device)
        model.load_state_dict(state_dict)
        model.eval()
        self.model = model
        return model

    def predict(self, sequence: list[list[float]] | np.ndarray, return_attention: bool = False) -> dict[str, Any]:
        seq = self._validate_sequence(sequence)
        windows = self._window_sequence(seq)  # (n_windows, 30, 24)

        bag = torch.from_numpy(windows).unsqueeze(0).to(self.device)  # (1, n_windows, 30, 24)
        model = self._load_model()

        with torch.no_grad():
            logits, attention = model(bag)
            logits_np = logits.squeeze(0).cpu().numpy()
            probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()

        pred = int(np.argmax(probs))
        severity, severity_stage = self._to_severity(pred)
        confidence = float(np.max(probs))
        response: dict[str, Any] = {
            "predicted_updrs_stage": pred,
            "probabilities": {str(i): float(probs[i]) for i in range(N_CLASSES)},
            # Backward-compatible fields for systems expecting severity-like outputs.
            "severity": severity,
            "severity_stage": severity_stage,
            "prediction": severity,
            "confidence": confidence,
            "lstm_output": [float(x) for x in probs.tolist()],
            "logits": [float(x) for x in logits_np.tolist()],
            "n_windows": int(windows.shape[0]),
            "window_size": WINDOW,
            "stride": STRIDE,
            "model_version": "lstm_cnn_mil_v1",
            "preprocessing_version": "window30_stride10_features24",
            "checkpoint_path": str(self.checkpoint_path),
        }

        if return_attention:
            response["attention_weights"] = attention.cpu().numpy().astype(float).tolist()

        return response


inference_service = LSTMCNNInferenceService()
