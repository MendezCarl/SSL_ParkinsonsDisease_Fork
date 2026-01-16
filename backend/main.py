from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Body, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import os
import shutil
import mimetypes
import uvicorn
from subprocess import run, PIPE
import uuid
import json
import base64
import numpy as np
from tslearn.metrics import dtw_path
from uuid import uuid4
from dtw_rest import router as dtw_router
from utils_dtw import EndOnlyDTW, normalize_test_name

from pathlib import Path




# ============ Paths / Folders ============
RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# ============ Lazy imports (avoid libGL issues on boot) ============
def _cv2():
    try:
        import cv2
        return cv2
    except Exception as e:
        raise RuntimeError(
            "OpenCV not available. Install opencv-python-headless."
        ) from e

def _mp():
    try:
        import mediapipe as mp
        return mp
    except Exception as e:
        raise RuntimeError(
            "MediaPipe not available. Install mediapipe.", e
        ) from e

# ============ Patient Manager ============
from patient_manager import (
    Patient, PatientManager,
    async_create_patient, async_get_patient_info,
    async_update_patient_info, async_delete_patient_record,
    async_get_all_patients_info, async_search_patients,
    async_filter_patients,
    TestHistoryManager
)

app = FastAPI(title="Patient Management API")
app.include_router(dtw_router)

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

# ============ Models ============
class PatientCreate(BaseModel):
    name: str
    # age: int = Field(..., ge=0, le=120)
    birthDate: str  # Add this line
    height: str = Field(..., min_length=1)
    weight: str = Field(..., min_length=1)
    lab_results: Optional[Dict] = Field(default_factory=dict)
    doctors_notes: Optional[str] = ""
    severity: str = Field(
        "Stage 1",
        pattern="^(low|medium|high|mild|moderate|severe|stage [1-5])$"
    )


class PatientUpdate(BaseModel):
    name: Optional[str] = None
    # age: Optional[int] = Field(None, ge=0, le=120)
    birthDate: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    lab_results: Optional[Dict] = None
    lab_results_history: Optional[List[Dict]] = None
    doctors_notes: Optional[str] = None
    doctors_notes_history: Optional[List[Dict]] = None
    severity: Optional[str] = Field(
        None,
        pattern="^(low|medium|high|mild|moderate|severe|stage [1-5])$"
    )

class PatientResponse(BaseModel):
    patient_id: str
    name: str
    birthDate: str
    height: str  # Changed to str to handle existing data
    weight: str  # Changed to str to handle existing data
    lab_results: Dict
    doctors_notes: str
    severity: str
    lab_results_history: Optional[List[Dict]] = []
    doctors_notes_history: Optional[List[Dict]] = []

class PatientsListResponse(BaseModel):
    success: bool
    patients: List[PatientResponse]
    total: int
    skip: int
    limit: int

class PatientSearchResponse(BaseModel):
    success: bool
    patients: List[PatientResponse]
    count: int

class FilterCriteria(BaseModel):
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    severity: Optional[str] = None

# ============ Media helpers ============
def _decode_base64_image(data_str: str) -> np.ndarray:
    """Accepts 'data:*;base64,...' or raw base64 and returns BGR frame."""
    if "," in data_str:
        b64 = data_str.split(",", 1)[1]
    else:
        b64 = data_str
    img_bytes = base64.b64decode(b64)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    cv2 = _cv2()
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Could not decode frame from provided data.")
    return frame

def _save_frames_to_mp4(frames: List[np.ndarray], fps: float = 30.0) -> str:
    """Saves frames to MP4 and returns the filename (inside RECORDINGS_DIR)."""
    if not frames:
        raise ValueError("No frames to save.")
    cv2 = _cv2()
    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    recording_id = str(uuid.uuid4())
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"ws_recording_{ts}_{recording_id}.mp4"
    path = os.path.join(RECORDINGS_DIR, filename)
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    for f in frames:
        writer.write(f)
    writer.release()
    return filename

# ============ MediaPipe extractor ============
class MPExtractor:
    """Create once per WebSocket connection to reuse Mediapipe graph."""
    def __init__(self, model: str = "hands"):
        self.model = model
        mp = _mp()
        if model == "hands":
            self.solution = mp.solutions.hands.Hands(
                static_image_mode=False, max_num_hands=2,
                min_detection_confidence=0.5, min_tracking_confidence=0.5
            )
        elif model == "pose":
            self.solution = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                enable_segmentation=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        else:
            self.solution = None

    def process(self, frame_bgr):
        if self.solution is None:
            return {"error": f"Unsupported model {self.model}"}
        cv2 = _cv2()
        mp = _mp()
        # MediaPipe expects RGB
        results = self.solution.process(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))

        if self.model == "hands":
            out = {"model": "hands", "hands": []}
            if getattr(results, "multi_hand_landmarks", None):
                handed = []
                if getattr(results, "multi_handedness", None):
                    handed = [h.classification[0].label for h in results.multi_handedness]
                for i, lm in enumerate(results.multi_hand_landmarks):
                    pts = [{"x": p.x, "y": p.y, "z": p.z} for p in lm.landmark]
                    out["hands"].append({
                        "landmarks": pts,
                        "handedness": handed[i] if i < len(handed) else None
                    })
            return out

        elif self.model == "pose":
            out = {"model": "pose", "pose": []}
            if getattr(results, "pose_landmarks", None):
                lm = results.pose_landmarks.landmark
                pts = [{"x": p.x, "y": p.y, "z": p.z, "v": getattr(p, "visibility", 0.0)} for p in lm]
                out["pose"] = pts
            return out

        return {"error": "Unknown model"}
    



