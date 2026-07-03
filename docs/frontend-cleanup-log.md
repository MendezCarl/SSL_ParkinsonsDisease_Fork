# Frontend Cleanup Log

## Phase 0 Summary

- Confirmed `frontend/src/pages/Welcome.tsx` is intentional and should be kept as the future live landing page.
- Confirmed `frontend/src/assets/tempBackground.png` is intentional and should be kept as the temporary background asset for `Welcome.tsx`.
- Confirmed these files are currently unused and safe cleanup candidates:
  - `frontend/src/pages/Index.tsx`
  - `frontend/src/App.css`
  - `frontend/src/components/ui/use-toast.ts`
- Confirmed `frontend/src/App.tsx` mounts both toast systems:
  - shadcn/Radix via `components/ui/toaster.tsx`
  - Sonner via `components/ui/sonner.tsx`
- Confirmed app pages currently use `frontend/src/hooks/use-toast.ts` and not `frontend/src/components/ui/use-toast.ts`.
- Confirmed React Query is mounted in `frontend/src/App.tsx`, but there are no `useQuery`, `useMutation`, or related React Query hooks in `frontend/src`.
- Deferred larger frontend cleanup items to later phases:
  - toast system consolidation
  - React Query keep/remove decision
  - route-level code splitting
  - route alias cleanup
  - API layer split
  - patient flow consolidation

## Phase 1 Summary

- Removed `frontend/src/pages/Index.tsx`.
- Removed `frontend/src/App.css`.
- Removed `frontend/src/components/ui/use-toast.ts`.

## Verification

- `npm run build`: passed.
- `npm run lint`: failed due to an ESLint configuration/runtime issue unrelated to the deleted files.

Observed lint error:

```text
TypeError: Error while loading rule '@typescript-eslint/no-unused-expressions':
Cannot read properties of undefined (reading 'allowShortCircuit')
```

This should be handled as a separate frontend tooling fix before using lint as a cleanup gate for later phases.

## Next Planned Phases

- Phase 2: shared plumbing cleanup
  - choose one toast system
  - decide whether React Query stays
  - remove small duplicate utility helpers
- Phase 3: route-level code splitting
- Phase 4: route cleanup
- Phase 5: API layer cleanup
- Phase 6: patient flow consolidation

## Phase 2 Summary

- Kept the existing shadcn/Radix toast system because app pages already use `frontend/src/hooks/use-toast.ts` throughout the codebase.
- Removed the unused Sonner wiring:
  - removed `frontend/src/components/ui/sonner.tsx`
  - removed Sonner mounting from `frontend/src/App.tsx`
  - removed the `sonner` dependency
  - removed the now-unused `next-themes` dependency that existed only for Sonner theming
- Removed React Query because it was mounted in `frontend/src/App.tsx` but not used anywhere in `frontend/src`:
  - removed `QueryClient` and `QueryClientProvider` from `frontend/src/App.tsx`
  - removed the `@tanstack/react-query` dependency
- Deferred duplicate utility cleanup for later because those helpers still sit inside active page and service flows that deserve a separate review.

## Phase 2 Verification

- `npm run build`: passed.
- Bundle size improved after removing unused plumbing, but Vite still reports a large main chunk warning.
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.

## Phase 3 Summary

- Converted route pages in `frontend/src/App.tsx` to lazy-loaded imports using `React.lazy`.
- Wrapped the router in `Suspense` with a minimal `Loading page...` fallback.
- Applied route-level code splitting across the app pages, including the heavier routes:
  - `VideoSummary.tsx`
  - `VideoRecording.tsx`
  - `Timeline.tsx`

## Phase 3 Verification

- `npm run build`: passed.
- Route-level code splitting significantly reduced the old single entry bundle.
- The previous Vite large-chunk warning did not appear after this change.
- Build output now shows separate route/page chunks, including dedicated chunks for:
  - `VideoSummary`
  - `VideoRecording`
  - `Timeline`
  - `PatientList`
  - `PatientDetails`
  - `PatientForm`
  - `Welcome`
  - `Login`
  - `Register`
  - `Profile`
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.

## Phase 4 Summary

- Standardized frontend patient-facing navigation on the plural `/patients/...` route family.
- Updated internal links and navigations across the frontend pages to use canonical plural routes.
- Introduced explicit compatibility redirects in `frontend/src/App.tsx` for old singular routes:
  - `/patient/:id`
  - `/patient/:id/test-selection`
  - `/patient/:id/video-recording/:testId`
  - `/patient/:id/video-summary`
  - `/patient/:id/video-summary/:testId`
  - `/patient-form`
  - `/patient-form/:id`
