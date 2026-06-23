from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Body, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Dict, List, Optional, Annotated
from datetime import datetime, timedelta
import os
import shutil
import uvicorn
from pydantic import BaseModel

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

app = FastAPI(title="Patient Management API")
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

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class CurrentUserResponse(BaseModel):
    username: str
    full_name: str
    email: str | None = None
    location: str
    title: str
    speciality: str


def serialize_user(user: User) -> CurrentUserResponse:
    return CurrentUserResponse(
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        location=user.location,
        title=user.title,
        speciality=user.speciality,
    )


def ensure_demo_user() -> None:
    demo_username = "doctor@hospital.com"
    demo_password = "Demo123!"
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
        "exp": datetime.now() + timedelta(minutes=ACCESS_MIN)
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
    
@app.post("/token")
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate(form.username, form.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = create_access_token(sub=user.username)
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/me", response_model=CurrentUserResponse)
async def read_current_user(current_user: User = Depends(get_current_user)):
    return serialize_user(current_user)

# ============ REST: Health & Patients ============
@app.get("/")
async def root():
    return {"message": "Welcome to the Patient Management API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "API is running"}

# ============ REST: Test History ============
@app.get("/patients/{patient_id}/tests", response_model=Dict)
async def get_patient_tests(patient_id: str):
    thm = TestHistoryManager()
    tests = thm.get_patient_tests(patient_id)
    return {"success": True, "tests": tests}

@app.post("/patients/{patient_id}/tests", response_model=Dict)
async def add_patient_test(patient_id: str, test_data: dict = Body(...)):
    thm = TestHistoryManager()
    thm.add_patient_test(patient_id, test_data)
    return {"success": True}



# ============ REST: Recordings ============
# ============ REST: Recordings ============
@app.post("/upload-video/")
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

@app.get("/videos/{patient_id}/{test_name}", response_model=Dict)
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
