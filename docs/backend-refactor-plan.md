# Backend Refactor Plan

Based on the Phase 0 audit findings in `docs/backend-phase-0-audit.md`.

## Phase 0 — Audit / Map Current Flows (DONE)

11 findings documented in the audit doc. Key outcomes:
- Patient import is a frontend-only batch-create workflow with no backend import endpoint.
- Workbook importer (`backend/repo/excel_to_repository.py`) is stale and unwired.
- Validation in `create_patient` / `update_patient_info` is effectively broken (`_validate()` never returns its errors).
- Recording/DTW flow produces duplicate assets (websocket MP4 + REST upload .mov).
- DTW session identity is inconsistent across three different identifiers.
- Test history does not store patient-to-session linkage.
- Keypoint overlay contract is spread across four layers.
- Repeat audit added five more deltas: missing `dtw_saved.session_id`, retake overwrite risk, widened history-schema drift, duplicate legacy history-manager copy, and DTW reduce-contract mismatch.

---

## Phase 0.5 — Fix Broken Validation (PREREQUISITE FOR PHASE 1)

### Target
Make `backend/patient_manager.py::_validate()` actually return its `errors` dict to callers, and ensure the existing severity branch rejects invalid non-empty values.

### Why this is a prerequisite
- Phase 1 will build a backend import service on top of the same validation path.
- If validation is broken, the import endpoint will silently accept invalid data.
- The current code looks like it validates but does not enforce anything.

### Verification
- `create_patient` returns `errors` for invalid inputs instead of silently succeeding.
- `update_patient_info` returns `errors` for invalid inputs.
- Invalid severity values are rejected consistently in both paths.
- Existing frontend create/update forms surface errors correctly.

### Risk
Mild — client code currently does not check for errors from these endpoints, so adding validation that rejects previously-accepted data could break the frontend create flow.

---

## Phase 1 — Redesign Patient Import / CSV Flow

### Current state (from audit)
- The frontend parses CSVs in-browser, normalizes everything, and calls `POST /patients/` once per row.
- The backend workbook importer expects a different schema and writes to obsolete tables.
- There is no backend endpoint for batch import.

### Target
- One backend endpoint that accepts a CSV file and returns a structured batch result.
- Server-side header mapping, date normalization, severity normalization, and default-value policy.
- Frontend uploads the file, displays the result, and refreshes the patient list.
- `record_number` remains backend-generated.
- The frontend no longer needs to compute `age` or define default values.

### Questions to settle
1. **Format**: CSV only, or also Excel workbook? (The audit found the workbook importer stale — decide whether to keep the format.)
2. **Scope**: Import only patients, or also lab results and doctor notes?
3. **Error model**: All-or-nothing, or partial-success with per-row error reporting?
4. **Validation behavior**: Apply the same validation as the single-create path, or define import-specific rules?

### Verification
- Import endpoint allows uploading a CSV and returns `{ success_count, failure_count, errors[] }`.
- Existing `POST /patients/` single-create path still works unchanged.
- Frontend PatientList CSV dialog uses the new endpoint instead of the row loop.

### Coupling to remove in this phase
- Frontend: CSV header knowledge, date normalization, severity normalization, default values, age computation.
- Backend: stale workbook importer paths (keep them or remove after replacement).

---

## Phase 2 — Normalize Keypoint Overlay / Session Mapping

### Current state (from audit)
- Three conflicting session identifiers: frontend `testId`, DTW artifact folder name, `meta.json["session_id"]`.
- Test history does not store a canonical DTW session reference.
- Patient-to-session linkage is implicit (metadata inside meta.json only) — no server-side index.
- Websocket payloads are raw MediaPipe shapes consumed by four layers independently.
- Recording produces duplicate saves (WS MP4 + REST .mov) with format/extension mismatch.
- Frontend ignores websocket completion messages (`dtw_saved`, `complete`, `dtw_error`, `status`).
- The websocket `dtw_saved` message currently drops the saved `session_id` even though `save_dtw_npz()` produces one.
- Retakes currently reuse the same route-level `testId`, so multiple takes can write into the same DTW folder.
- The published patient test-history contract now advertises `test_id`, `fps`, `summary_available`, and `dtw.session_id`, but the live writer still does not populate them.

### Target
- Choose one canonical DTW session id and use it in: artifact folders, meta.json, test history, REST responses, frontend routes.
- Ensure every recording attempt gets a fresh canonical session id so retakes never overwrite prior artifacts.
- Persist patient-to-session linkage explicitly (add `patient_id` to meta.json or store the relationship in SQL).
- Define a stable websocket payload contract for overlay keypoints, including one documented schema consumed by both DTW extraction and frontend rendering.
- Restore websocket completion contracts so `dtw_saved` returns the canonical session id and artifact refs, and test history stores the same id.
- The frontend summary page queries sessions by patient, not by test-only heuristics.

### Questions to settle
1. **Canonical ID**: Should the artifact folder name *be* the session id, or should meta.json's `session_id` become the folder name?
2. **Persistence**: Should DTW session metadata live in SQL alongside the patient, or remain file-based?
3. **Payload contract**: Should the websocket expose raw landmarks, normalized landmarks (wrist-centered, scaled), or both?
4. **Recording**: Keep both WS and REST upload, or switch to a single save path?
5. **Take identity**: Should the backend mint a per-attempt session id, or should the frontend request one before recording starts?

### Verification
- Fresh test recording produces exactly one recording file, not two.
- A single session id is returned by: websocket `dtw_saved`, `GET /patients/{id}/tests`, and `GET /dtw/sessions/lookup/{id}`.
- Retaking the same test creates a new session id and leaves the prior DTW artifacts intact.
- VideoSummary resolves the correct DTW session for any historical test entry.
- Frontend overlay and backend DTW extraction consume from a shared payload type.

