# DTW Recording Flow

This document explains the live recording and DTW session flow as it works today.

## Purpose

The live recording path is responsible for:

- opening the websocket camera session
- streaming frames for overlay and DTW feature extraction
- minting one canonical session id per recording attempt
- saving one recording file
- saving DTW artifacts
- writing a patient test-history entry that points to the same canonical session id

## Key Runtime Pieces

- Frontend page:
  - `frontend/src/pages/VideoRecording.tsx`
- Websocket route:
  - `backend/routes/websockets.py`
- DTW service:
  - `backend/services/dtw_service.py`
- DTW feature extraction/save logic:
  - `backend/routes/utils_dtw.py`
- Recording persistence:
  - `backend/services/recording_service.py`
- Test-history append/build logic:
  - `backend/services/test_history_service.py`

## Canonical Session Identity

Every recording attempt gets a backend-minted DTW session id.

Why:

- retakes must not overwrite older DTW artifacts
- test history, DTW artifacts, websocket completion payloads, and summary routes need one stable identifier

Current sources of truth:

- websocket `initialized` / `dtw_saved` / `complete` messages
- test-history entry `test_id`
- test-history entry `dtw.session_id`
- DTW artifact folder under `backend/data/dtw_runs/<test>/<session_id>/`

## Websocket Message Flow

### 1. `init`

Frontend sends:

- `patientId`
- `testType`
- `testId` (route-level client id, no longer authoritative for DTW persistence)
- `model`
- `fps`

Backend responds with:

- `type: "status"`
- `status: "initialized"`
- canonical `sessionId`

### 2. `frame`

Frontend sends JPEG snapshots over the websocket.

Backend:

- decodes frame
- runs MediaPipe extraction
- pushes normalized keypoint payload into DTW feature extraction
- sends `type: "keypoints"` for overlay rendering

### 3. `end`

Backend finalizes DTW, saves artifacts, saves the recording, writes test history, and sends:

- `dtw_saved`
- `complete`

## Shared Keypoint Contract

The websocket keypoint payload is now driven by one shared schema source:

- `shared/keypoint-contract.json`

Runtime shape:

```json
{
  "type": "keypoints",
  "model": "hands",
  "detections": [
    {
      "kind": "hand",
      "label": "Right",
      "landmarks": [
        { "x": 0.1, "y": 0.2, "z": 0.0 }
      ]
    }
  ]
}
```

For pose:

```json
{
  "type": "keypoints",
  "model": "pose",
  "detections": [
    {
      "kind": "pose",
      "label": null,
      "landmarks": [
        { "x": 0.1, "y": 0.2, "z": 0.0, "visibility": 0.98 }
      ]
    }
  ]
}
```

Backend wrapper:

- `backend/schema/keypoint_contracts.py`

Frontend wrapper:

- `frontend/src/types/keypoint-contract.ts`

## Current Recording Behavior

The live websocket flow now owns the canonical save path for live recordings.

That means one successful live take produces:

- one canonical DTW artifact folder
- one canonical recording file
- one patient history row pointing at that session id

The separate upload flow still exists for user-supplied existing videos:

- `POST /upload-video/`

That route is now a distinct path for uploaded files, not a duplicate save stage for the live websocket session.

## Patient-Scoped DTW Session Access

The summary page now uses patient-scoped DTW queries instead of test-only heuristics.

Endpoints:

- `GET /dtw/sessions/{test_name}?patient_id=...`
- `GET /dtw/sessions/lookup/{session_id}?patient_id=...`

Why:

- avoids mixing sessions from different patients who took the same test
- reduces fallback-to-latest-session errors on historical summaries

## Legacy Compatibility

Older saved DTW runs may have:

- folder names that differ from canonical `meta.json["session_id"]`
- history rows with no explicit DTW linkage

Current support:

- DTW service resolves canonical session ids as well as legacy folder names
- migration script can rename old DTW folders and backfill history rows when the match is safe

Migration entry point:

```bash
python backend/scripts/migrate_historical_dtw.py
```

## Why The Flow Still Looks Hybrid

The live flow uses all three active persistence models together:

- SQLite for patient identity and auth
- JSON for patient-facing test timeline
- filesystem for DTW artifacts and recordings

That is currently intentional. The refactor normalized ownership and contracts first, while leaving the existing storage split in place for compatibility and lower migration risk.

## Recommended Related Docs

- `docs/current-architecture.md`
- `docs/data-storage-model.md`
- `docs/backend-phase-6-verification.md`
