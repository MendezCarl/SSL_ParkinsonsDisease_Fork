from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Body, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Any, Dict, List, Optional, Annotated
from datetime import datetime, timedelta, timezone
import logging
import os
import shutil
import uvicorn
from pydantic import BaseModel, ConfigDict, Field

from routes.dtw_rest import router as dtw_router
from routes.patient import router as patient_router
from routes.websockets import router as ws_router
from routes.classifier import router as classifier_router
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from repo.sql_models import User
from patient_manager import SessionLocal
from storage_paths import RECORDINGS_DIR
from routes.utils_dtw import generate_session_id, normalize_test_name
from services.recording_service import resolve_recording_path, save_uploaded_video
from services.test_history_service import (
    append_patient_test,
    build_uploaded_video_test_history_entry,
    get_patient_tests as load_patient_tests,
    patient_exists,
)

try:
    import jwt
    from jwt import InvalidTokenError
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test environments
    try:
        from jose import jwt
        from jose import JWTError as InvalidTokenError
    except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test environments
        jwt = None

        class InvalidTokenError(Exception):
            pass

try:
    from passlib.context import CryptContext
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test environments
    CryptContext = None

# ============ Paths / Folders ============
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)

# ============ Lazy imports (avoid libGL issues on boot) ============

app = FastAPI(
    title="Patient Management API",
    version="0.1.0",
    description=(
        "Backend API for the Parkinson's demo application. Swagger UI is available at `/docs` "
        "and the raw OpenAPI schema is available at `/openapi.json`."
    ),
    openapi_tags=[
        {"name": "auth", "description": "Authentication and current-user endpoints."},
        {"name": "system", "description": "Health and diagnostic endpoints."},
        {"name": "test-history", "description": "Patient test history storage and retrieval."},
        {"name": "recordings", "description": "Uploaded and generated recording assets."},
    ],
)
app.include_router(dtw_router)
app.include_router(patient_router)
app.include_router(ws_router)
app.include_router(classifier_router)

# ============ CORS ============
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:5174",  # Add this line
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",  # Add this line too
        "http://127.0.0.1:3000",
        "http://localhost:8001",
        "http://localhost:8000/patients",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "stupid_hash_for_now"
ALGO = "HS256"
ACCESS_MIN = 30
_FALLBACK_TOKEN_PREFIX = "dev-token:"

if CryptContext is None:
    class _FallbackPasswordContext:
        def hash(self, value: str) -> str:
            return value

        def verify(self, plain: str, hashed: str) -> bool:
            return plain == hashed

    pwd = _FallbackPasswordContext()
else:
    pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class CurrentUserResponse(BaseModel):
    username: str
    full_name: str
    email: str | None = None
    location: str
    title: str
    speciality: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class RootResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    message: str


class DtwMetricsSnapshot(BaseModel):
    session_id: str | None = None
    distance: float | None = None
    avg_step_cost: float | None = None
    similarity: float | None = None


class PersistedDtwAnalysisSnapshot(BaseModel):
    session_id: str | None = None
    distance_pos: float | None = None
    distance_amp: float | None = None
    distance_spd: float | None = None
    avg_step_pos: float | None = None
    avg_step_cost: float | None = None
    similarity_overall: float | None = None
    similarity_pos: float | None = None
    similarity_amp: float | None = None
    similarity_spd: float | None = None
    distance: float | None = None
    similarity: float | None = None


class PersistedMlPredictionSnapshot(BaseModel):
    predicted_updrs_stage: int
    probabilities: Dict[str, float]
    severity: str
    severity_stage: int
    prediction: str
    confidence: float
    model_version: str | None = None
    preprocessing_version: str | None = None
    generated_at: str | None = None


class TestAnalysisSnapshot(BaseModel):
    dtw_metrics: PersistedDtwAnalysisSnapshot | None = None
    ml_prediction: PersistedMlPredictionSnapshot | None = None


class PatientTestHistoryEntry(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "test_name": "finger-tapping",
                "date": "2026-07-02T19:20:30Z",
                "recording_file": "patient123_finger-tapping_2026-07-02_19-20-30.mov",
                "frame_count": 312,
                "fps": 30,
                "summary_available": True,
                "dtw": {
                    "session_id": "test-1776797714156",
                    "distance": 12.4,
                    "avg_step_cost": 0.21,
                    "similarity": 0.87,
                },
            }
        }
    )

    test_id: str | None = None
    test_name: str = Field(..., description="Canonical frontend/backend test name.")
    date: str = Field(..., description="UTC ISO-8601 timestamp.")
    recording_file: str | None = None
    frame_count: int | None = None
    fps: int | None = None
    summary_available: bool | None = None
    dtw: DtwMetricsSnapshot | None = None
    analysis: TestAnalysisSnapshot | None = None
    extra: Dict[str, Any] = Field(default_factory=dict, description="Additional stored metadata for the test record.")


