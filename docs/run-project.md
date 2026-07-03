# Run The Project

This guide explains how to run the project locally and with Docker.

## Prerequisites

Install these first:
- Python 3.12
- Node.js and npm
- Docker and Docker Compose if you want the containerized path

Useful notes:
- The frontend dev server runs on `http://localhost:5174`
- The FastAPI backend runs on `http://localhost:8000`
- Swagger UI is available at `http://localhost:8000/docs`

## Local Run

### 1. Create the Python virtual environment

From the repo root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 2. Install backend dependencies

```bash
pip install -r backend/requirements.txt
```

### 3. Download MediaPipe model files

First-time setup only:

```bash
mkdir -p backend/models
curl -L "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task" -o backend/models/hand_landmarker.task
curl -L "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task" -o backend/models/pose_landmarker_lite.task
```

### 4. Start the backend

In one terminal:

```bash
source .venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Run that command from the `backend/` directory:

```bash
cd backend
source ../.venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Backend URLs:
- API root: `http://localhost:8000/`
- Health check: `http://localhost:8000/health`
- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

### 5. Install frontend dependencies

In a second terminal:

```bash
cd frontend
npm install
```

### 6. Start the frontend

```bash
npm run dev
```

Frontend URL:
- `http://localhost:5174`

Vite proxies:
- `/api/*` -> backend on `http://localhost:8000`
- `/ws/*` -> backend websocket routes

## Demo Login

If the backend demo user is available, use:

- Email: `doctor@hospital.com`
- Password: `Demo123!`

## Docker Run

From the repo root:

```bash
docker-compose up --build
```

URLs:
- Frontend: `http://localhost:5174`
- Backend: `http://localhost:8000`

## Optional DTW Template Setup

If healthy templates have not been generated yet, run:

```bash
cd backend
python process_healthy_videos.py
```

Useful variants:

```bash
python process_healthy_videos.py --test finger-tapping
python process_healthy_videos.py --force
python process_healthy_videos.py --no-rebuild-template
```

## Frontend Commands

From `frontend/`:

```bash
npm run dev
npm run build
npm run build:dev
npm run lint
npm run preview
```

## Common Issues

### Backend imports fail

Make sure the virtualenv is active and backend dependencies are installed:

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### Swagger does not load

Check:
- backend is running on port `8000`
- open `http://localhost:8000/docs`
- if startup errors mention optional crypto dependencies, reinstall backend requirements in the project virtualenv

### MediaPipe models missing

Re-run the model download commands and confirm these files exist:
- `backend/models/hand_landmarker.task`
- `backend/models/pose_landmarker_lite.task`

### ML prediction endpoints fail

The project can run without the external ML checkpoint, but inference endpoints may fail if the checkpoint is missing.

## Related Docs

- `docs/swagger-api-docs.md`
- `docs/frontend-backend-integration-cleanup.md`
- `README.md`
- `backend/README.md`
