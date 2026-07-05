# Current Architecture

This document describes how the application works today after the backend refactor work, not how it looked before the audit.

## High-Level Shape

The application is intentionally split across three persistence styles:

1. SQLite for relational application data
2. JSON for lightweight patient test-history timeline data
3. Filesystem storage for recordings, DTW artifacts, templates, and other generated assets

That split is deliberate. The project has evolved from a demo/prototype codebase, and the refactor work prioritized stabilizing the running behavior without forcing a risky all-at-once migration into one storage model.

## Active Runtime Areas

Backend runtime paths are rooted under `backend/data/`.

Important paths:

- `backend/data/app.db`
  - authoritative runtime SQLite database
- `backend/data/test_history.json`
  - authoritative patient timeline/test-history feed for the current app
- `backend/data/dtw_runs/`
  - DTW artifacts and `meta.json` files per test/session
- `backend/data/recordings/`
  - generated or uploaded video files
- `backend/data/templates/`
  - healthy reference templates used by DTW

## Backend Modules By Responsibility

Active backend layers now look roughly like this:

- `backend/main.py`
  - FastAPI app setup
  - auth endpoints
  - root/health endpoints
  - recording list/serve endpoints
  - patient test-history REST endpoints
- `backend/routes/patient.py`
  - patient CRUD/import HTTP routes
- `backend/routes/dtw_rest.py`
  - DTW REST routes delegated through `DtwService`
- `backend/routes/websockets.py`
  - websocket transport for live recording
- `backend/services/patient_service.py`
  - patient orchestration wrapper
- `backend/services/recording_service.py`
  - recording persistence and filename generation
- `backend/services/test_history_service.py`
  - test-history entry construction and append/load helpers
- `backend/services/dtw_service.py`
  - DTW session lookup, patient scoping, artifact reads, legacy alias handling, doctor label persistence
- `backend/services/dtw_migration_service.py`
  - historical DTW folder normalization and test-history backfill
- `backend/patient_manager.py`
  - still active for database bootstrap, patient persistence orchestration, validation, CSV import core logic, and JSON-backed test-history manager

## Why The Storage Model Is Still Split

### SQL is authoritative for users and patients

SQLite is the right fit for:

- users
- patients
- lab results
- doctor notes

These entities are relational, queryable, and naturally fit the current SQLAlchemy model.

### Test history remains JSON-backed

`backend/data/test_history.json` remains active because:

- the historical app flow already relied on it
- moving it into SQL during the refactor would have introduced extra migration risk
- the refactor goal was to normalize contracts and ownership before replacing storage

This means patient history is currently timeline-oriented and lightweight, while DTW detail still lives in the DTW artifact store.

### DTW artifacts remain file-based

DTW runs store:

- compressed arrays
- plotted series inputs
- per-session metadata

Those are better represented as artifact files under `backend/data/dtw_runs/` than as large SQL rows.

### Recordings remain file-based

Video recordings are binary assets and are served by filename from `backend/data/recordings/`.

## Current Compatibility Strategy

The system includes compatibility logic because older saved data used different conventions.

Examples:

- older DTW run folders sometimes used route-level folder names instead of canonical session ids
- older history rows often lacked explicit DTW linkage
- older websocket recording filenames used `ws_recording_...` patterns

Current strategy:

- new writes use canonical session ids and richer history rows
- reads support legacy alias resolution
- a conservative migration script can normalize old DTW folders and backfill history when matches are unambiguous

## Current Shared Contract Strategy

The websocket keypoint payload is now driven by one canonical schema file:

- `shared/keypoint-contract.json`

Language-specific wrappers read that schema in:

- `backend/schema/keypoint_contracts.py`
- `frontend/src/types/keypoint-contract.ts`

That avoids relying on raw MediaPipe-specific websocket message shapes as the de facto contract.

## Recommended Related Docs

- `docs/data-storage-model.md`
- `docs/dtw-recording-flow.md`
- `docs/backend-phase-6-verification.md`