- Added canonical patient form routes:
  - `/patients/new`
  - `/patients/:id/edit`
- Made `/` a compatibility redirect to `/patients` instead of treating it as the canonical patient-list URL.
- Confirmed backend alignment: no backend API route change was required because the backend already uses plural `/patients` endpoints.

## Phase 4 Verification

- `npm run build`: passed.
- Internal frontend route usage is now canonicalized to `/patients/...`.
- Compatibility aliases remain in place through redirects for existing bookmarks or deep links.
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.

## Phase 5 Summary

- Introduced a dedicated DTW/video-summary service module at `frontend/src/services/dtw.ts`.
- Moved `VideoSummary.tsx` off direct low-level `fetch()` calls for:
  - DTW session lookup
  - patient video listing
  - DTW session listing
  - DTW series metrics
  - DTW aggregate axis data
  - ML prediction from session
  - DTW export download payload
  - doctor-confirmed stage labelling
- Centralized request details for those flows:
  - API base path handling
  - auth token header injection
  - JSON parsing and error normalization
- Updated the `VideoSummary` empty-state copy to reflect the current backend storage location `backend/data/recordings`.

## Phase 5 Notes

- This phase was intentionally scoped to the `VideoSummary`/DTW path as the safest high-impact extraction target.
- The larger `frontend/src/services/api.ts` split is still a future cleanup item.

## Phase 5 Verification

- `npm run build`: passed.
- `VideoSummary.tsx` no longer contains direct `fetch()` calls to `/api/dtw`, `/api/videos`, or `/api/ml`.
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.

## Phase 6 Summary

- Consolidated persisted patient editing onto the canonical API-backed patient form route.
- Removed the duplicate local-only edit flow from `frontend/src/pages/PatientDetails.tsx`.
- Updated the `PatientDetails` “Edit Patient” action to navigate to the canonical edit route:
  - `/patients/:id/edit`
- Removed the inline edit dialog/state from `PatientDetails` because it only updated local component state and did not persist through the backend.

## Phase 6 Notes

- This phase intentionally handled the highest-risk duplication first: two different edit flows with different behavior.
- Quick-add creation in `PatientList.tsx` and CSV import defaults are still separate follow-up work.
- Lab result and doctor note flows in `PatientDetails.tsx` were left unchanged because they already call backend endpoints and were not part of the duplicate local edit problem.

## Phase 6 Verification

- `npm run build`: passed.
- `PatientDetails` bundle size decreased after removing the duplicate inline edit UI.
- Persisted patient editing now has one canonical frontend route and backend path.
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.

## Identity Phase 1 Summary

- Made `recordNumber` a real backend-persisted patient field instead of reconstructing it from `patient_id` in the frontend.
- Kept `patient_id` as the internal persistent identifier and separated it from the doctor-facing record number.
- Added backend bootstrap/migration support to:
  - add the `record_number` column to existing databases
  - backfill existing patients with generated chronological values
  - enforce uniqueness through a database index
- Implemented backend-generated record numbers with the format `REC-000001`, `REC-000002`, etc.
- Added `recordNumber` to backend patient responses so frontend list/detail/test pages receive stable persisted values.
- Updated backend patient search so doctor-facing search can match either patient name or record number.
- Updated frontend patient mapping to consume backend `recordNumber` as first-class data.
- Updated patient creation/edit UX so `recordNumber` is no longer a user-entered required field:
  - displayed as read-only in the detailed patient form
  - described as system-generated during patient creation
- Updated CSV import guidance to reflect that record numbers are generated automatically.
- Removed the requirement for quick-create flows to supply a manual record number.

## Identity Phase 1 Verification

- `npm run build`: passed.
- Backend database schema verified to contain the new `record_number` column.
- Existing patient rows were verified to be backfilled with generated values like `REC-000001`.
- Backend response smoke test confirmed `recordNumber` is returned in patient payloads.
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.

## Phase 2 Summary

- Added patient selection mode to `frontend/src/pages/PatientList.tsx`.
- Added a `Select` / `Cancel Select` toggle alongside the patient-list action buttons.
- While selection mode is active:
  - patient cards become selectable instead of navigational
  - the primary create button is replaced with `Delete Patients`
  - selected cards are visually highlighted
- Implemented sequential deletion on top of the existing single-patient delete endpoint.
- Added confirmation before deletion.
- Added partial-failure handling:
  - successfully deleted patients are removed from the UI
  - failed deletions remain selected
  - a summary toast reports successes and failures

## Phase 2 Notes

