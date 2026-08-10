# Video Embedding Models

The whole-video anomaly endpoint is model-swappable through `backend/ml/registry.py`.

## Registered Models

- `dummy`: placeholder embedder that returns `501 Not Implemented`.
- `vjepa2`: external-command adapter for a real V-JEPA2 embedding runtime.

## Migrating Off `dummy`

Install the V-JEPA2 embedding runtime outside this repository, then start the backend with:

```bash
DEFAULT_VIDEO_MODEL=vjepa2
VJEPA2_EMBEDDING_COMMAND='/absolute/path/to/python /Users/carlosmendez/Projects/SmartSystemsLab/SSL_ParkinsonsDisease_Fork/backend/scripts/export_vjepa2_embedding_from_video.py --video {video_path} --model facebook/vjepa2-vitg-fpc64-256 --device cpu'
```

`VJEPA2_EMBEDDING_COMMAND` must print one JSON embedding record to stdout. The command may use these placeholders:

- `{video_path}`: resolved server-side path to a saved recording.
- `{model_dir}`: value of `VJEPA2_MODEL_DIR`.

If `{video_path}` is not present in the command, the backend appends the resolved video path as the final argument.

Optional timeout. The first run can be slow because HuggingFace downloads and caches the model weights:

```bash
VJEPA2_EMBEDDING_TIMEOUT_SECONDS=900
```

The raw-video exporter follows the HuggingFace model card for `facebook/vjepa2-vitg-fpc64-256`: it loads `AutoVideoProcessor`, loads `AutoModel`, samples four 64-frame temporal views with stride 2, calls `model.get_vision_features`, and mean-pools each view into a 1408-dimensional vector.

When the backend requests timestamp review windows, the adapter appends `--review-window-seconds <seconds>` to the command. The raw-video exporter currently supports this and emits additional per-window embeddings in the same process so the model is loaded once. These windows are heuristic review cues only; the anomaly classifier was trained with whole-video labels, not timestamp labels.

Install requirements into the Python used by `VJEPA2_EMBEDDING_COMMAND`:

```bash
python -m pip install -U git+https://github.com/huggingface/transformers opencv-python torch
```

Use a CUDA-capable environment for practical performance when available. CPU or Apple MPS can work for setup/testing but may be slow for the 1B-parameter `vitg` model.

## Expected Command Output

The command must emit JSON with the same schema used to train the anomaly classifier:

```json
{
  "filename": "recording_20260810t082448_a20e658e829b.mp4",
  "view_0_mean_pooled_embedding": [0.1, 0.2],
  "view_1_mean_pooled_embedding": [0.3, 0.4],
  "view_2_mean_pooled_embedding": [0.5, 0.6],
  "view_3_mean_pooled_embedding": [0.7, 0.8]
}
```

The four embedding vectors are concatenated by `AnomalyPredictor`; their combined dimensionality must match the trained anomaly model.

## Legacy Precomputed-Embedding Bridge

The sibling `embeddings-model` repo contains a precomputed VJEPA2 pickle used during anomaly-model training, not a raw-video exporter. For filenames already present in that pickle, this backend includes a lookup exporter:

```bash
DEFAULT_VIDEO_MODEL=vjepa2
VJEPA2_EMBEDDING_COMMAND='/Users/carlosmendez/Projects/SmartSystemsLab/embeddings-model/.venv/bin/python /Users/carlosmendez/Projects/SmartSystemsLab/SSL_ParkinsonsDisease_Fork/backend/scripts/export_vjepa2_embedding_from_pickle.py --video {video_path} --embedding-path /Users/carlosmendez/Projects/SmartSystemsLab/embeddings-model/park_video_benchmarking_data/multi_view_embeddings/VJEPA2/VJEPA2_basic_4views_2stride_Features_All_PARK_Videos.pkl'
```

This bridge does not generate embeddings for brand-new recordings. It only looks up records whose filename already exists in the pickle.

## Path Handling

The `/ml/embed-video` and `/ml/predict-anomaly-from-video` routes accept recording filenames or `recordings/<filename>`. Absolute paths are accepted only when they resolve under the configured recordings directory.

Frontend code should pass only the recording filename.

## Runtime Dependencies

The backend already includes PyTorch/TorchVision pins in `backend/requirements.txt`. Any additional V-JEPA2 package, checkpoint, or preprocessing dependency should be installed with the deployment environment that provides `VJEPA2_EMBEDDING_COMMAND`; large checkpoints should not be committed to this repo.