# ============ WebSocket handler ============
async def _camera_ws_handler(websocket: WebSocket):
    await websocket.accept()

    frames: List[np.ndarray] = []
    fps_hint: float = 30.0
    patient_id: Optional[str] = None
    test_name: Optional[str] = None
    test_id: Optional[str] = None
    model: str = "hands"      # "hands" | "pose"
    started: bool = False

    mp_extractor: Optional[MPExtractor] = None
    dtw_end: Optional[EndOnlyDTW] = None

    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            mtype = data.get("type")

            if mtype == "init":
                try:
                    patient_id = data.get("patientId") or data.get("patient_id")
                    raw_test = data.get("testType") or data.get("test_name")
                    test_name = normalize_test_name(raw_test)          # canonicalize
                    model = data.get("model", model)                   # "hands" | "pose"
                    fps_hint = float(data.get("fps", fps_hint))
                    test_id = data.get("testId")     # unique per test run
                    mp_extractor = MPExtractor(model=model)
                    dtw_end = EndOnlyDTW(test_name or "unknown", model, test_id)

                    # Surface template init errors immediately
                    if getattr(dtw_end, "init_error", None):
                        await websocket.send_json({
                            "type": "error",
                            "where": "init",
                            "message": dtw_end.init_error,
                            "testName": test_name,
                            "model": model
                        })

                    started = True
                    await websocket.send_json({
                        "type": "status",
                        "status": "initialized",
                        "patientId": patient_id,
                        "testName": test_name,  # canonical test
                        "model": model,
                        "fps": fps_hint
                    })
                except Exception as e:
                    started = False
                    await websocket.send_json({"type": "error", "where": "init", "message": str(e)})

            elif mtype == "frame":
                try:
                    if not started or not mp_extractor:
                        await websocket.send_json({"type": "error", "where": "frame", "message": "Not initialized"})
                        continue

                    frame = _decode_base64_image(data["data"])
                    frames.append(frame)

                    kp = mp_extractor.process(frame)
                    if dtw_end and "error" not in kp:
                        dtw_end.push(kp)

                    resp = {"type": "keypoints", "model": model, "frame_idx": len(frames)}
                    resp.update(kp)
                    await websocket.send_json(resp)

                except Exception as e:
                    await websocket.send_json({"type": "error", "where": "frame", "message": f"{e}"})

            elif mtype == "pause":
                paused = bool(data.get("paused", False))
                await websocket.send_json({
                    "type": "status",
                    "status": "paused" if paused else "resumed"
                })

            elif mtype == "end":
                if not started:
                    await websocket.send_json({"type": "error", "where": "end", "message": "Test not initialized"})
                    continue
                if not frames:
                    await websocket.send_json({"type": "error", "where": "end", "message": "No frames received"})
                    continue
                if not dtw_end:
                    await websocket.send_json({"type": "error", "where": "end", "message": "DTW not initialized"})
                    continue

                # Finalize DTW (returns ok=False with details if it couldn't save)
                payload = dtw_end.finalize_and_save(meta_sidecar={"patientId": patient_id, "fps": fps_hint})
                if not payload.get("ok"):
                    await websocket.send_json({
                        "type": "dtw_error",
                        **payload,
                        "testName": test_name,
                        "model": model,
                    })
                else:
                    await websocket.send_json({"type": "dtw_saved", **payload})

                # Save MP4 & history (optional)
                try:
                    saved_name = _save_frames_to_mp4(frames, fps=fps_hint)
                except Exception as e:
                    await websocket.send_json({"type": "error", "where": "save_mp4", "message": f"{e}"})
                    frames = []
                    continue

                try:
                    thm = TestHistoryManager()
                    thm.add_patient_test(patient_id or "unknown", {
                        "test_name": test_name or "unknown",
                        "date": datetime.utcnow().isoformat(),
                        "recording_file": saved_name,
                        "frame_count": len(frames)
                    })
                except Exception:
                    pass

                await websocket.send_json({
                    "type": "complete",
                    "recording": saved_name,
                    "path": f"recordings/{saved_name}",
                    "frame_count": len(frames),
                    "patientId": patient_id,
                    "testName": test_name
                })
                frames = []

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown message: {data}"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass


# Primary WS endpoint: ws://.../ws/{client_id}
@app.websocket("/ws/{client_id}")
async def ws_client(websocket: WebSocket, client_id: str):
    await _camera_ws_handler(websocket)

@app.websocket("/ws/camera")
async def ws_camera(websocket: WebSocket):
    await _camera_ws_handler(websocket)