- This phase intentionally reuses the existing backend `DELETE /patients/{patient_id}` endpoint.
- No batch-delete backend endpoint was introduced yet.
- The current implementation is the first safe step toward broader admin deletion workflows.

## Phase 2 Verification

- `npm run build`: passed.
- Patient list now supports multi-select deletion without changing normal card navigation outside selection mode.
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.

## Phase 3 Summary

- Fixed the canonical patient edit flow so every intentional main-form field now has explicit persistence behavior.
- Kept `recordNumber` in the form as a backend-owned read-only field.
- Kept `labResults` and `doctorNotes` in the main edit form, per product direction.
- Updated the main patient edit flow so when `labResults` or `doctorNotes` change during edit:
  - core patient fields still save through the canonical patient update endpoint
  - changed lab results are appended as a new lab result history entry through the existing backend lab-result endpoint
  - changed doctor notes are appended as a new doctor-note history entry through the existing backend doctor-note endpoint
- Added helper text in the edit form so the append behavior is visible to users.

## Phase 3 Notes

- This phase intentionally avoids introducing new backend bulk update semantics for note/history arrays.
- The persistence rule is now explicit instead of silent:
  - core fields update the patient record
  - note/history text changes append new entries
- Clearing `labResults` or `doctorNotes` in the main form does not delete prior history; that would require a separate explicit delete/edit history workflow.

## Phase 3 Verification

- `npm run build`: passed.
- The canonical patient edit route now persists all intended main-form changes through explicit backend paths.
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.

## Phase 4 Summary

- Standardized frontend service call contracts on the existing app-wide `{ success, data, error }` response shape.
- Added a shared service response type at `frontend/src/services/service-response.ts`.
- Updated `frontend/src/services/api.ts` to use that shared service response type.
- Converted `frontend/src/services/dtw.ts` away from exception-based returns so it now follows the same contract as `api.ts`.
- Updated `frontend/src/pages/VideoSummary.tsx` to consume DTW service responses through `response.success`, `response.data`, and `response.error` instead of `try/catch`-driven service usage.

## Phase 4 Notes

- This phase standardizes service behavior without yet splitting the large `api.ts` file by domain.
- `getRecordingUrl()` remains a plain utility function because it is not an async service call.
- The larger domain split remains a later phase.

## Phase 4 Verification

- `npm run build`: passed.
- `api.ts` and `dtw.ts` now follow the same frontend service contract style.
- `VideoSummary.tsx` no longer mixes exception-based DTW service calls with success-object-based patient service calls.
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.

## Phase 5 Summary

- Split the old monolithic `frontend/src/services/api.ts` into domain-oriented modules.
- Added a shared transport layer in `frontend/src/services/client.ts`.
- Added a shared patient/test mapping layer in `frontend/src/services/patient-mappers.ts`.
- Extracted domain modules:
  - `frontend/src/services/auth.ts`
  - `frontend/src/services/patients.ts`
  - `frontend/src/services/tests.ts`
  - `frontend/src/services/uploads.ts`
  - `frontend/src/services/ml.ts`
- Kept `frontend/src/services/dtw.ts` as the DTW/video-summary domain module from the earlier cleanup phase.
- Reduced `frontend/src/services/api.ts` to a compatibility facade that re-exports the existing `apiService` surface for current pages.

## Phase 5 Notes

- This phase prioritizes structural separation without forcing a broad import rewrite across the app.
- Existing page imports of `apiService` continue to work through the facade layer.
- The codebase now has a cleaner base for future direct domain imports or a later dependency-injection/container layer.

## Phase 5 Verification

- `npm run build`: passed.
- The old API/service responsibilities are now separated into transport, mappers, and domain services.
- `frontend/src/services/api.ts` remains available as a stable compatibility boundary for the current app.
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.

## Phase 6 Summary

- Removed the silent fallback that coerced unsupported backend test types to `stand-and-sit`.
- Extended the shared frontend test model to support an explicit `unknown` type.
- Updated the shared patient/test mapper so unsupported backend test types are now mapped to `unknown` instead of being mislabeled as a known test.
- Added a mapper-level console warning when unsupported backend test data is received.
- Updated patient/test history UI styling to handle the explicit `unknown` type.
- Removed the page-level fallback normalization in `frontend/src/pages/TestSelection.tsx` and now trust the shared test mapping layer there as well.
- Updated timeline breakdown rendering so an `unknown` category appears if unsupported tests are present in the data.

## Phase 6 Notes

- This phase prioritizes truthful representation over forced compatibility.
- Unsupported tests may still be displayed in the UI, but they are no longer silently presented as `stand-and-sit`.
- The user-visible fallback is now explicit rather than misleading.

