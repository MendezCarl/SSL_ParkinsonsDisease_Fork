from fastapi import WebSocket, WebSocketDisconnect
import base64
import json
from datetime import datetime
from pathlib import Path


import numpy as np
from typing import List, Optional, Dict, Any
from schema.keypoint_contracts import build_hand_payload, build_pose_payload
from services.dtw_service import dtw_service
from services.recording_service import save_frames_to_mp4
from services.test_history_service import append_patient_test, build_completed_test_history_entry, patient_exists
from fastapi import APIRouter

router = APIRouter(prefix="/ws", tags=["websockets"])

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
            hands: list[list[dict[str, float]]] = []
            labels: list[str | None] = []
            if result.hand_landmarks:
                for i, hand_lm in enumerate(result.hand_landmarks):
                    pts = [{"x": lm.x, "y": lm.y, "z": lm.z} for lm in hand_lm]
                    handedness = None
                    if result.handedness and i < len(result.handedness):
                        handedness = result.handedness[i][0].category_name
                    hands.append(pts)
                    labels.append(handedness)
            return build_hand_payload(hands, labels)

        elif self.model == "pose":
            result = self.solution.detect(mp_image)
            if result.pose_landmarks:
                lm_list = result.pose_landmarks[0]
                pts = [
                    {
                        "x": lm.x,
                        "y": lm.y,
                        "z": lm.z,
                        "visibility": lm.visibility if hasattr(lm, "visibility") else 0.0,
                    }
                    for lm in lm_list
                ]
                return build_pose_payload(pts)
            return build_pose_payload([])

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
    client_test_id: Optional[str] = None
    session_id: Optional[str] = None
    model: str = "hands"      # "hands" | "pose"
    started: bool = False

    mp_extractor: Optional[MPExtractor] = None
    dtw_end: Optional[Any] = None

    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            mtype = data.get("type")

            if mtype == "init":
                try:
                    patient_id = data.get("patientId") or data.get("patient_id")
                    if not patient_id or not patient_exists(patient_id):
                        raise ValueError("Patient not found")
                    raw_test = data.get("testType") or data.get("test_name")
                    test_name = dtw_service.normalize_test_name(raw_test)
                    model = data.get("model", model)                   # "hands" | "pose"
                    fps_hint = float(data.get("fps", fps_hint))
                    client_test_id = data.get("testId")
                    session_id = dtw_service.new_session_id()
                    mp_extractor = MPExtractor(model=model)
                    dtw_end = dtw_service.create_live_session(test_name or "unknown", model, session_id)

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
                        "testId": client_test_id,
                        "sessionId": session_id,
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
                        "sessionId": session_id,
                        "model": model,
                    })
                else:
                    await websocket.send_json({
                        "type": "dtw_saved",
                        "patientId": patient_id,
                        "testName": test_name,
                        "sessionId": payload.get("session_id") or session_id,
                        "artifacts": payload.get("artifacts"),
                        "distance": payload.get("distance"),
                        "avgStepCost": payload.get("avg_step_cost"),
                        "similarity": payload.get("similarity_overall"),
                        "similarityPos": payload.get("similarity_pos"),
                        "similarityAmp": payload.get("similarity_amp"),
                        "similaritySpd": payload.get("similarity_spd"),
                    })

                # Save MP4 & history
                try:
                    saved_name = save_frames_to_mp4(
                        frames,
                        fps=fps_hint,
                        patient_id=patient_id,
                        test_name=test_name,
                        session_id=session_id,
                    )
                except Exception as e:
                    await websocket.send_json({"type": "error", "where": "save_mp4", "message": f"{e}"})
                    frames = []
                    continue

                try:
                    entry = build_completed_test_history_entry(
                        test_name=test_name or "unknown",
                        session_id=payload.get("session_id") or session_id or client_test_id or "unknown",
                        recording_file=saved_name,
                        frame_count=len(frames),
                        fps=fps_hint,
                        similarity=payload.get("similarity_overall") if payload.get("ok") else None,
                        similarity_pos=payload.get("similarity_pos") if payload.get("ok") else None,
                        similarity_amp=payload.get("similarity_amp") if payload.get("ok") else None,
                        similarity_spd=payload.get("similarity_spd") if payload.get("ok") else None,
                        distance=payload.get("distance") if payload.get("ok") else None,
                        avg_step_cost=payload.get("avg_step_cost") if payload.get("ok") else None,
                        model=model,
                        artifacts=payload.get("artifacts") if payload.get("ok") else None,
                    )
                    append_patient_test(patient_id or "unknown", entry)
                except Exception:
                    pass

                await websocket.send_json({
                    "type": "complete",
                    "sessionId": payload.get("session_id") or session_id,
                    "recording": saved_name,
                    "path": f"recordings/{saved_name}",
                    "frame_count": len(frames),
                    "patientId": patient_id,
                    "testName": test_name,
                    "fps": fps_hint,
                    "summaryAvailable": bool(payload.get("ok")),
                    "dtw": {
                        "session_id": payload.get("session_id") or session_id,
                        "distance": payload.get("distance") if payload.get("ok") else None,
                        "avg_step_cost": payload.get("avg_step_cost") if payload.get("ok") else None,
                        "similarity": payload.get("similarity_overall") if payload.get("ok") else None,
                        "artifacts": payload.get("artifacts") if payload.get("ok") else None,
                    },
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