# ============ REST: Health & Patients ============
@app.get("/")
async def root():
    return {"message": "Welcome to the Patient Management API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "API is running"}

@app.post("/patients/", response_model=Dict)
async def create_patient(patient: PatientCreate):
    try:
        height = float(patient.height) if patient.height is not None else 0.0
    except ValueError:
        height = 0.0
    try:
        weight = float(patient.weight) if patient.weight is not None else 0.0
    except ValueError:
        weight = 0.0

    lab_results = patient.lab_results if patient.lab_results is not None else {}
    doctors_notes = patient.doctors_notes if patient.doctors_notes is not None else ""
    result = await async_create_patient(
        name=patient.name,
        # age=patient.age,  # Add this line
        birthDate=patient.birthDate,
        height=height,
        weight=weight,
        lab_results=lab_results,
        doctors_notes=doctors_notes,
        severity=patient.severity
    )

    if not result.get("success", False):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to create patient"))

    return result

@app.get("/patients/", response_model=PatientsListResponse)
async def get_patients(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000)
):
    return await async_get_all_patients_info(skip, limit)

@app.get("/patients/{patient_id}", response_model=Dict)
async def get_patient(patient_id: str):
    result = await async_get_patient_info(patient_id)

    if not result.get("success", False):
        raise HTTPException(status_code=404, detail="Patient not found")

    return result

@app.put("/patients/{patient_id}", response_model=Dict)
async def update_patient(patient_id: str, patient_update: PatientUpdate):
    update_data = {k: v for k, v in patient_update.dict().items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="No valid update data provided")

    result = await async_update_patient_info(patient_id, update_data)

    if not result.get("success", False):
        if "errors" in result:
            raise HTTPException(status_code=400, detail=result["errors"])
        raise HTTPException(status_code=404, detail=result.get("error", "Failed to update patient"))

    return result

@app.delete("/patients/{patient_id}", response_model=Dict)
async def delete_patient(patient_id: str):
    result = await async_delete_patient_record(patient_id)

    if not result.get("success", False):
        raise HTTPException(status_code=404, detail="Patient not found")

    return result

@app.get("/patients/search/{query}", response_model=PatientSearchResponse)
async def search_patients_endpoint(query: str):
    return await async_search_patients(query)

@app.post("/patients/filter/", response_model=PatientSearchResponse)
async def filter_patients_endpoint(criteria: FilterCriteria):
    return await async_filter_patients(criteria.dict(exclude_none=True))

# ============ REST: Recordings ============
@app.post("/upload-video/")
async def upload_video(
    patient_id: str = Form(...),
    test_name: str = Form(...),
    video: UploadFile = File(...)
):
    try:
        canonical_test = normalize_test_name(test_name) or "unknown"
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        original_suffix = Path(getattr(video, "filename", "") or "").suffix.lower()
        allowed_suffixes = {".mp4", ".mov", ".webm", ".mkv"}
        suffix = original_suffix if original_suffix in allowed_suffixes else ".webm"

        filename = f"{patient_id}_{canonical_test}_{timestamp}{suffix}"
        filepath = os.path.join(RECORDINGS_DIR, filename)

        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)

        message = f"Video saved to {filepath}"
        print(f"[upload_video] patient={patient_id} test={canonical_test} file={filepath}")

        return {
            "success": True,
            "filename": filename,
            "path": f"recordings/{filename}",
            "disk_path": filepath,
            "patient_id": patient_id,
            "test_name": canonical_test,
            "message": message,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/videos/{patient_id}/{test_name}", response_model=Dict)
def list_videos(patient_id: str, test_name: str):
    try:
        canonical_test = normalize_test_name(test_name) or test_name
        files = os.listdir(RECORDINGS_DIR)
        matching = []
        for f in files:
            if not f.lower().endswith((".mov", ".mp4", ".webm", ".mkv")):
                continue
            if not f.startswith(f"{patient_id}_"):
                continue
            remainder = f[len(patient_id) + 1:]
            test_segment = remainder.split("_", 1)[0]
            if normalize_test_name(test_segment) == canonical_test:
                matching.append(f)
            elif canonical_test in f:
                matching.append(f)
        matching.sort(
            key=lambda fname: os.path.getmtime(os.path.join(RECORDINGS_DIR, fname)),
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
    media_type, _ = mimetypes.guess_type(file_path)
    if not media_type:
        media_type = "application/octet-stream"
    return FileResponse(file_path, media_type=media_type)

# ============ REST: Start Scripts ============
@app.post("/start-test/")
async def start_test(patient_id: str = Form(...), test_name: str = Form(...)):
    """
    Start a test by running the appropriate script based on test_name.
    Returns output or error from the script.
    """
    script_map = {
        "finger-tapping": os.path.join(os.path.dirname(__file__), "finger_tapping.py"),
        "fist-open-close": os.path.join(os.path.dirname(__file__), "fist_open_close.py"),
    }
    script_path = script_map.get(test_name)
    if not script_path or not os.path.exists(script_path):
        return {"success": False, "error": f"Unknown or missing script for test: {test_name}"}

    try:
        result = run(["python", script_path], stdout=PIPE, stderr=PIPE, text=True, check=False)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

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

# ============ Uvicorn ============
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
