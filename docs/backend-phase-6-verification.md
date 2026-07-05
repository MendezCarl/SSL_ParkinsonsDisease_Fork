# Backend Phase 6 Verification

This document records the final verification pass completed after the backend refactor phases.

## Scope Covered

- System endpoints:
  - `GET /`
  - `GET /health`
  - `GET /docs`
  - `GET /openapi.json`
- Auth:
  - `POST /token`
  - `GET /me`
- Patient flows:
  - create patient
  - read patient
  - update patient
  - add lab result
  - add doctor note
  - list patients
  - search patients
  - filter patients
  - delete patient
- CSV import:
  - `POST /patients/import/csv`
- Recording/history flows:
  - `POST /upload-video/`
  - `GET /patients/{id}/tests`
  - `GET /videos/{id}/{test}`
  - `GET /recordings/{filename}`
- Websocket live recording flow:
  - `WS /ws/camera`
  - `init`
  - `frame`
  - `end`
  - `dtw_saved`
  - `complete`
- DTW session APIs:
  - patient-scoped list and lookup
  - canonical/legacy session-id resolution
- Historical data migration:
  - DTW folder rename to canonical session ids
  - test-history backfill where matching is unambiguous

## Automated Verification Executed

- Backend test suite: `23 passed`
- Frontend production build: passed

Tests added or expanded during this pass:

- `backend/tests/test_phase6_integration.py`
- `backend/tests/test_dtw_migration_service.py`
- `backend/tests/test_dtw_api.py`
- `backend/tests/test_keypoint_contracts.py`

## Historical Migration Result

Executed via:

```bash
python backend/scripts/migrate_historical_dtw.py
```

Observed result:

- `renamed_folders`: 11
- `backfilled_entries`: 11
- `updated_existing_entries`: 0
- `skipped_ambiguous_entries`: 0
- `skipped_unmatched_entries`: 31
- `errors`: 0

Interpretation:

- older DTW folders that still used route-level folder names were renamed to canonical session ids from `meta.json`
- historical test-history rows were backfilled only when the patient, test type, and timestamp produced one clear DTW match
- unmatched rows were intentionally preserved without modification rather than guessed

## Additional Issues Found and Fixed During Verification

- Patient ID generation could collide during fast CSV imports because IDs were timestamp-based at second resolution.
  - Fixed in `backend/patient_manager.py` by switching to a UUID-suffixed patient id.
- Video listing excluded `.webm` files even though upload and serve flows support them.
  - Fixed in `backend/main.py` by expanding supported extensions in the listing route.

## Remaining Notes

- The websocket keypoint contract is now normalized and driven by `shared/keypoint-contract.json`.
- The backend and frontend still use language-specific wrappers around that shared schema:
  - `backend/schema/keypoint_contracts.py`
  - `frontend/src/types/keypoint-contract.ts`
- The historical migration is intentionally conservative and does not fabricate DTW links where the old data cannot be matched confidently.