class PatientTestHistoryResponse(BaseModel):
    success: bool
    tests: List[PatientTestHistoryEntry]


class SimpleSuccessResponse(BaseModel):
    success: bool


class UploadVideoResponse(BaseModel):
    success: bool
    filename: str | None = None
    path: str | None = None
    patient_id: str | None = None
    test_name: str | None = None
    session_id: str | None = None
    error: str | None = None


class VideoListResponse(BaseModel):
    success: bool
    videos: List[str] = Field(default_factory=list)
    error: str | None = None


_VIDEO_EXTENSIONS = (".mov", ".mp4", ".webm", ".avi", ".mkv")


def _password_matches(plain: str, stored: str) -> bool:
    try:
        return pwd.verify(plain, stored)
    except Exception:
        return plain == stored


def _should_rehash_password(stored: str) -> bool:
    if CryptContext is None:
        return False
    try:
        return pwd.needs_update(stored)
    except Exception:
        return True


def serialize_user(user: User) -> CurrentUserResponse:
    return CurrentUserResponse(
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        location=user.location,
        title=user.title,
        speciality=user.speciality,
    )


def normalize_test_history_entry(raw: Dict[str, Any]) -> PatientTestHistoryEntry:
    known_fields = {
        "test_id",
        "test_name",
        "date",
        "recording_file",
        "frame_count",
        "fps",
        "summary_available",
        "dtw",
        "analysis",
    }
    return PatientTestHistoryEntry(
        test_id=raw.get("test_id"),
        test_name=str(raw.get("test_name") or "unknown"),
        date=str(raw.get("date") or datetime.now(timezone.utc).isoformat()),
        recording_file=raw.get("recording_file"),
        frame_count=raw.get("frame_count"),
        fps=raw.get("fps"),
        summary_available=raw.get("summary_available"),
        dtw=raw.get("dtw"),
        analysis=raw.get("analysis"),
        extra={k: v for k, v in raw.items() if k not in known_fields},
    )


def ensure_demo_user() -> None:
    demo_username = "doctor@hospital.com"
    demo_password = "Demo123!"
    try:
        with SessionLocal() as session:
            existing = session.query(User).filter(
                (User.username == demo_username) | (User.email == demo_username)
            ).first()
            if existing:
                if not _password_matches(demo_password, existing.hashed_password) or _should_rehash_password(existing.hashed_password):
                    existing.hashed_password = pwd.hash(demo_password)
                    session.commit()
                return

            session.add(
                User(
                    username=demo_username,
                    full_name="Demo Doctor",
                    email=demo_username,
                    hashed_password=pwd.hash(demo_password),
                    location="Demo Clinic",
                    title="Neurologist",
                    speciality="Movement Disorders",
                )
            )
            session.commit()
    except Exception:
        # Keep app importable for docs/OpenAPI even when the optional bcrypt backend is unavailable.
        return


ensure_demo_user()

def authenticate(username: str, password: str) -> User | None:
    try:
        with SessionLocal() as session:
            user = session.query(User).filter(
                (User.username == username) | (User.email == username)
            ).first()
            if user and _password_matches(password, user.hashed_password):
                if _should_rehash_password(user.hashed_password):
                    user.hashed_password = pwd.hash(password)
                    session.commit()
                return user
    except Exception:
        return None
    
def create_access_token(sub: str) -> str:
    if jwt is None:
        return f"{_FALLBACK_TOKEN_PREFIX}{sub}"
    to_encode = {
        "sub": sub, 
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_MIN)
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGO)

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    if jwt is None:
        if not token.startswith(_FALLBACK_TOKEN_PREFIX):
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        username = token.removeprefix(_FALLBACK_TOKEN_PREFIX)
    else:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGO])
            username = payload.get("sub")
            if username is None:
                raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        except InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    with SessionLocal() as session:
        user = session.query(User).filter_by(username=username).first()
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return user
    
