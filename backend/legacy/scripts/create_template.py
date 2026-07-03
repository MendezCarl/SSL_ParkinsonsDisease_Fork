#!/usr/bin/env python3
"""
create_template.py
Record a template sequence from webcam and save features to templates/<test>/<model>.npz

Usage examples:
  python create_template.py --test finger-tapping --model hands
  python create_template.py --test fist-open-close --model hands
  python create_template.py --test stand-and-sit --model pose --use-z
Keys:
  r = toggle recording on/off
  q = finish and save
"""

import os, sys, time, argparse
from datetime import datetime
import numpy as np
import cv2
import mediapipe as mp

# -------------------- Feature extraction --------------------
def hands_features(lm) -> np.ndarray | None:
    """
    FULL Mediapipe hands (21 landmarks) -> 42D feature.
    Origin = wrist (0). Scale = distance wrist(0) -> middle MCP(9).
    """
    if lm is None or len(lm.landmark) < 21:
        return None
    pts = np.array([[p.x, p.y] for p in lm.landmark], dtype=np.float32)  # (21,2)
    ref = pts[0]                                  # wrist
    rel = pts - ref                               # translation-invariant
    scale = np.linalg.norm(pts[9] - ref) + 1e-6   # wrist->middle MCP
    return (rel / scale).reshape(-1)              # (42,)

def pose_features(lm, use_z: bool = False) -> np.ndarray | None:
    # lm: mp.framework.formats.landmark_pb2.NormalizedLandmarkList for pose (33 required)
    if lm is None or len(lm.landmark) < 33:
        return None
    if use_z:
        pts = np.array([[p.x, p.y, p.z] for p in lm.landmark], dtype=np.float32)  # (33,3)
        mid_hips = (pts[23] + pts[24]) / 2.0
        rel = pts - mid_hips
        shoulder_w = np.linalg.norm(pts[11] - pts[12]) + 1e-6
        return (rel / shoulder_w).reshape(-1)  # (99,)
    else:
        pts = np.array([[p.x, p.y] for p in lm.landmark], dtype=np.float32)       # (33,2)
        mid_hips = (pts[23] + pts[24]) / 2.0
        rel = pts - mid_hips
        shoulder_w = np.linalg.norm(pts[11] - pts[12]) + 1e-6
        return (rel / shoulder_w).reshape(-1)  # (66,)

def extract_features(model: str, results, use_z: bool = False) -> np.ndarray | None:
    if model == "hands":
        # choose first detected hand
        if getattr(results, "multi_hand_landmarks", None):
            return hands_features(results.multi_hand_landmarks[0])
        return None
    elif model == "pose":
        return pose_features(getattr(results, "pose_landmarks", None), use_z=use_z)
    return None

# -------------------- Drawing helpers --------------------
mp_drawing = mp.solutions.drawing_utils
mp_styles = mp.solutions.drawing_styles

def draw_overlays(image_bgr, model: str, results, recording: bool):
    if model == "hands":
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(
                    image_bgr, hand_landmarks, mp.solutions.hands.HAND_CONNECTIONS,
                    mp_styles.get_default_hand_landmarks_style(),
                    mp_styles.get_default_hand_connections_style()
                )
    else:  # pose
        if results.pose_landmarks:
            mp_drawing.draw_landmarks(
                image_bgr, results.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS,
                landmark_drawing_spec=mp_styles.get_default_pose_landmarks_style()
            )
    # HUD
    status = "REC" if recording else "PAUSED"
    color = (0,0,255) if recording else (128,128,128)
    cv2.rectangle(image_bgr, (10,10), (120,50), (0,0,0), -1)
    cv2.putText(image_bgr, status, (20,42), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2, cv2.LINE_AA)

# -------------------- Main capture & save --------------------
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def normalize_test_name(t: str) -> str:
    t = t.strip().lower()
    if t == "finger-taping":  # tolerate typo
        t = "finger-tapping"
    return t

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", required=True,
                    choices=["finger-tapping","finger-taping","fist-open-close","stand-and-sit"],
                    help="Which test this template is for")
    ap.add_argument("--model", required=True, choices=["hands","pose"], help="MediaPipe model to use")
    ap.add_argument("--use-z", action="store_true", help="Include z for pose (33x3 -> 99 dims)")
    ap.add_argument("--device", type=int, default=0, help="Webcam index")
    ap.add_argument("--outdir", default="templates", help="Root directory to save template npz")
    ap.add_argument("--fps", type=float, default=30.0, help="Target capture FPS (soft)")
    ap.add_argument("--keep-every", type=int, default=1, help="Keep 1 of every N frames for the template")
    ap.add_argument("--preview-width", type=int, default=960, help="Preview window width")
    args = ap.parse_args()

    test_name = normalize_test_name(args.test)
    model = args.model
    use_z = bool(args.use_z)

    # Setup output path
    out_dir = os.path.join(args.outdir, test_name)
    ensure_dir(out_dir)
    out_path = os.path.join(out_dir, f"{model}.npz")

    # MediaPipe setup
    mp_hands = mp.solutions.hands
    mp_pose  = mp.solutions.pose

    if model == "hands":
        solution = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
    else:
        solution = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

    cap = cv2.VideoCapture(args.device)
    if not cap.isOpened():
        print("ERROR: Could not open webcam.", file=sys.stderr)
        sys.exit(1)

    print("Controls: 'r' = toggle record, 'q' = finish & save.")
    X = []
    recording = False
    frame_idx = 0
    t_last = time.time()
    dt_target = 1.0/max(1e-3, args.fps)

    try:
        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                print("WARN: Frame grab failed, exiting.")
                break

            # throttle FPS
            now = time.time()
            if now - t_last < dt_target:
                # small sleep helps CPU
                time.sleep(max(0.0, dt_target - (now - t_last)))
            t_last = time.time()

            # MediaPipe expects RGB
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            results = solution.process(frame_rgb)

            # Optionally collect features
            if recording:
                # downsample by keep_every
                if (frame_idx % max(1, args.keep_every)) == 0:
                    feat = extract_features(model, results, use_z=use_z)
                    if feat is not None:
                        X.append(feat)

            # Visualization
            vis = frame_bgr.copy()
            draw_overlays(vis, model, results, recording)
            # resize preview
            h, w = vis.shape[:2]
            scale = args.preview_width / float(w)
            vis = cv2.resize(vis, (int(w*scale), int(h*scale)))
            cv2.imshow("Template Capture", vis)

            # keyboard
            key = cv2.waitKey(1) & 0xFF
            if key == ord('r'):
                recording = not recording
                print("Recording:", recording)
            elif key == ord('q'):
                print("Finishing and saving...")
                break

            frame_idx += 1

    finally:
        cap.release()
        cv2.destroyAllWindows()
        solution.close()

    if not X:
        print("No features collected; nothing saved.")
        return

    X = np.stack(X, axis=0).astype(np.float32)  # (T, D)
    # Also archive a timestamped copy for provenance
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    archive_dir = os.path.join(out_dir, "_captures")
    ensure_dir(archive_dir)
    archive_path = os.path.join(archive_dir, f"{model}_{ts}.npz")

    np.savez_compressed(out_path, X=X)
    np.savez_compressed(archive_path, X=X)

    print(f"Saved template to: {out_path}  (key: X, shape={X.shape})")
    print(f"Archived raw capture at: {archive_path}")

if __name__ == "__main__":
    main()
