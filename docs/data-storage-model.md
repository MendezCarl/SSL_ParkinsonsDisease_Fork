# Data Storage Model

This document explains the current persistence model and why different kinds of data live in different places.

## Authoritative Runtime Storage

### 1. SQLite database

Path:

- `backend/data/app.db`

Current live tables:

- `users`
- `patients`
- `labresults`
- `doctornotes`
- `testresults`

### 2. Legacy JSON test history import source

Path:

- `backend/data/test_history.json`

Purpose:

- historical import source for legacy timeline rows
- optional backup/reference file during the SQLite cutover

### 3. File-based artifact storage

Paths:

- `backend/data/dtw_runs/`
- `backend/data/recordings/`
- `backend/data/templates/`
- `backend/data/labelled_training_data/`
- `backend/data/jsons/`

Purpose:

- DTW arrays and session metadata
- video recordings
- healthy reference templates
- exported/derived runtime data

## Current SQLite Structure

### `users`

Columns:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `username VARCHAR(255) UNIQUE NOT NULL`
- `full_name VARCHAR(255) NOT NULL`
- `email VARCHAR(320) UNIQUE`
- `hashed_password VARCHAR(255) NOT NULL`
- `location VARCHAR(255) NOT NULL`
- `title VARCHAR(255) NOT NULL`
- `speciality VARCHAR(255) NOT NULL`

### `patients`

Columns:

- `patient_id VARCHAR(64) PRIMARY KEY`
- `user_id INTEGER NOT NULL`
- `name VARCHAR(255)`
- `dob DATE`
- `height INTEGER`
- `weight INTEGER`
- `severity VARCHAR(50)`
- `record_number VARCHAR(32)`

Indexes/constraints:

- FK: `user_id -> users.id ON DELETE CASCADE`
- index: `ix_patients_user_id`
- unique index: `ix_patients_record_number_unique`

### `labresults`

Columns:

- `lab_id VARCHAR PRIMARY KEY`
- `patient_id VARCHAR(64) NOT NULL`
- `result_date DATETIME`
- `results TEXT`
- `added_by VARCHAR(255)`

Indexes/constraints:

- FK: `patient_id -> patients.patient_id ON DELETE CASCADE`
- index: `ix_labresults_patient_id`

### `doctornotes`

Columns:

- `note_id VARCHAR PRIMARY KEY`
- `patient_id VARCHAR(64) NOT NULL`
- `note_date DATETIME`
- `note TEXT`
- `added_by VARCHAR(255)`

Indexes/constraints:

- FK: `patient_id -> patients.patient_id ON DELETE CASCADE`
- index: `ix_doctornotes_patient_id`

### `testresults`

Columns:

- `test_id INTEGER PRIMARY KEY AUTOINCREMENT`
- `patient_id VARCHAR(64) NOT NULL`
- `test_name VARCHAR(100)`
- `test_date DATETIME`
- `recording_file VARCHAR(512)`
- `frame_count INTEGER`
- `session_id VARCHAR(64)`
- `fps INTEGER`
- `summary_available BOOLEAN`
- `dtw JSON`
- `extra JSON`

Indexes/constraints:

- FK: `patient_id -> patients.patient_id ON DELETE CASCADE`
- index: `ix_testresults_patient_id`
- index: `ix_testresults_patient_date`
- index: `ix_testresults_patient_name`
- index: `ix_testresults_session_id`

## Authoritative Split After The Refactor

After the test-history migration:

- SQLite is authoritative for users/patients/lab results/doctor notes/test history
- DTW artifacts and recordings remain authoritative on disk
- `backend/data/test_history.json` is no longer a runtime source of truth
- SQLite foreign-key enforcement is enabled at runtime, so child rows must reference real parent rows

This removes the previous JSON compatibility layer from `/patients/{id}/tests` while still keeping large binary and DTW artifact data file-based.

Persisted revisit snapshots now live on the same `testresults` rows:

- lightweight DTW summary metrics are stored for reuse in the revisit UI
- ML prediction snapshots are stored after session-based inference runs
- raw DTW arrays and other heavy artifacts remain file-based

## Why It Is Still Structured This Way

### Risk-managed refactor scope

The refactor focused on:

- fixing broken validation
- normalizing contracts
- clarifying ownership between routes and services
- normalizing DTW session identity
- reducing frontend/backend drift

It intentionally did not force a full storage-model rewrite at the same time.

### DTW data is artifact-heavy

DTW sessions store large arrays, alignment data, and metadata in a way that is naturally file-based.

### Recordings are binary assets

Video storage and file serving are simpler and more transparent on the filesystem than in SQLite blobs.

### Legacy JSON history is now a migration source only

The JSON history file remains useful for one-time migration and audit purposes, but runtime reads and writes now belong in `testresults`.

### SQLite relationships are now enforced

The backend enables `PRAGMA foreign_keys = ON` for runtime connections.

That means:

- `patients.user_id` must reference a real `users.id`
- `labresults`, `doctornotes`, and `testresults` must reference a real `patients.patient_id`
- uploads, websocket recordings, and direct test-history writes now require the patient record to exist first

## Historical Compatibility

Older saved data may differ from current canonical writes in these ways:

- DTW folder names may not equal canonical session ids
- history rows may not contain `test_id` or `dtw.session_id`
- recording filenames may use older `ws_recording_...` patterns

Current mitigation:

- compatibility-aware reads
- patient-scoped DTW lookup/list endpoints
- historical migration script:
  - `backend/scripts/migrate_historical_dtw.py`
- legacy history import script:
  - `backend/scripts/migrate_test_history_to_sqlite.py`

## Recommended Related Docs

- `docs/current-architecture.md`
- `docs/dtw-recording-flow.md`
- `docs/backend-phase-6-verification.md`