@app.post("/token", response_model=TokenResponse, tags=["auth"], summary="Create a bearer token")
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate(form.username, form.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = create_access_token(sub=user.username)
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/me", response_model=CurrentUserResponse, tags=["auth"], summary="Get the current authenticated user")
async def read_current_user(current_user: User = Depends(get_current_user)):
    return serialize_user(current_user)

# ============ REST: Health & Patients ============
@app.get("/", response_model=RootResponse, tags=["system"], summary="API root")
async def root():
    return {"message": "Welcome to the Patient Management API"}

@app.get("/health", response_model=HealthResponse, tags=["system"], summary="Health check")
async def health_check():
    return {"status": "healthy", "message": "API is running"}

# ============ REST: Test History ============
@app.get(
    "/patients/{patient_id}/tests",
    response_model=PatientTestHistoryResponse,
    tags=["test-history"],
    summary="Get stored test history for a patient",
)
async def get_patient_tests(patient_id: str):
    tests = load_patient_tests(patient_id)
    return {"success": True, "tests": [normalize_test_history_entry(test) for test in tests]}

@app.post(
    "/patients/{patient_id}/tests",
    response_model=SimpleSuccessResponse,
    tags=["test-history"],
    summary="Add a test history record for a patient",
)
async def add_patient_test(patient_id: str, test_data: PatientTestHistoryEntry = Body(...)):
    if not patient_exists(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    payload = test_data.model_dump(exclude_none=True)
    if payload.get("extra"):
        payload.update(payload.pop("extra"))
    append_patient_test(patient_id, payload)
    return {"success": True}



# ============ REST: Recordings ============
# ============ REST: Recordings ============
@app.post(
    "/upload-video/",
    response_model=UploadVideoResponse,
    tags=["recordings"],
    summary="Upload a processed video recording",
)
async def upload_video(
    patient_id: str = Form(...),
    test_name: str = Form(...),
    video: UploadFile = File(...)
):
    if not patient_exists(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        session_id = generate_session_id()
        filename = save_uploaded_video(
            patient_id=patient_id,
            test_name=test_name,
            upload_file=video.file,
            original_filename=video.filename,
            content_type=video.content_type,
            session_id=session_id,
        )

        append_patient_test(
            patient_id,
            build_uploaded_video_test_history_entry(
                test_name=test_name,
                session_id=session_id,
                recording_file=filename,
            ),
        )

        return {
            "success": True,
            "filename": filename,
            "path": f"recordings/{filename}",
            "patient_id": patient_id,
            "test_name": test_name,
            "session_id": session_id,
        }
    except Exception:
        logger.exception("Video upload failed")
        return {"success": False, "error": "Failed to upload video"}

@app.get(
    "/videos/{patient_id}/{test_name}",
    response_model=VideoListResponse,
    tags=["recordings"],
    summary="List saved recordings for a patient and test",
)
def list_videos(patient_id: str, test_name: str):
    try:
        normalized_target = normalize_test_name(test_name)
        seen: set[str] = set()

        # 1. Collect recording files from test history entries whose test_name matches
        for entry in load_patient_tests(patient_id):
            raw_test_name = entry.get("test_name") or ""
            if normalize_test_name(raw_test_name) != normalized_target:
                continue
            recording_file = entry.get("recording_file")
            if recording_file and recording_file.lower().endswith(_VIDEO_EXTENSIONS):
                try:
                    filepath = resolve_recording_path(recording_file)
                except ValueError:
                    continue
                if filepath.exists():
                    seen.add(recording_file)

        # 2. Fallback: filename pattern match for files not yet recorded in test history
        try:
            for f in os.listdir(RECORDINGS_DIR):
                if f in seen:
                    continue
                if f.startswith(f"{patient_id}_{test_name}_") and f.lower().endswith(_VIDEO_EXTENSIONS):
                    seen.add(f)
        except OSError:
            pass

        matching = sorted(
            seen,
            key=lambda f: os.path.getmtime(resolve_recording_path(f)),
            reverse=True,
        )
        return {"success": True, "videos": matching}
    except Exception:
        logger.exception("Listing videos failed")
        return {"success": False, "error": "Failed to list videos"}

@app.get("/recordings/{filename}", response_class=FileResponse)
def get_recording_file(filename: str):
    try:
        file_path = resolve_recording_path(filename)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Video not found") from exc
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    suffix = file_path.suffix.lower()
    if suffix == ".webm":
        media_type = "video/webm"
    elif suffix == ".mov":
        media_type = "video/quicktime"
    else:
        media_type = "video/mp4"
    return FileResponse(str(file_path), media_type=media_type)

# ============ Uvicorn ============
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
