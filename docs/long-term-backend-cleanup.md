# Long-Term Backend Cleanup

This document captures future cleanup and refactor ideas that were intentionally left out of the current storage/layout migration.

## Current Intentional State

The recent cleanup established:

- `backend/data/` as the canonical home for runtime-generated artifacts.
- `backend/legacy/` as the archive location for old scripts, camera utilities, and flat-file data.
- `backend/services/dtw_service.py` as the active DTW session/artifact service layer.
- `shared/keypoint-contract.json` as the canonical shared websocket keypoint contract schema.
- `backend/main.py`, `backend/patient_manager.py`, `backend/process_healthy_videos.py`, and `backend/storage_paths.py` still at the backend root because they are active and moving them now would create unnecessary import and workflow churn.

## Top-Level Python Files To Revisit Later

### Keep for now

- `backend/main.py`
  - Active FastAPI entrypoint.
  - Referenced by tests and local startup commands.

- `backend/storage_paths.py`
  - Shared runtime path configuration for active backend modules.

- `backend/patient_manager.py`
  - Still actively imported by the running backend.
  - Candidate for future split or rename, but not during the current migration.

- `backend/process_healthy_videos.py`
  - Still part of the documented healthy-template generation workflow.
  - Could eventually move into a dedicated scripts directory.

### Move later

- `backend/dtw.py`
  - Appears to be an older standalone DTW analysis/visualization script.
  - Not part of the active DTW API pipeline.
  - Good candidate to move into `backend/legacy/scripts/` in a future pass.

## Recommended Future Refactor Areas

### 1. Convert backend root into a clearer application package

Possible future shape:

```text
backend/
  main.py
  config/
    storage_paths.py
  routes/
  services/
  repo/
  schema/
  ml/
  scripts/
    process_healthy_videos.py
  legacy/
  data/
```

Goals:

- Reduce the number of active `.py` files at the backend root.
- Make operational scripts easier to distinguish from API code.
- Separate configuration from business logic.

### 2. Refactor `patient_manager.py`

`patient_manager.py` still mixes multiple concerns:

- database setup
- patient CRUD orchestration
- test-name normalization
- test-history flat-file persistence

Some of the planned service extraction has already happened elsewhere (`PatientService`, `RecordingService`, `TestHistoryService`, `DtwService`), but `patient_manager.py` itself is still a large active module.

Possible future split:

- `repo/` for persistence access only
- `services/` for patient/test-history business logic
- `config/` for database/bootstrap settings

Goals:

- smaller modules
- clearer ownership of logic
- easier testing

### 3. Remove the legacy flat-file test history artifact when safe

`backend/data/test_history.json` is no longer the runtime source of truth after the SQLite test-history refactor.

Future options:

- keep it as a short-term audit/import artifact
- remove it after the team confirms the SQLite migration is complete and no recovery use remains

The live endpoints and WebSocket recording flow should now rely on `testresults` instead.

### 4. Revisit old database artifacts

Known database files to review later:

- repo-root `app.db`
- `backend/data/app.db`
- `backend/data/test.db`
- `backend/legacy/data/app.db.pre_data_path_migration.db`

Future goal:

- document exactly which DBs are authoritative
- remove obsolete DB artifacts after team confirmation

The current authoritative runtime SQLite database is `backend/data/app.db`. The surrounding files remain because the repository has been migrated in-place and older artifacts were preserved for review rather than deleted aggressively.

### 5. Clean test discovery and Python package structure further

One issue already surfaced during verification: non-test modules had names that pytest tried to collect.

Future cleanup areas:

- make backend import/package boundaries more explicit
- standardize naming so app modules do not look like tests
- consider consolidating real tests under `backend/tests/`

### 6. Decide whether archived legacy material stays in-repo permanently

Current archived areas:

- `backend/legacy/scripts/`
- `backend/legacy/camera/`
- `backend/legacy/data/`

Future decision needed:

- keep them in the repository for reference
- or remove them after team confirmation

## Recommended Order For A Future Refactor Pass

1. Decide whether `backend/dtw.py` should move to `backend/legacy/scripts/`.
2. Split `patient_manager.py` by responsibility.
3. Move `process_healthy_videos.py` into a dedicated `scripts/` area and update docs/commands.
4. Standardize package/import structure for backend modules.
5. Revisit whether test history should remain JSON-backed.
6. Remove obsolete legacy/database artifacts only after team approval.

## No Longer Future Work

These items were previously prospective but now exist in the active codebase:

- DTW route/service extraction via `backend/services/dtw_service.py`
- patient-scoped DTW session APIs
- normalized websocket keypoint contract
- one canonical shared keypoint schema source at `shared/keypoint-contract.json`

## Caution

These items are intentionally future-facing. They should be done in small, reviewable steps because they affect:

- import paths
- startup commands
- tests
- local developer workflows
- persisted runtime data