---

## Phase 3 — Decouple Backend Route Logic from Business Logic

### Current state (from audit)
- `backend/patient_manager.py` is a monolith mixing: DB bootstrap, patient CRUD orchestration, test-name normalization, flat-file test history, async wrappers.
- `backend/routes/websockets.py` mixes MediaPipe extraction, DTW building, recording persistence, and history writes.
- `backend/main.py` defines auth endpoints, upload endpoints, recording endpoints, and the test history REST API directly.
- `backend/routes/dtw_rest.py` and `backend/routes/utils_dtw.py` have overlapping responsibility for DTW file layout and session metadata.

### Target
- Extract clearly-owned services:
  - PatientService from `patient_manager.py`
  - RecordingService from `websockets.py` (recording persistence only)
  - DtwService from `utils_dtw.py` + `dtw_rest.py`
- Routes become thin controllers that validate input, call services, and format responses.
- `patient_manager.py` shrinks or is replaced by smaller modules.

### Verification
- `patient_manager.py` no longer imports from `routes/contracts.py` (dependency direction is the correct way).
- Routes do not directly write files, run DTW, or open database sessions — they delegate to services.
- All existing endpoint contracts remain unchanged.

---

## Phase 4 — Remove Confirmed Stale / Dead Paths

### Current state (from audit)
The audit already identified specific files that should not be treated as authoritative:

| File | Status |
|---|---|
| `backend/repo/excel_to_repository.py` | Not wired into any route |
| `backend/repo/result_repository.py` | Not imported by active code |
| `backend/repo/patient_repository.py::add_test_result()` | Stale against current `TestResult` model |
| `backend/patient_manager.py` comment about SQL migration | Aspirational, not reflected in runtime |
| Unused imports (e.g., `TestResultRepository` in `patient_manager.py`) | Imported but never called |
| `backend/legacy/history_manager.py` | Archived duplicate; active code imports `TestHistoryManager` from `patient_manager.py` |

### Target
- Remove or archive confirmed dead paths after Phases 1–3 have established replacements.
- Keep only what is actively used by the running system.

### Verification
- `git grep` for each removed import shows zero active references.
- Backend starts and passes existing tests.
- No route 404s or import errors.

### Risk
Low — these paths are already dead. Removal only if the replacement flow exists.

---

## Phase 5 — Reduce Frontend/Backend Knowledge Leakage

### Current state (from audit)
- Frontend knows: CSV header-to-field mapping, date normalization, severity mapping, default values, age derivation.
- Frontend `patient-mappers.ts` manufactures lab/note entries from flat CSV strings and understands Raw MediaPipe landmark dimensions.
- Frontend `VideoRecording.tsx` ignores websocket completion events, so it cannot react to DTW save results directly.

### Target
- All CSV normalization moves to the backend import endpoint (Phase 1).
- All session/payload normalization moves to the backend websocket and DTW services (Phase 2).
- Frontend only handles display and user interaction — no business rule duplication.
- Shared payload types are co-located or published from the backend.

### How this differs from Phases 1 and 2
Phase 5 is a *verification pass*: after Phases 1 and 2, check that no business logic remains duplicated in frontend code.

### Verification
- No frontend code performs date normalization or severity string matching on backend data.
- No frontend code computes `age` from `birthDate` for API calls.
- No frontend code knows landmark counts or dimensionality for specific test types.
- The frontend imports payload types from a single source rather than redefining them.

---

## Phase 6 — Integration Verification

### Scope
Confirm that the refactored system behaves identically to the pre-refactor system across the critical flows:

1. **Patient CRUD**: Create, read, update, delete, search, filter — all still work.
2. **CSV import**: Upload a file, see results, patients appear in the list.
3. **Test recording**: Live camera → websocket → DTW → recording → history — end-to-end.
4. **Upload existing video**: File upload + test history — end-to-end.
5. **Video summary**: Navigate to summary, see correct DTW session, see prediction, confirm label.
6. **Auth**: Login, token refresh, protected routes.
7. **Health endpoints**: `/health`, `/`, OpenAPI docs still load.

### Verification
- Frontend `npm run build` passes.
- Backend starts without errors (import paths, module resolution).
- Manual or automated E2E walkthrough of each critical flow.
- No 404, 422, or 500 errors that were not present before the refactor.

---

## Summary

| Phase | What | Why | Depends on |
|---|---|---|---|
| 0.5 | Fix broken `_validate()` | Without this, Phase 1 import endpoint will silently accept bad data | Nothing |
| 1 | Backend import endpoint | Move CSV parsing out of browser, fix validation, add batch contract | Phase 0.5 |
| 2 | Keypoint/session normalization | Resolve 3 conflicting IDs, stop duplicate saves, fix historical routing | Nothing |
| 3 | Decouple routes from logic | Shrink monolith, clarify ownership, thin controllers | Phase 2 |
| 4 | Remove dead paths | Clean up confirmed stale files after replacements exist | Phases 1–3 |
| 5 | Frontend leakage check | Verify no business logic remains duplicated in frontend | Phases 1, 2 |
| 6 | Integration verification | Confirm everything still works end-to-end | All phases |

### Risk matrix

| Risk | Mitigation |
|---|---|
| Frontend create flow breaks if validation starts rejecting previously-accepted data | Phase 0.5: add validation incrementally, test with existing frontend |
| DTW session id change breaks existing saved sessions | Phase 2: write migration that creates canonical aliases for existing sessions |
| Patient import format/scope decision delays implementation | Phase 1: answer the three questions (CSV vs Excel, scope, error model) before coding |
| Phase 2 scope is too large (session identity + payload contract + duplicate saves) | Split into 2a (canonical ID + patient→session link) and 2b (websocket contract + recording path) |
