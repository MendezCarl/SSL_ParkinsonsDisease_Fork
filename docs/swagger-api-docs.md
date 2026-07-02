# Swagger API Docs

The FastAPI backend exposes interactive API documentation and the raw OpenAPI schema.

## URLs

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## What is documented

The generated Swagger docs now include explicit request and response schemas for the main integration points instead of generic `object` responses.

Notable improvements:
- Auth endpoints:
  - `POST /token`
  - `GET /me`
- System endpoints:
  - `GET /`
  - `GET /health`
- Patient test history endpoints:
  - `GET /patients/{patient_id}/tests`
  - `POST /patients/{patient_id}/tests`
- Recording endpoints:
  - `POST /upload-video/`
  - `GET /videos/{patient_id}/{test_name}`
- DTW endpoints:
  - session lookup
  - session list
  - DTW series
  - channel series
  - axis aggregate
  - label endpoint
- Patient request models now include example payloads for:
  - create
  - update
  - lab results
  - doctor notes
  - filter criteria
- ML request models include a sample sequence payload.

## Notes

- If the backend is running in the repo virtualenv, use that interpreter to ensure all backend dependencies are available.
- The demo-user seed is now non-fatal during app import so `/docs` can still load even if an optional bcrypt backend is unavailable.
