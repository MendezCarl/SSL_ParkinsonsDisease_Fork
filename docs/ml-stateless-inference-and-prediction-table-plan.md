# Stateless ML Inference And Dedicated Prediction Table Plan

## Goal

Add a stateless, swappable ML inference layer under `/ml` in the FastAPI backend.

The system should support:

- Current whole-video anomaly classifier: VJEPA2 embeddings -> `normal` / `anomalous`
- Future anomaly classifiers
- Current/future video embedding models: raw or saved video -> embeddings
- Future raw-video end-to-end models
- Persistent ML prediction records in a dedicated database table linked to the existing test history records

The implementation should not hard-code the app to the current LogisticRegression anomaly classifier or one video embedding model.

## Current Repo Context

Target repo:

```text
/Users/carlosmendez/Projects/SmartSystemsLab/SSL_ParkinsonsDisease_Fork
```

Relevant current files:

- `backend/main.py`
- `backend/routes/classifier.py`
- `backend/routes/dtw_rest.py`
- `backend/services/lstm_cnn_inference.py`
- `backend/services/test_history_service.py`
- `backend/repo/db.py`
- `backend/repo/sql_models.py`
- `backend/repo/patient_repository.py`
- `backend/ml/anomaly_detection/anomaly_predictor.py`
- `backend/ml/anomaly_detection/best_whole_video_anomaly_model.joblib`
- `frontend/src/pages/VideoSummary.tsx`
- `frontend/src/services/api.ts`

Current copied anomaly package:

```text
backend/ml/anomaly_detection/
  __init__.py
  anomaly_predictor.py
  best_whole_video_anomaly_model.joblib
  best_whole_video_anomaly_model_portable.npz
  README.md
```

The copied anomaly model currently expects precomputed embedding records with:

```python
{
    "filename": "example.mp4",
    "view_0_mean_pooled_embedding": ...,
    "view_1_mean_pooled_embedding": ...,
    "view_2_mean_pooled_embedding": ...,
    "view_3_mean_pooled_embedding": ...,
}
```

It does not process raw video directly.

## Existing ML Situation

The app already has a different ML path for UPDRS/stage-like prediction:

```text
camera video -> keypoints -> DTW/session artifacts -> LSTM-MIL inference -> frontend Video Summary
```

The new anomaly model is separate:

```text
saved/raw video -> video embedding model -> embedding record -> anomaly classifier -> normal/anomalous
```

Do not mix anomaly prediction with the existing UPDRS/stage prediction. Keep it as a separate ML capability.

The anomaly classifier is binary only:

- `normal`
- `anomalous`

It does not predict Parkinson's stage and does not use `PD_Stage`.

## Existing Database Context

The backend uses SQLite with SQLAlchemy.

Important DB files:

- `backend/repo/db.py`
- `backend/repo/sql_models.py`
- `backend/services/test_history_service.py`
- `backend/services/dtw_migration_service.py`

Current `TestResult` model in `backend/repo/sql_models.py` includes:

- `test_id`: integer primary key
- `patient_id`: foreign key to `patients.patient_id`
- `test_name`
- `test_date`
- `recording_file`
- `frame_count`
- `session_id`
- `fps`
- `summary_available`
- `dtw`: JSON
- `extra`: JSON, currently used for `analysis`

Current test-history service stores DTW and stage-model analysis inside `TestResult.extra["analysis"]`.

New ML predictions should be stored in a dedicated SQL table instead of being stored only inside `extra.analysis`.

The current database already has the right anchor point for ML predictions:

```text
patients.patient_id
  -> testresults.patient_id
  -> ml_predictions.test_result_id
```

`testresults` should remain the clinical/test event record. `ml_predictions` should become the audit trail for model outputs generated for that test event.

This is a good fit because:

- One test can have multiple ML predictions over time
- Different model versions can be compared on the same test/session
- Rerunning a newer model does not overwrite older prediction records
- Prediction history is directly queryable
- Test history can still expose the latest prediction for simple frontend display

Important ID distinction:

- `TestResult.test_id` is the integer database primary key
- `TestResult.session_id` is the DTW/session identifier used by recording/session flows
- Frontend routes may use a session ID or other test identifier, not necessarily the DB `test_id`

Therefore, backend services should resolve frontend-friendly identifiers to the DB row before inserting predictions.

Preferred persisted flow:

```text
API receives patient_id + session_id
-> ml_prediction_service resolves matching TestResult
-> insert ml_predictions row with test_result_id FK
```

The frontend should not need to know `testresults.test_id` for the first implementation. It can pass `patient_id + session_id`, and the backend can resolve the correct row.

## Required DB Design

Add a dedicated `ml_predictions` SQLAlchemy table.

This table should reference existing test history through `testresults.test_id` and also keep denormalized lookup fields for fast lookup by patient/session.

`test_result_id` should be required for persisted predictions in the first implementation. If unlinked/ad-hoc predictions are needed later, add that deliberately as a separate feature instead of making the core audit trail nullable from the start.

Recommended SQLAlchemy model:

```python
class MLPrediction(Base):
    __tablename__ = "ml_predictions"
    __table_args__ = (
        Index("ix_ml_predictions_test_result", "test_result_id"),
        Index("ix_ml_predictions_patient_created", "patient_id", "created_at"),
        Index("ix_ml_predictions_session", "session_id"),
        Index("ix_ml_predictions_type", "prediction_type"),
    )

    prediction_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    test_result_id: Mapped[int] = mapped_column(
        ForeignKey("testresults.test_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[str | None] = mapped_column(String(64), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    test_name: Mapped[str | None] = mapped_column(String(100))

    prediction_type: Mapped[str] = mapped_column(String(64), nullable=False)
    video_model: Mapped[str | None] = mapped_column(String(128))
    classifier_model: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(128))
    model_artifact_path: Mapped[str | None] = mapped_column(String(512))

    predicted_label: Mapped[str] = mapped_column(String(64), nullable=False)
    probability: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)

    input_video_path: Mapped[str | None] = mapped_column(String(512))
    input_filename: Mapped[str | None] = mapped_column(String(512))
    embedding_artifact_path: Mapped[str | None] = mapped_column(String(512))

    request_json: Mapped[dict | None] = mapped_column(JSON)
    response_json: Mapped[dict | None] = mapped_column(JSON)
    error_json: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    test_result: Mapped["TestResult"] = relationship("TestResult", back_populates="ml_predictions")
```

Also add the relationship to `TestResult`:

```python
ml_predictions: Mapped[list["MLPrediction"]] = relationship(
    "MLPrediction",
    back_populates="test_result",
    cascade="all, delete-orphan",
    passive_deletes=True,
)
```

Add `Float` to SQLAlchemy imports in `sql_models.py`.

## DB Persistence Rules

All new ML prediction persistence should go through a service layer, not directly through routes.

Create:

```text
backend/services/ml_prediction_service.py
```

Responsibilities:

- Resolve an existing `TestResult` by `test_result_id`, or by `(patient_id, session_id)`, or by `(patient_id, test_name, recording_file)` as needed
- Insert a new `MLPrediction` row
- Return the created prediction row or serialized response
- Provide query helpers for frontend/test-history screens

Required persistence behavior:

- If `persist=false`, return prediction only and do not write DB
- If `persist=true`, write one `ml_predictions` row
- If `persist=true` and `test_result_id` is supplied, validate that the row exists before inserting
- If `persist=true` and only `patient_id + session_id` are supplied, resolve the matching `TestResult` server-side before inserting
- If `persist=true` and the test/session cannot be resolved, return `400`
- Do not support unlinked persisted predictions in the first implementation

Recommended unique/deduplication policy for first implementation:

- Do not enforce uniqueness initially
- Allow multiple predictions per test/session so model comparisons and reruns can be audited
- Always return the latest prediction in summary views unless the frontend explicitly requests prediction history

## Test History Integration

The existing test history response should be extended to include the latest ML predictions for each `TestResult`.

In `test_history_service.py`, update serialization so `_serialize_test_result(row)` can include a summary under `analysis`, for example:

```json
{
  "analysis": {
    "dtw_metrics": {...},
    "ml_prediction": {...},
    "anomaly_prediction": {
      "prediction_id": 123,
      "predicted_label": "anomalous",
      "anomaly_probability": 0.87,
      "video_model": "vjepa2",
      "classifier_model": "logistic_vjepa2",
      "created_at": "2026-08-10T..."
    }
  }
}
```

This keeps frontend display simple while preserving the dedicated source of truth in `ml_predictions`.

Recommended service helper:

```python
def latest_prediction_for_test_result(
    session: Session,
    test_result_id: int,
    prediction_type: str,
) -> MLPrediction | None:
    ...
```

