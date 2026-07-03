# Parkinson's Disease AI Assessment Platform

A web-based clinical tool for administering motor-function tests, scoring them with Dynamic Time Warping (DTW) against healthy baselines, and predicting UPDRS severity with an LSTM-MIL deep learning model. A doctor review workflow allows clinicians to confirm or correct the AI prediction and automatically archives labelled data for future model retraining.

---

## Architecture Overview

```
┌─────────────────────────────────┐        ┌──────────────────────────────────┐
│       Browser (React / Vite)    │        │    FastAPI Backend  (port 8000)  │
│  port 5174 dev / built static   │◄──────►│                                  │
│                                 │  REST  │  /patients   patient CRUD        │
│  Pages                          │  + WS  │  /token      JWT auth            │
│  ├─ Login / Register            │        │  /dtw        DTW session API     │
│  ├─ Patient List / Details      │        │  /ml         LSTM-MIL inference  │
│  ├─ Test Selection              │        │  /ws         WebSocket keypoints │
│  ├─ Video Recording             │        │  /recordings video file serving  │
│  ├─ Video Summary  ◄── AI card  │        │                                  │
│  └─ Timeline                    │        └──────────────┬───────────────────┘
└─────────────────────────────────┘                       │
                                                          │
              ┌───────────────────────────────────────────┤
              │                                           │
   ┌──────────▼──────────┐              ┌─────────────────▼──────────────┐
   │  MediaPipe Tasks    │              │       SQLite (SQLAlchemy)       │
   │  hand_landmarker    │              │  Users · Patients · Visits      │
   │  pose_landmarker    │              └────────────────────────────────┘
   └──────────┬──────────┘
              │ keypoints (T × 24)
   ┌──────────▼──────────┐
   │   DTW Engine        │     data/dtw_runs/<test>/<session_id>/
   │   (tslearn)         │     ├─ dtw_artifacts.npz
   │   vs healthy NPZ    │     └─ meta.json
   └──────────┬──────────┘
              │
   ┌──────────▼──────────┐
   │  LSTM-MIL Classifier│     data/labelled_training_data/<test>/stage_N/<session>/
   │  (T×24 → Stage 0-3) │     ← doctor-labelled sessions archived here
   └─────────────────────┘
```

---

## Repository Layout

```
.
├── backend/                  FastAPI application
│   ├── main.py               App entry-point, routers, auth, recordings endpoints
│   ├── requirements.txt
│   ├── routes/
│   │   ├── patient.py        /patients  CRUD
│   │   ├── dtw_rest.py       /dtw       DTW session REST API + doctor label
│   │   ├── classifier.py     /ml        LSTM-MIL inference endpoints
│   │   ├── websockets.py     /ws        Real-time keypoint WebSocket
│   │   └── contracts.py      Shared Pydantic models
│   ├── services/
│   │   └── lstm_cnn_inference.py   Inference wrapper (windowed, attention)
│   ├── repo/                 SQLAlchemy models, DB session, Excel import
│   ├── schema/               Pydantic schemas (patient, visit, classifier)
│   ├── ml/                   MIL bag-level classifier module
│   ├── data/                 Runtime-generated artifacts and local DB files
│   ├── legacy/               Archived scripts, camera utilities, and flat files
│   ├── healthy_data/         Healthy reference videos (per-test subdirs)
│   ├── models/               MediaPipe .task files
│   │   ├── hand_landmarker.task
│   │   └── pose_landmarker_lite.task
│   ├── process_healthy_videos.py   Offline pipeline: videos → NPZ templates
│   └── tests/                Pytest suite
├── frontend/                 Vite + React + TypeScript
│   └── src/
│       ├── pages/            Full-page route components
│       ├── components/ui/    shadcn/ui component library
│       ├── services/api.ts   HTTP client
│       └── types/            Shared TypeScript types
└── docker-compose.yml
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, TypeScript, shadcn/ui, Tailwind CSS |
| Backend | FastAPI, Python 3.12, Uvicorn |
| Real-time | WebSockets (Starlette) |
| Pose estimation | MediaPipe Tasks API 0.10.33 (HandLandmarker, PoseLandmarker) |
| DTW scoring | tslearn 0.6 |
| ML model | LSTM + Attention MIL classifier (PyTorch) |
| Database | SQLite via SQLAlchemy 2.0 |
| Auth | JWT (python-jose), BCrypt (passlib) |
| Container | Docker / docker-compose |

---

## Quick Start (local, no Docker)

### Backend

```bash
# 1. Create and activate virtualenv
python3.12 -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Download MediaPipe model files (first time only)
mkdir -p backend/models
curl -L "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task" \
  -o backend/models/hand_landmarker.task
curl -L "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task" \
  -o backend/models/pose_landmarker_lite.task

# 4. Start the server
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install          # or: bun install
npm run dev          # serves on http://localhost:5174
```

Requests to `/api/*` are proxied to `http://localhost:8000` by Vite.

### Docker (both services)

```bash
docker-compose up --build
```

---

## Building Healthy Reference Templates

Before running DTW comparisons for the first time, generate the NPZ templates from healthy-control videos:

```bash
cd backend
python process_healthy_videos.py                  # all test types
python process_healthy_videos.py --test finger-tapping  # single type
python process_healthy_videos.py --force          # re-process already-done videos
```

Videos go in `backend/healthy_data/<test-type>/` (e.g., `finger-tapping/`, `fist-open-close/`, `stand-and-sit/`).

---

## Doctor Label & Training Data Workflow

After a patient session is processed:

1. The **Video Summary** page displays the AI-predicted UPDRS stage with confidence and per-class probabilities.
2. A clinician clicks **Confirm / Adjust Stage**, selects the correct stage from a dropdown, and optionally adds clinical notes.
3. The frontend calls `PATCH /api/dtw/sessions/{test}/{session_id}/label`.
4. The backend:
   - Updates `meta.json` in the session folder with `doctor_confirmed_stage`, timestamp, `label_source` (`doctor_confirmed` or `doctor_correction`), and optional notes.
   - Copies the session artifacts to `backend/data/labelled_training_data/<test>/stage_<N>/<session_id>/` for future model retraining.
   - Updates the patient's severity field if `patient_id` is provided.

---

## API Reference

See [backend/README.md](backend/README.md) for the full endpoint reference, inference contract, and test instructions.