## Phase 6 Verification

- `npm run build`: passed.
- Shared test mapping no longer silently coerces unsupported backend test types into a valid known type.
- `frontend/src/pages/TestSelection.tsx` no longer reintroduces its own test-type fallback.
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.

## Phase 7 Summary

- Replaced unstable `Date.now()`-based fallback IDs in the shared patient mapper with deterministic IDs derived from:
  - patient ID
  - date
  - content
  - author metadata
- Stabilized fallback IDs for:
  - lab result history entries
  - doctor note history entries
  - latest lab result projection
  - latest doctor note projection

## Phase 7 Notes

- This phase targets client-side identity stability for React keys and timeline/history rendering.
- New user-created lab/note submissions still use fresh IDs at creation time, which is appropriate because those are new records rather than fallback projections of existing backend data.

## Phase 7 Verification

- `npm run build`: passed.
- Shared mapper fallback IDs are now deterministic across reloads for existing backend records.
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.

## Phase 8 Summary

- Separated backend health detection from auth-dependent patient access in `frontend/src/hooks/use-api-status.ts`.
- Backend status now reflects only the `/health` endpoint result.
- Updated patient-list status wording from auth-coupled connectivity language to backend availability language:
  - `Backend reachable`
  - `Backend unavailable`

## Phase 8 Notes

- This phase prevents expired auth or patient-fetch failures from being misreported as backend outages.
- Auth/session failures still need their own UI handling path, but they are no longer folded into the backend health indicator.

## Phase 8 Verification

- `npm run build`: passed.
- Backend health state no longer depends on protected patient list access.
- `npm run lint`: now passes after the tooling and code cleanup.

## ESLint Tooling Cleanup

- Fixed the ESLint runtime failure caused by the `@typescript-eslint/no-unused-expressions` rule path in the flat config.
- Reached a clean `npm run lint` state by addressing the actual reported code issues instead of hiding them behind a broken lint runtime.
- Resolved remaining lint findings across:
  - hook dependency handling
  - explicit `any` usage
  - deterministic fallback IDs
  - regex escapes
  - `require()` usage in Tailwind config
  - empty interface/type aliases
  - fast-refresh export warnings through targeted config allowances for intentional shared exports

## Final Frontend Verification

- `npm run lint`: passed.
- `npm run build`: passed.

## Remaining Cleanup Completion

### Native Browser Prompt Replacement

- Replaced the remaining `window.confirm()` usage in `PatientList.tsx` with in-app confirmation UI via `AlertDialog`.
- Replaced the remaining native `alert()` usage in `VideoSummary.tsx` with the app toast system.

### Debug Logging Removal

- Removed remaining `console.log()` / `console.info()` development logging from the active frontend pages.
- Kept `console.error()` paths where they are still useful for operational failure reporting.

### VideoSummary Structural Split

- Extracted major `VideoSummary` UI sections into `frontend/src/components/video-summary/VideoSummarySections.tsx`.
- Moved the following render blocks out of the page:
  - header
  - recorded video card
  - test history card
  - performance statistics card
  - ML prediction card
  - doctor label dialog
- `VideoSummary.tsx` now focuses more on state orchestration and DTW-specific rendering logic.

### PatientList Structural Split

- Extracted major `PatientList` UI sections into `frontend/src/components/patient-list/PatientListSections.tsx`.
- Moved the following render blocks out of the page:
  - CSV import dialog
  - list controls
  - primary create/delete action
  - patient card rendering
- `PatientList.tsx` now focuses more on list state, CSV processing, selection, and data orchestration.

### API Facade Removal

- Migrated remaining pages and hooks off `frontend/src/services/api.ts` and onto direct domain services.
- Removed the `api.ts` compatibility facade after all imports were migrated.

Direct domain imports now cover:

- auth
- patients
- tests
- uploads
- DTW

### Legacy Route Redirect Removal

- Removed the old singular patient route redirects from `frontend/src/App.tsx`.
- The app now only exposes the canonical plural `/patients/...` frontend route family.

## Final Frontend State

- Canonical route family only
- Domain-split services
- No `api.ts` compatibility facade
- No browser-native `alert()` / `window.confirm()` prompts
- No remaining debug `console.log()` / `console.info()` noise in active frontend pages
- `npm run lint` passes
- `npm run build` passes

## Phase 8 Verification

- `npm run build`: passed.
- Backend health state no longer depends on protected patient list access.
- `npm run lint`: still fails due to the existing ESLint configuration/runtime issue.
