# Backend Phase 0 Audit

This document maps the current backend-adjacent flows that should drive the next refactor pass.

Scope of this audit:

- patient import / CSV flow
- websocket recording / keypoint overlay / DTW flow
- confirmed coupling hotspots
- confirmed stale or dead paths that should not shape the redesign

## Current Architecture Snapshot

The active backend still spans multiple persistence models and responsibilities:

- patient CRUD lives in SQLite-backed routes through `backend/routes/patient.py` and `backend/patient_manager.py`
- test history lives in flat-file JSON via `backend/patient_manager.py::TestHistoryManager`
- DTW artifacts live on disk under `backend/data/dtw_runs/`
- recordings live on disk under `backend/data/recordings/`
- websocket extraction, DTW building, recording persistence, and history writes are all mixed in `backend/routes/websockets.py`

That split is the main backdrop for the findings below.

## Phase 0 Findings

### 1. Patient import is currently a frontend batch-create flow, not a backend import flow

The live import path is:

1. `frontend/src/components/patient-list/PatientListSections.tsx`
   - presents the CSV upload dialog only
2. `frontend/src/pages/PatientList.tsx`
   - reads the CSV in-browser
   - parses headers and rows
   - normalizes dates and severity
   - fills defaults for missing height, weight, notes, and severity
   - loops over rows sequentially and calls `createPatient(...)`
3. `frontend/src/services/patients.ts`
   - converts each row into the regular patient-create contract
   - posts one request per patient to `POST /patients/`
4. `backend/routes/patient.py`
   - forwards to `async_create_patient(...)`
5. `backend/patient_manager.py`
   - generates `patient_id`
   - generates backend-owned `record_number`
   - persists the patient, lab results, and doctor notes

The backend workbook importer at `backend/repo/excel_to_repository.py` is not wired into any active route or service in the current codebase.

### 2. The backend workbook importer is stale relative to the live schema

`backend/repo/excel_to_repository.py` appears to reflect an older data model:

- expects workbook-managed `patient_id` input instead of using the live patient creation flow
- writes `Visit` rows even though visits are not part of the active patient API flow
- writes `TestResult` fields that do not match the current SQLAlchemy model shape used elsewhere

Related stale code confirms this drift:

- `backend/repo/patient_repository.py::add_test_result()` still refers to `test_type` and `keypoints`, but `backend/repo/sql_models.py::TestResult` now defines `test_name`, `recording_file`, and `frame_count`
- `backend/repo/result_repository.py` exists but is not used by active routes
- `backend/patient_manager.py` imports `TestResultRepository` but does not use it

This means the repo currently contains import-related backend code, but not a live backend import pipeline.

### 3. CSV import currently leaks backend knowledge into the frontend

The current browser-side import flow duplicates business rules that should ideally live server-side:

- date parsing and normalization
- severity normalization
- default value policy for missing fields
- lab result and doctor note coercion
- age derivation from birth date to satisfy `POST /patients/`

Specific leakage points:

- `frontend/src/pages/PatientList.tsx` knows which CSV headers map to backend fields
- `frontend/src/services/patient-mappers.ts` manufactures lab/note history entries from flat CSV strings
- `frontend/src/services/patient-mappers.ts` computes `age` even though the backend already has `birthDate`

This increases drift risk because import policy is currently split across UI code and backend create logic.

### 4. Validation in the live patient creation path is effectively bypassed

`backend/patient_manager.py::_validate()` builds an `errors` dictionary but never returns it.

Current callers expect a returned dictionary:

- `create_patient(...)`
- `update_patient_info(...)`

In practice, that means import-time validation and normal patient create/update validation are much weaker than the surrounding code suggests.

This is important for Phase 1 because a backend import endpoint should not be built on top of validation that only looks implemented.

### 5. Websocket recording, DTW persistence, test history, and upload persistence are split across two separate save paths

The live recording flow is:

1. `frontend/src/pages/TestSelection.tsx`
   - creates a client-side `testId` like `test-<timestamp>`
   - navigates to `/patients/:id/video-recording/:testId`
2. `frontend/src/pages/VideoRecording.tsx`
   - opens `ws://.../ws/camera`
   - sends `init` with `patientId`, `testType`, `testId`, `model`, and `fps`
   - streams frames to the websocket
3. `backend/routes/websockets.py`
   - decodes base64 frames
   - extracts MediaPipe landmarks
   - returns raw keypoint payloads for overlay drawing
   - pushes each frame into `EndOnlyDTW`
4. `backend/routes/utils_dtw.py`
   - loads the reference template
   - builds live feature vectors
   - computes positional, amplitude, and speed DTW
   - saves artifacts under `backend/data/dtw_runs/<test>/<test_id>/`
5. `backend/routes/websockets.py`
   - saves a websocket-generated MP4 recording
   - appends a flat-file test-history entry through `TestHistoryManager`
6. `frontend/src/pages/VideoRecording.tsx`
   - separately stops `MediaRecorder`
   - uploads the recorded blob to `POST /upload-video/`
7. `backend/main.py`
   - writes another recording file under `backend/data/recordings/`

This means one user recording produces:

- DTW artifacts from the websocket path
- a websocket-saved MP4
- a second REST-uploaded recording file
- a flat-file history row

### 6. The frontend ignores websocket completion payloads and only consumes live keypoint payloads

`frontend/src/pages/VideoRecording.tsx` currently handles websocket messages only when `msg.type === "keypoints"`.

It does not consume:

- `dtw_saved`
- `dtw_error`
- `complete`
- `status`

That has two effects:

- the client does not persist or react to the DTW save result directly
- the client later has to rediscover session state indirectly through routes and follow-up REST calls

