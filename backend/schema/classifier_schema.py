from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field, field_validator


class LSTMCNNPredictRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "sequence": [
                    [0.12, 0.44, 0.0, 0.18, 0.39, 0.0, 0.25, 0.35, 0.0, 0.31, 0.29, 0.0, 0.42, 0.21, 0.0, 0.49, 0.18, 0.0, 0.54, 0.14, 0.0, 0.61, 0.11, 0.0],
                    [0.11, 0.43, 0.0, 0.19, 0.38, 0.0, 0.24, 0.34, 0.0, 0.32, 0.28, 0.0, 0.41, 0.20, 0.0, 0.5, 0.17, 0.0, 0.55, 0.13, 0.0, 0.62, 0.1, 0.0],
                    [0.1, 0.42, 0.0, 0.2, 0.37, 0.0, 0.23, 0.33, 0.0, 0.33, 0.27, 0.0, 0.4, 0.19, 0.0, 0.51, 0.16, 0.0, 0.56, 0.12, 0.0, 0.63, 0.09, 0.0]
                ],
                "return_attention": False,
            }
        }
    }
    sequence: list[list[float]] = Field(
        ...,
        description="Input sequence with shape (T, 24).",
    )
    return_attention: bool = Field(
        default=False,
        description="Include attention weights per window in the response.",
    )

    @field_validator("sequence")
    @classmethod
    def validate_sequence_contract(cls, value: list[list[float]]) -> list[list[float]]:
        if not value:
            raise ValueError("sequence must not be empty")
        if len(value) < 30:
            raise ValueError("sequence length must be at least 30")

        for i, frame in enumerate(value):
            if len(frame) != 24:
                raise ValueError(f"frame {i} must have exactly 24 features")
            for j, feature in enumerate(frame):
                if not math.isfinite(feature):
                    raise ValueError(f"feature at frame {i}, index {j} is NaN or infinite")

        return value


class LSTMCNNPredictResponse(BaseModel):
    predicted_updrs_stage: int
    probabilities: dict[str, float]
    severity: str
    severity_stage: int
    prediction: str
    confidence: float
    lstm_output: list[float]
    logits: list[float]
    n_windows: int
    window_size: int
    stride: int
    model_version: str
    preprocessing_version: str
    checkpoint_path: str
    attention_weights: list[float] | None = None


class LSTMCNNPredictAndUpdateResponse(LSTMCNNPredictResponse):
    patient_id: str
    patient_updated: bool


class APIErrorResponse(BaseModel):
    detail: Any
