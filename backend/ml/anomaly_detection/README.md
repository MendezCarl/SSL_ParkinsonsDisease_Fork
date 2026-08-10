# Whole-Video Anomaly Detection Model

This folder contains an inference-only copy of the best whole-video anomaly model trained from VJEPA2 multi-view embeddings.

The model is binary:

- `normal`
- `anomalous`

It does not predict Parkinson's stage, and it does not process raw video directly. The application must provide the same precomputed embedding record format used during training.

## Files

- `best_whole_video_anomaly_model.joblib`: trained scikit-learn model bundle
- `anomaly_predictor.py`: inference wrapper

The joblib bundle was trained with `scikit-learn==1.9.0`. The backend requirements pin that version so the model can be loaded safely.

## Expected Input

Each embedding record must contain:

```python
{
    "filename": "example.mp4",
    "view_0_mean_pooled_embedding": ...,
    "view_1_mean_pooled_embedding": ...,
    "view_2_mean_pooled_embedding": ...,
    "view_3_mean_pooled_embedding": ...,
}
```

Each embedding can be a torch tensor, list, or numpy array. The four views are concatenated into one `5632`-feature vector.

## Usage

```python
from ml.anomaly_detection import AnomalyPredictor

predictor = AnomalyPredictor()
result = predictor.predict("example.mp4", embedding_records)
print(result)
```

Example output:

```python
{
    "filename": "example.mp4",
    "predicted_label": "anomalous",
    "anomaly_probability": 0.87,
    "model_name": "logistic_regression",
    "model_path": ".../best_whole_video_anomaly_model.joblib",
}
```

## Current Model Notes

The copied model is the best bounded configuration-search result from the embeddings project:

- model: `logistic_regression`
- test balanced accuracy: approximately `0.802`
- test ROC AUC: approximately `0.872`
- participant-level train/test split