For `get_patient_tests(patient_id)`, use efficient loading or a small query per row initially. If performance becomes an issue, optimize later with a grouped latest-prediction query.

## Migration Strategy

Check whether the repo uses migrations. If not, it appears to rely on SQLAlchemy metadata/create-all style setup in existing scripts/services.

Implementation options:

1. If the app already calls `Base.metadata.create_all(engine)`, adding the model may be enough for fresh DBs.
2. For existing local DBs, add a small migration script:

```text
backend/scripts/migrate_ml_predictions.py
```

The migration should:

- Create `ml_predictions` if it does not exist
- Be safe to rerun
- Not drop or rewrite existing tables
- Preserve existing `testresults.extra.analysis`

Add tests for migration idempotency if practical.

## Stateless ML Architecture

Create two independent model interfaces:

```text
VideoEmbeddingModel
video path -> embedding record

AnomalyClassifier
embedding record -> anomaly prediction
```

Recommended backend layout:

```text
backend/
  ml/
    registry.py
    schemas.py
    anomaly_detection/
      anomaly_predictor.py
      best_whole_video_anomaly_model.joblib
    video_embeddings/
      __init__.py
      base.py
      dummy_embedder.py
      vjepa2_embedder.py
  routes/
    ml.py
  services/
    ml_prediction_service.py
```

## Statelessness Rules

Do:

- Treat each request as self-contained
- Allow request to specify `video_model` and `anomaly_model`
- Use environment/default config only for defaults
- Load models lazily from disk
- Cache model instances in process memory only for performance
- Return model metadata in responses
- Persist prediction outputs to `ml_predictions` only when requested or when endpoint policy requires it

Do not:

- Store selected model in patient/session state
- Store request-specific mutable data inside model objects
- Hard-code endpoint names to one model
- Make the anomaly classifier depend directly on a specific video embedding class
- Store raw embeddings in SQLite by default

## Model Registry

Add a registry to map model names to implementations.

Example:

```python
VIDEO_EMBEDDERS = {
    "dummy": DummyVideoEmbedder,
    "vjepa2": VJEPA2VideoEmbedder,
}

ANOMALY_CLASSIFIERS = {
    "logistic_vjepa2": AnomalyPredictor,
}
```

Use defaults from env vars or constants:

```text
DEFAULT_VIDEO_MODEL=dummy
DEFAULT_ANOMALY_MODEL=logistic_vjepa2
```

The registry should expose:

- list available video models
- list available anomaly models
- get selected video embedder
- get selected anomaly classifier

## Video Embedder Interface

Create `backend/ml/video_embeddings/base.py`:

```python
from pathlib import Path
from typing import Protocol, Any

class VideoEmbedder(Protocol):
    model_name: str

    def embed_video(self, video_path: Path) -> dict[str, Any]:
        ...
```

First implementation:

- `DummyVideoEmbedder`
- It should raise `NotImplementedError` or return a clear `501` through the endpoint
- This lets the API and Swagger docs exist now

Future implementation:

- `VJEPA2VideoEmbedder`
- It should output the four required mean-pooled embedding keys:
  - `view_0_mean_pooled_embedding`
  - `view_1_mean_pooled_embedding`
  - `view_2_mean_pooled_embedding`
  - `view_3_mean_pooled_embedding`

## Anomaly Classifier Interface

Current `AnomalyPredictor` already supports:

```python
predict_from_record(record)
predict(filename, embedding_records)
```

Wrap it behind a common protocol if useful:

```python
class AnomalyClassifier(Protocol):
    model_name: str

    def predict_from_embedding(self, embedding_record: dict[str, Any]) -> dict[str, Any]:
        ...
```

Response should include:

- filename
- predicted_label: `normal` or `anomalous`
- anomaly_probability if available
- anomaly_score if available
- anomaly_model
- model_version/model_path if useful

## Pydantic Schemas

Create `backend/ml/schemas.py` or `backend/schema/ml_schema.py`.

Recommended schemas:

```python
class AvailableModelsResponse(BaseModel):
    video_models: list[str]
    anomaly_models: list[str]
    default_video_model: str
    default_anomaly_model: str
```

```python
class EmbeddingRequest(BaseModel):
    video_path: str
    video_model: str | None = None
```

```python
class EmbeddingResponse(BaseModel):
    filename: str
    video_model: str
    embedding_dim: int | None = None
    feature_keys: list[str]
```

