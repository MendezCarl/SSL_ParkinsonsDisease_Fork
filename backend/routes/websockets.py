from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

import os
import base64
import json
from datetime import datetime
from pathlib import Path
import uuid


import numpy as np
from typing import List, Optional, Dict
from routes.utils_dtw import EndOnlyDTW, normalize_test_name
from storage_paths import RECORDINGS_DIR

from patient_manager import (
    TestHistoryManager
)
from fastapi import APIRouter

router = APIRouter(prefix="/ws", tags=["websockets"])

RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# Resolve model files relative to this file: backend/models/
_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
_HAND_MODEL  = str(_MODELS_DIR / "hand_landmarker.task")
_POSE_MODEL  = str(_MODELS_DIR / "pose_landmarker_lite.task")


def _cv2():
    try:
        import cv2
        return cv2
    except Exception as e:
        raise RuntimeError(
            "OpenCV not available. Install opencv-python-headless."
        ) from e


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
    if not frames:
        raise ValueError("No frames to save.")

    cv2 = _cv2()
    h, w = frames[0].shape[:2]

    recording_id = str(uuid.uuid4())
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"ws_recording_{ts}_{recording_id}.mp4"
    path = RECORDINGS_DIR / filename

    # Try H.264 first, fall back to mp4v if unavailable
    for fourcc_str in ("avc1", "H264", "mp4v"):
        fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
        writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
        if writer.isOpened():
            print("Using fourcc:", fourcc_str)
            break
    else:
        raise RuntimeError("Could not open VideoWriter with any codec")

    for f in frames:
        writer.write(f)
    writer.release()
    return filename


# ============ MediaPipe extractor (Tasks API — mediapipe >= 0.10) ============
class MPExtractor:
    """Create once per WebSocket connection. Uses the MediaPipe Tasks API."""

    def __init__(self, model: str = "hands"):
        self.model = model
        import mediapipe as mp
        import mediapipe.tasks as mp_tasks
        vision = mp_tasks.vision

        if model == "hands":
            if not Path(_HAND_MODEL).exists():
                raise FileNotFoundError(
                    f"Hand landmarker model not found at {_HAND_MODEL}. "
                    "Run: curl -L https://storage.googleapis.com/mediapipe-models/"
                    "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task "
                    f"-o {_HAND_MODEL}"
                )
            options = vision.HandLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(model_asset_path=_HAND_MODEL),
                running_mode=vision.RunningMode.IMAGE,
                num_hands=2,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.solution = vision.HandLandmarker.create_from_options(options)

        elif model == "pose":
            if not Path(_POSE_MODEL).exists():
                raise FileNotFoundError(
                    f"Pose landmarker model not found at {_POSE_MODEL}. "
                    "Run: curl -L https://storage.googleapis.com/mediapipe-models/"
                    "pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task "
                    f"-o {_POSE_MODEL}"
                )
            options = vision.PoseLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(model_asset_path=_POSE_MODEL),
                running_mode=vision.RunningMode.IMAGE,
                num_poses=1,
                min_pose_detection_confidence=0.5,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.solution = vision.PoseLandmarker.create_from_options(options)

        else:
            self.solution = None

    def process(self, frame_bgr: np.ndarray) -> dict:
        if self.solution is None:
            return {"error": f"Unsupported model {self.model}"}

        import mediapipe as mp
        import mediapipe.tasks as mp_tasks
        vision = mp_tasks.vision
        cv2 = _cv2()

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        if self.model == "hands":
            result = self.solution.detect(mp_image)
            out: dict = {"model": "hands", "hands": []}
            if result.hand_landmarks:
                for i, hand_lm in enumerate(result.hand_landmarks):
                    pts = [{"x": lm.x, "y": lm.y, "z": lm.z} for lm in hand_lm]
                    handedness = None
                    if result.handedness and i < len(result.handedness):
                        handedness = result.handedness[i][0].category_name
                    out["hands"].append({"landmarks": pts, "handedness": handedness})
            return out

        elif self.model == "pose":
            result = self.solution.detect(mp_image)
            out = {"model": "pose", "pose": []}
            if result.pose_landmarks:
                lm_list = result.pose_landmarks[0]
                pts = [
                    {"x": lm.x, "y": lm.y, "z": lm.z,
                     "v": lm.visibility if hasattr(lm, "visibility") else 0.0}
                    for lm in lm_list
                ]
                out["pose"] = pts
            return out

        return {"error": "Unknown model"}

    def close(self) -> None:
        if self.solution is not None:
            try:
                self.solution.close()
            except Exception:
                pass
            self.solution = None




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
    finally:
        if mp_extractor is not None:
            mp_extractor.close()


# Primary WS endpoint: ws://.../ws/{client_id}
@router.websocket("/{client_id}")
async def ws_client(websocket: WebSocket, client_id: str):
    await _camera_ws_handler(websocket)

@router.websocket("/camera")
async def ws_camera(websocket: WebSocket):
    await _camera_ws_handler(websocket)

@router.get("/test")
async def test_ws():
    return{"message": "WebSocket endpoint is at /ws/{client_id} or /ws/camera"}
