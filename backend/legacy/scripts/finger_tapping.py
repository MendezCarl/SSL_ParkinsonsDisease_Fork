#!/usr/bin/env python3
import os
import cv2
import time
import json
import numpy as np
import mediapipe as mp
import matplotlib.pyplot as plt

# ─── USER CONFIG ─────────────────────────────────────────────────────────────
VIDEO_DIR      = "recordings"
JSON_DIR       = "jsons"
RECORD_SECONDS = 10
FPS            = 20

os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)

# ─── MediaPipe Hands setup ──────────────────────────────────────────────────
mp_hands = mp.solutions.hands
hands    = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.6,
)

def is_ok_gesture(lm, w, h):
    """Detects an 'OK' gesture: thumb tip & index tip touching, other fingers extended."""
    tips = [(int(lm.landmark[i].x * w), int(lm.landmark[i].y * h))
            for i in (4, 8, 12, 16, 20)]
    ref = np.mean([
        np.linalg.norm(np.array(tips[i]) - np.array(tips[i+1]))
        for i in range(1, 4)
    ]) or 1.0

    # thumb–index close?
    if np.linalg.norm(np.array(tips[0]) - np.array(tips[1])) > 0.4 * ref:
        return False

    # other fingers extended?
    for tip_id, pip_id in zip((12, 16, 20), (10, 14, 18)):
        if lm.landmark[tip_id].y > lm.landmark[pip_id].y:
            return False

    return True

def compute_metrics(landmarks_list, fps):
    """
    Compute normalized tap amplitude (thumb ↔ index) and speed.
    landmarks_list: list of frames, each a list of 21 (x,y,z) tuples.
    """
    arr = np.array(landmarks_list)  # (N,21,3)
    THUMB, INDEX, WRIST, MID = 4, 8, 0, 9

    # distances
    d_tap = np.linalg.norm(arr[:, THUMB, :2] - arr[:, INDEX, :2], axis=1)
    d_ref = np.linalg.norm(arr[:, MID,   :2] - arr[:, WRIST, :2], axis=1)

    amp_norm = d_tap / d_ref
    times    = np.arange(len(amp_norm)) / fps
    speed    = np.gradient(amp_norm, times)
    return times, amp_norm, speed

def plot_metrics(times, amp, speed, save_path=None):
    plt.figure(figsize=(10,4))
    plt.subplot(1,2,1)
    plt.plot(times, amp)
    plt.title("Normalized Tap Amplitude")
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude (a.u.)")
    plt.subplot(1,2,2)
    plt.plot(times, speed)
    plt.title("Tap Speed")
    plt.xlabel("Time (s)")
    plt.ylabel("Speed (a.u./s)")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path)
        print(f"-> Saved metrics plot to {save_path}")
    plt.show()

def distance_state(distances, low_thresh=0.5, high_thresh=0.8):
    """
    Convert normalized distances into discrete states:
      - "closed" if ≤ low_thresh
      - "open"   if ≥ high_thresh
      - None     otherwise
    """
    state = []
    for d in distances:
        if d <= low_thresh:
            state.append("closed")
        elif d >= high_thresh:
            state.append("open")
        else:
            state.append(None)
    return state

def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Cannot open camera.")
        return

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    recording     = False
    out           = None
    start_ts      = None
    vid_path      = None
    json_path     = None
    landmarks_buf = []
    tap_count     = 0

    print("-> Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res   = hands.process(rgb)

        if not recording:
            cv2.putText(frame, "Show OK gesture to start...", (30,30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
            if res.multi_hand_landmarks:
                lm0 = res.multi_hand_landmarks[0]
                if is_ok_gesture(lm0, w, h):
                    ts = time.strftime("%Y%m%d-%H%M%S")
                    vid_path  = os.path.join(VIDEO_DIR, f"tap_{ts}.avi")
                    json_path = os.path.join(JSON_DIR,  f"tap_{ts}.json")
                    fourcc    = cv2.VideoWriter_fourcc(*"XVID")
                    out       = cv2.VideoWriter(vid_path, fourcc, FPS, (w,h))
                    recording = True
                    start_ts  = time.time()
                    landmarks_buf.clear()
                    tap_count = 0
                    print(f"-> OK detected! Recording {RECORD_SECONDS}s to {vid_path} ...")
        else:
            elapsed = time.time() - start_ts
            if not res.multi_hand_landmarks:
                print("-> Hand lost! Discarding clip.")
                out.release()
                os.remove(vid_path)
                recording = False
            else:
                lm0 = res.multi_hand_landmarks[0]
                # store landmarks
                landmarks_buf.append([(p.x, p.y, p.z) for p in lm0.landmark])
                out.write(frame)

                # realtime count using state machine
                # compute normalized distance for this frame
                thumb = np.array([p.x for p in lm0.landmark[4:5]] + [p.y for p in lm0.landmark[4:5]])
                # (we'll recompute full series after end for plotting)
                # Here, we'll just append distance to temp list and count later

                secs_left = max(0, RECORD_SECONDS - int(elapsed))
                cv2.putText(frame,
                            f"Recording... {secs_left}s",
                            (30,30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)

                if elapsed >= RECORD_SECONDS:
                    out.release()
                    print(f"-> Done! Saved video to {vid_path}")

                    # save JSON
                    with open(json_path, "w") as f:
                        json.dump(landmarks_buf, f)
                    print(f"-> Saved landmarks to {json_path}")

                    # compute metrics & count taps
                    times, amp, speed = compute_metrics(landmarks_buf, FPS)
                    states = distance_state(amp)
                    # count open->closed transitions
                    prev = None
                    for st in states:
                        if prev == "open" and st == "closed":
                            tap_count += 1
                        if st in ("open","closed"):
                            prev = st

                    print(f"-> You did {tap_count} thumb-index taps.")
                    plot_path = json_path.replace(".json", "_metrics.png")
                    plot_metrics(times, amp, speed, save_path=plot_path)
                    break

        # draw landmarks
        if res.multi_hand_landmarks:
            for lm in res.multi_hand_landmarks:
                mp.solutions.drawing_utils.draw_landmarks(frame, lm, mp_hands.HAND_CONNECTIONS)

        cv2.imshow("Finger Tapping Recorder", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # cleanup
    if recording and out:
        out.release()
    cap.release()
    cv2.destroyAllWindows()
    print("Program ended.")

if __name__ == "__main__":
    main()
