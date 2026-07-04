# Frontend/Backend Integration Cleanup

This document summarizes the incremental integration cleanup work completed on branch `module1-route-integrity`.

## Scope

The cleanup was performed module-by-module to keep the React/Vite frontend and FastAPI backend buildable during each step.

## Completed Modules

### Module 1: Route Integrity

Commit: `ff72f07` `Fix frontend route integrity`

Changes:
- Added safe frontend route aliases for existing demo navigation targets.
- Normalized the timeline back link to `/patients`.

Result:
- No known frontend navigation target points to a missing route.

Verification:
- `npm run build`

### Module 2: Shared API Access

Commit: `9968b38` `Centralize frontend API access`

Changes:
- Removed hardcoded runtime `localhost:8000` usage from frontend health and patient detail flows.
- Routed patient detail mutations and video upload through `frontend/src/services/api.ts`.
- Added shared API helpers for health checks, patient note/lab appends, and video uploads.

Result:
- Frontend runtime API access no longer hardcodes localhost hosts.
- Specialized `VideoSummary` DTW/session fetches still use direct `/api` requests by design.

Verification:
- `npm run build`

### Module 3: Patient API Contract Cleanup

Commit: `92af085` `Align patient API contracts`

Changes:
- Standardized patient scalar updates on `PUT /patients/{patient_id}`.
- Added dedicated append endpoints:
  - `POST /patients/{patient_id}/lab-results`
  - `POST /patients/{patient_id}/doctor-notes`
- Updated frontend patient mutations to use one coherent contract path.
- Updated frontend service typing for touched patient flows.

Final patient mutation contract:
- Create patient: `POST /patients/`
- Read patient: `GET /patients/{patient_id}`
- Update patient fields: `PUT /patients/{patient_id}`
- Add lab result: `POST /patients/{patient_id}/lab-results`
- Add doctor note: `POST /patients/{patient_id}/doctor-notes`

Verification:
- `npm run build`
- `python -m compileall backend/routes/contracts.py backend/routes/patient.py backend/patient_manager.py backend/main.py`

Notes:
- Backend `pytest` was not available in the environment during verification.

### Module 4: Auth Foundations

Commit: `cbac46c` `Add auth session flow`

Changes:
- Added backend `GET /me`.
- Updated backend login lookup to allow username or email.
- Seeded a demo backend user for the current demo flow:
  - `doctor@hospital.com`
  - `Demo123!`
- Added frontend auth session storage and auth context.
- Updated frontend login to use the real backend `/token` flow.
- Added automatic bearer token attachment in the shared API service.

Session storage:
- Frontend stores the bearer token and `/me` user payload in localStorage.

Verification:
- `npm run build`
- `python -m compileall backend/main.py`

### Module 5: Profile Module

Included in commit: `cbac46c` `Add auth session flow`

Changes:
- Replaced the mocked Profile page with a `/me`-backed read-only view.
- Removed misleading fake-save behavior.
- Added explicit messaging that profile editing is not connected yet.

Result:
- Profile data shown on the page is real backend data.
- Profile editing remains intentionally unsupported until a backend update endpoint exists.

Verification:
- `npm run build`

### Module 6: VideoSummary and Test History Wiring

Status: implemented and build-verified, but not committed separately yet.

Changes made in `frontend/src/pages/VideoSummary.tsx`:
- Replaced mock test history usage with backend patient test history from `apiService.getPatientTests(id)`.
- Derived current test context from backend history and route params.
- Preserved existing DTW/session/ML API flows.
- Replaced mock history card output with backend-backed test records.

What is now backend-backed:
- Patient test history shown in `VideoSummary`
- Current test selection context
- Video list
- DTW session lookup/listing/metrics/export/label flows
- ML prediction from DTW session

Remaining limitation:
- DTW sessions are still listed by test type, not by patient.

Verification:
- `npm run build`

Notes:
- This file had concurrent/pre-existing edits in the worktree, so it was not committed blindly with unrelated changes.

### Module 7: Auth Guards and App-Level Protection

Commit: `23ee63d` `Protect authenticated app routes`

Changes:
- Added a lightweight `ProtectedRoute` wrapper in `frontend/src/App.tsx`.
- Protected the patient, profile, recording, summary, and timeline routes.
- Kept `welcome`, `login`, and `register` public.

Protected routes:
- `/`
- `/patients`
- `/patient/:id`
- `/patient-form`
- `/patient-form/:id`
- `/patient/:id/test-selection`
- `/patient/:id/video-recording/:testId`
- `/patient/:id/video-summary`
- `/patient/:id/video-summary/:testId`
- `/patients/:id/video-summary/:testId`
- `/patients/:patientId/timeline`
- `/profile`

Public routes:
- `/login`
- `/register`
- `/welcome`

Verification:
- `npm run build`

## Demo Login

- Email: `doctor@hospital.com`
- Password: `Demo123!`

## Remaining Follow-Ups

### Registration

Frontend registration is intentionally not connected yet. The current backend does not yet provide a matching safe minimal account-creation endpoint.

### Profile editing

Profile viewing is real. Profile editing still needs a backend update endpoint and matching frontend mutation flow.

## Resolved Since This Cleanup Log

- DTW sessions in `VideoSummary` are now fetched with patient scoping rather than by test type alone.
- Historical DTW session lookup now supports legacy folder-name compatibility and canonical session ids.
- The websocket keypoint payload is now normalized through the shared contract at `shared/keypoint-contract.json`.
