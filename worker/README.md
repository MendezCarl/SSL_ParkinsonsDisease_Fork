# Anomaly Detection Worker

Polls the backend for pending anomaly-detection jobs, fetches each job's recording,
runs it through an `AnomalyProcessor`, and posts the result back. Runs on a
separate, more powerful machine on the hospital's private network — VideoMAE-style
inference is too heavy to run in the main API process.

Full design: `docs/superpowers/specs/2026-07-11-anomaly-pipeline-integration-design.md`.

## What's here today

`processor.py` ships a `StubAnomalyProcessor` that returns an empty report — there is
no trained model yet. The poll → fetch → process → post loop is fully real and
runnable now; dropping in the real VideoMAE + autoencoder model later means writing
one new `AnomalyProcessor` subclass and pointing `main.py` at it. Nothing else changes.

## Setup

```bash
cd worker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration (environment variables)

| Variable | Default | Notes |
|---|---|---|
| `API_BASE_URL` | `http://localhost:8000` | Backend base URL, reachable from this machine |
| `ANOMALY_WORKER_TOKEN` | *(required)* | Must match the backend's `ANOMALY_WORKER_TOKEN` |
| `POLL_INTERVAL_SECONDS` | `10` | How often to check for pending jobs |
| `REQUEST_TIMEOUT_SECONDS` | `30` | HTTP timeout per request to the backend |

## Running

```bash
export API_BASE_URL=http://<backend-host>:8000
export ANOMALY_WORKER_TOKEN=<shared-secret>
python main.py
```

## Tests

```bash
cd worker
python -m pytest -q tests/
```
