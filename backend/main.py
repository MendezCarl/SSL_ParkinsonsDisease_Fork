from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Body, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Any, Dict, List, Optional, Annotated
from datetime import datetime, timedelta, timezone
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
from repo.db import engine
from jose import jwt, JWTError
from passlib.context import CryptContext
from patient_manager import SessionLocal

# ============ Paths / Folders ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDINGS_DIR = os.path.join(BASE_DIR, "routes", "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# ============ Lazy imports (avoid libGL issues on boot) ============

# ============ Patient Manager ============
from patient_manager import (
    TestHistoryManager
)

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
    error: str | None = None


class VideoListResponse(BaseModel):
    success: bool
    videos: List[str] = Field(default_factory=list)
    error: str | None = None


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
    }
    return PatientTestHistoryEntry(
        test_id=raw.get("test_id"),
        test_name=str(raw.get("test_name") or "unknown"),
        date=str(raw.get("date") or datetime.utcnow().isoformat()),
        recording_file=raw.get("recording_file"),
        frame_count=raw.get("frame_count"),
        fps=raw.get("fps"),
        summary_available=raw.get("summary_available"),
        dtw=raw.get("dtw"),
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
            if user and pwd.verify(password, user.hashed_password):
                return user
    except Exception as e:
        return {"error": "Failed to auth"}
    
def create_access_token(sub: str) -> str:
    to_encode = {
        "sub": sub, 
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_MIN)
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGO)

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGO])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    except JWTError:
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
    thm = TestHistoryManager()
    tests = thm.get_patient_tests(patient_id)
    return {"success": True, "tests": [normalize_test_history_entry(test) for test in tests]}

@app.post(
    "/patients/{patient_id}/tests",
    response_model=SimpleSuccessResponse,
    tags=["test-history"],
    summary="Add a test history record for a patient",
)
async def add_patient_test(patient_id: str, test_data: PatientTestHistoryEntry = Body(...)):
    thm = TestHistoryManager()
    payload = test_data.model_dump(exclude_none=True)
    if payload.get("extra"):
        payload.update(payload.pop("extra"))
    thm.add_patient_test(patient_id, payload)
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
    try:
        now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{patient_id}_{test_name}_{now_str}.mov"
        filepath = os.path.join(RECORDINGS_DIR, filename)

        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)

        return {
            "success": True,
            "filename": filename,
            "path": f"recordings/{filename}",
            "patient_id": patient_id,
            "test_name": test_name
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get(
    "/videos/{patient_id}/{test_name}",
    response_model=VideoListResponse,
    tags=["recordings"],
    summary="List saved recordings for a patient and test",
)
def list_videos(patient_id: str, test_name: str):
    try:
        files = os.listdir(RECORDINGS_DIR)
        matching = [
            f for f in files
            if f.startswith(f"{patient_id}_{test_name}_") and (f.endswith(".mov") or f.endswith(".mp4"))
        ]
        matching.sort(
            key=lambda f: os.path.getmtime(os.path.join(RECORDINGS_DIR, f)),
            reverse=True
        )
        return {"success": True, "videos": matching}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/recordings/{filename}", response_class=FileResponse)
def get_recording_file(filename: str):
    file_path = os.path.join(RECORDINGS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Video not found")
    media_type = "video/mp4" if filename.endswith(".mp4") else "video/quicktime"
    return FileResponse(file_path, media_type=media_type)

# ============ Uvicorn ============
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