### 7. DTW session identity is inconsistent across layers

There are three different identifiers in play:

- frontend route `testId` generated in `TestSelection.tsx`
- DTW artifact folder name, which is currently the frontend-provided `test_id`
- `meta.json["session_id"]`, which is separately generated inside `save_dtw_npz(...)`

The active DTW REST layer treats the folder name as the session id:

- `backend/routes/dtw_rest.py::list_sessions()` returns the directory name
- `backend/routes/dtw_rest.py::lookup_session()` searches directory names

But `backend/routes/utils_dtw.py::save_dtw_npz()` also writes a different `session_id` into `meta.json`.

That mismatch is a coupling hazard because the codebase has no single canonical DTW session identifier.

### 8. Historical summary routing is fragile because test history does not reliably store DTW session linkage

The websocket history write currently stores only basic fields such as:

- `test_name`
- `date`
- `recording_file`
- `frame_count`

It does not store a canonical DTW session reference.

Downstream effect:

- `frontend/src/services/patient-mappers.ts` falls back to using `recording_file` as the test id when no explicit `test_id` exists
- `frontend/src/pages/TestSelection.tsx` links summary pages using that derived id
- `frontend/src/pages/VideoSummary.tsx` then tries to resolve the route parameter as either a test key or a DTW session id

For freshly recorded tests, the route can still work because the app navigates with the original client-side `testId`.

For historical tests, the route may instead contain a recording filename, which is not a DTW session id. In that case the summary page can fail to resolve the intended session and may fall back to the newest session for that test type.

That creates a real risk of showing the wrong DTW session for the selected patient.

### 9. DTW session lookup and listing are test-scoped, not patient-scoped

`backend/routes/dtw_rest.py` organizes runs by:

- test name
- session folder name

It does not index or query by patient.

Patient context only exists as metadata inside `meta.json`, and the current REST lookup/list flows do not use it to filter sessions.

That makes patient-summary selection dependent on frontend heuristics rather than an authoritative patient-to-session relationship.

### 10. Recording persistence currently has a duplicate-save problem and a file-format mismatch risk

There are two recording save implementations:

- websocket flow saves frames as `.mp4`
- `POST /upload-video/` writes the uploaded blob as `.mov`

The frontend `MediaRecorder` blob is created as `video/webm`, but `backend/main.py` saves it with a `.mov` filename and later serves `.mov` as `video/quicktime`.

That is a format/extension mismatch risk on top of the duplicate-save issue.

### 11. Keypoint overlay mapping is currently an implicit raw MediaPipe contract

The backend websocket sends raw-ish MediaPipe-shaped payloads:

- `{"model": "hands", "hands": [...]}`
- `{"model": "pose", "pose": [...]}`

The frontend owns the drawing rules, landmark chains, visibility filtering, and some feature extraction assumptions.

Examples of contract spread:

- backend decides payload structure in `backend/routes/websockets.py`
- backend decides DTW feature extraction shape in `backend/routes/utils_dtw.py`
- frontend decides overlay rendering in `frontend/src/pages/VideoRecording.tsx`
- ML session extraction infers modality from DTW dimensions in `backend/routes/classifier.py`

This is functional, but it is not yet a normalized payload contract.

## Confirmed Stale Or Misaligned Paths

These paths should not be treated as authoritative when redesigning the live flow:

- `backend/repo/excel_to_repository.py`
  - present but not wired into the live backend
- `backend/repo/patient_repository.py::add_test_result()`
  - stale against the current `TestResult` model
- `backend/repo/result_repository.py`
  - not used by active routes
- `backend/patient_manager.py` comment `TestHistoryManager refactor -> SQL TestResultRepository`
  - aspirational, not reflected in the active runtime path

## Recommended Refactor Boundaries

### Phase 1: redesign patient import / CSV flow

Recommended target:

- move import parsing and validation into a backend import service
- accept one uploaded file and return a structured batch result
- keep `record_number` backend-generated
- stop requiring the frontend to compute `age`
- make row-level validation and error reporting authoritative on the server

Questions to settle in Phase 1:

- should CSV be the canonical import format, or should workbook support remain a goal?
- should import create only patients, or also lab results / doctor notes?
- should import be all-or-nothing, or partial-success with row errors?

### Phase 2: normalize keypoint overlay and session mapping

Recommended target:

- define one canonical DTW session id and use it everywhere
- persist patient-to-session linkage explicitly
- stop relying on route heuristics or recording filenames to recover DTW sessions later
- define a stable websocket payload contract for overlay and downstream consumers

Questions to settle in Phase 2:

- should websocket messages expose raw landmarks, normalized landmarks, or both?
- should the summary page query sessions by patient instead of by test only?
- should DTW artifact metadata become the authoritative record, or should SQL own session metadata?

### Phase 3: decouple route logic from business logic

Strong candidates for extraction:

- patient service from `backend/patient_manager.py`
- import service for batch patient creation
- websocket session service from `backend/routes/websockets.py`
- DTW session service from `backend/routes/utils_dtw.py` and `backend/routes/dtw_rest.py`

## Suggested Order After This Audit

1. Fix or replace the patient import path before adding more import features.
2. Choose one canonical DTW session identity before expanding summary/history features.
3. Decide whether test history remains JSON-backed or moves into SQL alongside patients.
4. Remove or rewrite stale importer/test-result code only after the replacement flow exists.

## Audit Summary

The main Phase 0 conclusion is:

- the live patient import flow is really a frontend batch patient-create workflow
- the live recording flow is really a split websocket-plus-upload workflow with duplicated persistence
- DTW session identity and patient/session linkage are the most important normalization gaps before deeper backend decoupling