```python
class AnomalyEmbeddingRequest(BaseModel):
    filename: str
    embedding: dict[str, Any]
    anomaly_model: str | None = None
    persist: bool = False
    patient_id: str | None = None
    test_result_id: int | None = None
    test_name: str | None = None
    session_id: str | None = None
```

```python
class AnomalyPredictionResponse(BaseModel):
    filename: str | None = None
    predicted_label: Literal["normal", "anomalous"]
    anomaly_probability: float | None = None
    anomaly_score: float | None = None
    anomaly_model: str
    video_model: str | None = None
    prediction_id: int | None = None
    test_result_id: int | None = None
    persisted: bool = False
```

```python
class VideoAnomalyRequest(BaseModel):
    video_path: str
    video_model: str | None = None
    anomaly_model: str | None = None
    persist: bool = False
    patient_id: str | None = None
    test_result_id: int | None = None
    test_name: str | None = None
    session_id: str | None = None
```

## New ML Endpoints

Create `backend/routes/ml.py`.

All new endpoints should live under `/ml`.

Recommended endpoints:

```text
GET /ml/models
```

Returns available video/anomaly models and defaults.

```text
POST /ml/embed-video
```

Input:

- `video_path`
- optional `video_model`

Output:

- embedding metadata or embedding payload, depending on implementation

For now, if VJEPA2 is not implemented, return `501 Not Implemented` with a clear message.

```text
POST /ml/predict-anomaly-from-embedding
```

Input:

- filename
- embedding record
- optional anomaly model
- optional persistence fields

Output:

- anomaly prediction
- `prediction_id` if persisted

This endpoint should work immediately with the copied model.

```text
POST /ml/predict-anomaly-from-video
```

Input:

- video path
- optional video model
- optional anomaly model
- optional persistence fields

Flow:

```text
video path -> selected video embedder -> selected anomaly classifier -> prediction -> optional ml_predictions insert
```

For now, if selected video embedder is `dummy`/not implemented, return `501`.

```text
GET /ml/predictions/test/{test_result_id}
```

Returns all ML predictions linked to a specific `TestResult`.

```text
GET /ml/predictions/session/{session_id}
```

Returns all ML predictions linked to a DTW/session ID.

```text
GET /ml/predictions/patient/{patient_id}
```

Returns recent ML predictions for a patient.

## Swagger/OpenAPI

FastAPI Swagger docs update automatically if:

- router is included in `backend/main.py`
- endpoints use `response_model`
- Pydantic request/response schemas are used
- route decorators include `summary` and `description`

Example:

```python
@router.post(
    "/predict-anomaly-from-video",
    response_model=AnomalyPredictionResponse,
    summary="Predict whole-video anomaly from a saved video",
    description=(
        "Runs the selected video embedding model, then runs the selected "
        "whole-video anomaly classifier. This predicts normal/anomalous only. "
        "If persist=true, the prediction is stored in ml_predictions and linked "
        "to an existing test history row."
    ),
)
```

Swagger URL:

```text
http://localhost:8000/docs
```

## Backend Main Integration

In `backend/main.py`, include the new router:

```python
from routes import ml

app.include_router(ml.router, prefix="/ml", tags=["ML"])
```

If the current app convention places API routes under `/api`, follow that existing convention while still grouping all new ML paths under the ML router.

## Frontend Integration

Add API client functions in `frontend/src/services/api.ts`:

```ts
getMlModels()
predictAnomalyFromEmbedding(payload)
predictAnomalyFromVideo(payload)
getMlPredictionsForTest(testResultId)
getMlPredictionsForSession(sessionId)
getMlPredictionsForPatient(patientId)
```

Add UI in `VideoSummary.tsx`:

- New "Whole-Video Anomaly" card
- Show latest persisted anomaly prediction from test history if available
- Show:
  - predicted label
  - probability/score
  - video model
  - anomaly model
  - prediction timestamp
  - persisted status
- Add a "Run Anomaly Analysis" button later when a real video embedder exists

For first release:

- Display saved anomaly prediction if backend returns one through test history or `/ml/predictions/...`
- Do not show a run button unless `/ml/models` reports a real implemented video model

## Video Embedding Model Strategy

The current anomaly classifier needs VJEPA2-style embeddings.

Short-term:

- Implement endpoint scaffolding
- Add dummy embedder returning `501`
- Support anomaly-from-embedding immediately
- Persist predictions from embedding requests into `ml_predictions`

Medium-term:

- Add actual `VJEPA2VideoEmbedder`
- Make it produce the same four mean-pooled embedding keys
- Run it post-recording, not real-time

Recommended flow:

```text
user records video
backend saves video
frontend/video summary requests anomaly analysis
backend runs selected video embedder
backend runs selected anomaly classifier
backend writes ml_predictions row
frontend displays result
```

Avoid true real-time embeddings at first because VJEPA2 inference is heavy and operationally more complex.

## Security

Validate video paths carefully:

- Do not allow arbitrary filesystem reads
- Restrict video paths to known recording/data directories
- Resolve path and ensure it is under an allowed base directory

Example rule:

```python
resolved = requested_path.resolve()
if not resolved.is_relative_to(ALLOWED_RECORDINGS_DIR):
    raise HTTPException(status_code=400, detail="Invalid video path")
```

Prefer session IDs or recording filenames that backend resolves internally instead of accepting raw absolute paths from the frontend.

## Testing

Add backend tests:

- `GET /ml/models` returns registered models
- Invalid model name returns `422` or `400`
- `POST /ml/predict-anomaly-from-embedding` works with synthetic embedding
- Missing embedding key returns `400`
- `POST /ml/predict-anomaly-from-video` returns `501` for dummy embedder
- `persist=false` does not write `ml_predictions`
- `persist=true` with valid `test_result_id` creates `ml_predictions` row
- `persist=true` with valid `(patient_id, session_id)` resolves `TestResult` and creates row
- `persist=true` with missing/unresolvable IDs returns `400`
- `GET /ml/predictions/test/{test_result_id}` returns persisted predictions
- Deleting a patient/test cascades prediction rows if cascade behavior is expected
- Test history serialization includes latest anomaly prediction summary
- Swagger/OpenAPI includes `/ml` paths

## Validation Commands

Run from repo root:

```bash
source .venv/bin/activate
python -m pytest backend/tests
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
npm audit
```

Backend dependency/security checks:

```bash
python -m pip check
python -m pip_audit -r backend/requirements.txt
```

## Current Dependency State

The repo was updated to secure/current dependencies.

Backend currently passes:

- `pip check`
- `pip-audit`
- backend tests

Frontend currently passes:

- `npm audit`
- `npm run lint`
- `npm run build`

Notable updates:

- `scikit-learn==1.9.0`
- `tslearn==0.9.0`
- `torch==2.13.0`
- `torchvision==0.28.0`
- React 19
- Vite 8
- Tailwind 4

Tailwind 4 required:

- `@tailwindcss/postcss`
- `postcss.config.js` uses `"@tailwindcss/postcss"`
- `src/index.css` includes `@config "../tailwind.config.ts";`

## Recommended Implementation Phases

### Phase 1: Backend Interfaces And DB Table

- Add `MLPrediction` SQLAlchemy model
- Add relationship from `TestResult` to `MLPrediction`
- Add migration/create-table path for existing DBs
- Add `ml_prediction_service.py`
- Add registry and schemas
- Add `/ml/models`
- Add `/ml/predict-anomaly-from-embedding`
- Add tests for persistence and lookup

### Phase 2: Endpoint Scaffolding For Video Models

- Add video embedder protocol
- Add dummy video embedder
- Add `/ml/embed-video`
- Add `/ml/predict-anomaly-from-video` returning `501` until real embedder exists
- Add Swagger descriptions for model swappability and current limitations

### Phase 3: Test History And Frontend Read Path

- Include latest anomaly prediction in test history serialization
- Add frontend API methods
- Add Whole-Video Anomaly card to `VideoSummary`
- Display latest persisted prediction

### Phase 4: Real Video Embedder

- Implement `VJEPA2VideoEmbedder`
- Restrict video path handling to known recording directories
- Add "Run Anomaly Analysis" button
- Persist prediction row after successful analysis

### Phase 5: Prediction History UI

- Show all predictions for a test/session
- Allow comparing model versions
- Keep latest prediction highlighted

## Key Design Principle

Keep this modular:

```text
frontend -> /ml endpoint -> registry -> selected video embedder -> selected anomaly classifier -> ml_predictions table -> test history summary
```

Do not let the frontend or route code know about VJEPA2 internals or LogisticRegression internals.
