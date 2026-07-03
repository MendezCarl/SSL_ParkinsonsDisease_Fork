# Repo Cleanup Log

## Phase 0 Summary

- Audited active backend storage paths and database defaults.
- Confirmed runtime artifacts were split across `backend/routes/`, `backend/`, and an unused `backend/data/` stub.
- Confirmed active backend test history still uses `TestHistoryManager` from `backend/patient_manager.py`, so `test_history.json` is active runtime data, not legacy-only data.
- Confirmed `backend/test_history_manager.py` is a duplicate legacy module and not imported by active backend code.
- Confirmed standalone scripts in `backend/` and `backend/Camera/` are not imported by the active FastAPI app.
- Confirmed `root app.db` is likely a stray alternate runtime database caused by the relative `sqlite:///./app.db` default when the backend is launched from the repository root.
- Confirmed `backend/app.db` is the expected active SQLite database when the backend is launched from `backend/` as documented.
- Confirmed `repo/db.py` still points to `test.db`, and `main.py` imported it only for side effects.

## Deferred Work

- Final `.gitignore` policy for `backend/data/` is intentionally deferred.
- Removal of migrated generated artifacts from git will happen only after team review.

## Phase 1 Summary

- Added `backend/storage_paths.py` as the canonical source for runtime and legacy paths.
- Moved live runtime artifacts into `backend/data/`:
  - `dtw_runs/`
  - `labelled_training_data/`
  - `recordings/`
  - `templates/`
  - `jsons/`
  - `test_history.json`
  - `test.db`
- Preserved the pre-existing sparse `backend/data/app.db` as `backend/legacy/data/app.db.pre_data_path_migration.db`.
- Promoted `backend/app.db` to the canonical active database at `backend/data/app.db`.
- Moved unused flat files to `backend/legacy/data/`:
  - `patients.json`
  - `patients.json.backup`

## Phase 2 Summary

- Updated active backend code to read and write only from `backend/data/` paths.
- Removed `main.py`'s unused `repo.db` import side effect so startup no longer creates `test.db` indirectly.
- Kept API response paths like `recordings/{filename}` unchanged.

## Phase 3 Summary

- Moved unused standalone scripts into `backend/legacy/scripts/`.
- Moved the unused `Camera/` package into `backend/legacy/camera/`.
- Moved the duplicate `test_history_manager.py` module into `backend/legacy/`.

## Phase 4 Summary

- Removed the accidental root `package-lock.json`.
- Removed the unused `frontend/templates/` HTML leftovers.
- Removed emptied source-adjacent storage directories after migration.

## Phase 5 Summary

- `frontend`: `npm run build` passed.
- `backend`: pytest collection now fails only because `torch` is not installed in the current environment.
- Renamed non-test Python modules that pytest was incorrectly collecting:
  - `backend/repo/test_repository.py` -> `backend/repo/result_repository.py`
  - `backend/legacy/test_history_manager.py` -> `backend/legacy/history_manager.py`

## Phase 6 Audit

- Current `.gitignore` is still malformed and duplicated:
  - contains an unresolved `=======` line
  - repeats `*.db`, `*.pyc`, `*.mp4`, `*.mov`, `*.avi`, `*.npz`
  - still references pre-refactor paths like `backend/patients.json`
- Current broad ignore rules already cover:
  - `backend/data/app.db`
  - `backend/data/test.db`
  - `backend/data/test_history.json`
  - `backend/data/templates/**/*.npz`
- Current ignore rules do not explicitly cover the new generated runtime directories under `backend/data/`:
  - `backend/data/dtw_runs/`
  - `backend/data/labelled_training_data/`
  - `backend/data/recordings/`
  - `backend/data/jsons/`
- Result: many generated files under `backend/data/` are currently untracked but not ignored.
- Audit counts:
  - tracked files formerly under `backend/jsons/`: 22
  - tracked files formerly under `backend/routes/dtw_runs/`: 6
  - tracked files formerly under `frontend/templates/`: 2
  - current untracked files under `backend/data/`: 38
  - current untracked files under `backend/legacy/`: 14

## Proposed `.gitignore` Rules

Recommended replacement backend-storage section:

```gitignore
# Backend runtime data
backend/data/app.db
backend/data/test.db
backend/data/test_history.json
backend/data/dtw_runs/
backend/data/labelled_training_data/
backend/data/recordings/
backend/data/templates/
backend/data/jsons/

# Legacy source-adjacent generated paths kept for migration review
backend/recordings/
backend/jsons/
backend/routes/dtw_runs/
backend/routes/_labelled_training_data/
backend/routes/recordings/
backend/routes/templates/
```

Notes:

- `backend/legacy/` should remain tracked; it contains archived code and data we intentionally preserved in-repo.
- This proposal is explicit by path and does not rely only on broad wildcard ignores.
- A later cleanup should also remove the duplicate rules and merge artifact from `.gitignore`.

## Remove-From-Git Review List

Review as generated/runtime artifacts:

- 22 files formerly tracked under `backend/jsons/`
- 6 files formerly tracked under `backend/routes/dtw_runs/`
- any future tracked files under `backend/data/dtw_runs/`
- any future tracked files under `backend/data/labelled_training_data/`
- any future tracked files under `backend/data/recordings/`
- any future tracked files under `backend/data/templates/`
- any future tracked files under `backend/data/jsons/`

Review as cleanup-only removals already made:

- root `package-lock.json`
- `frontend/templates/index.html`
- `frontend/templates/recording_details.html`

Keep tracked in-repo unless the team explicitly wants them removed:

- `backend/legacy/scripts/*`
- `backend/legacy/camera/*`
- `backend/legacy/data/patients.json`
- `backend/legacy/data/patients.json.backup`
- `backend/legacy/data/app.db.pre_data_path_migration.db`

## Phase 6 Implementation Summary

- Rewrote `.gitignore` into a clean, deduplicated version.
- Removed the unresolved merge artifact and stale pre-refactor ignore entries.
- Added explicit ignore rules for active generated runtime paths under `backend/data/`.
- Kept `backend/legacy/` intentionally unignored so archived code and data remain reviewable and can be tracked in git.
- Verified with `git check-ignore` that all intended `backend/data/` runtime paths are now ignored.

## Possible Git Removals To Review Later

- Migrated contents formerly under `backend/routes/dtw_runs/`
- Migrated contents formerly under `backend/routes/_labelled_training_data/`
- Migrated contents formerly under `backend/routes/recordings/`
- Migrated contents formerly under `backend/routes/templates/`
- Migrated contents formerly under `backend/jsons/`
- Migrated contents formerly under `backend/recordings/`
- Migrated `backend/test.db`
- Archived `backend/legacy/scripts/*`
- Archived `backend/legacy/camera/*`
- Archived `backend/legacy/data/patients.json`
- Archived `backend/legacy/data/patients.json.backup`
- Archived `backend/legacy/data/app.db.pre_data_path_migration.db`
