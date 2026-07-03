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

def hand_state(lm):
    """
    Returns "open" if index/middle/ring/pinky are extended,
    "closed" if all four are bent, else None.
    """
    tips = [8, 12, 16, 20]
    pips = [6, 10, 14, 18]
    extended = bent = 0

    for tip_id, pip_id in zip(tips, pips):
        if lm.landmark[tip_id].y < lm.landmark[pip_id].y:
            extended += 1
        else:
            bent += 1

    if extended == 4:
        return "open"
    if bent == 4:
        return "closed"
    return None

def compute_metrics(landmarks_list, fps):
    """
    Given a list of frames each containing 21 landmarks [x,y,z],
    compute normalized amplitude (index_tip ↔ wrist) and speed.
    """
    arr = np.array(landmarks_list)  # shape: (N, 21, 3)
    WRIST, INDEX_TIP, MIDDLE_MCP = 0, 8, 9

    # raw distances
    dist_tip = np.linalg.norm(arr[:, INDEX_TIP, :2] - arr[:, WRIST, :2], axis=1)
    dist_ref = np.linalg.norm(arr[:, MIDDLE_MCP, :2] - arr[:, WRIST, :2], axis=1)

    amp_norm = dist_tip / dist_ref
    times    = np.arange(len(amp_norm)) / fps
    speed    = np.gradient(amp_norm, times)

    return times, amp_norm, speed

def plot_metrics(times, amp, speed, save_path=None):
    """Plot normalized amplitude and speed over time."""
    plt.figure(figsize=(10,4))

    plt.subplot(1,2,1)
    plt.plot(times, amp)
    plt.title("Normalized Amplitude")
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude (a.u.)")

    plt.subplot(1,2,2)
    plt.plot(times, speed)
    plt.title("Movement Speed")
    plt.xlabel("Time (s)")
    plt.ylabel("Speed (a.u./s)")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path)
        print(f"-> Saved metrics plot to {save_path}")
    plt.show()

def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Cannot open camera.")
        return

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    recording    = False
    out          = None
    start_time   = None
    vid_path     = None
    json_path    = None
    landmarks_buf = []
    prev_state   = None
    count        = 0

    print("-> Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res   = hands.process(rgb)

        if not recording:
            cv2.putText(frame, "Show open fist to start...", (30,30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0]
                if hand_state(lm) == "open":
                    ts = time.strftime("%Y%m%d-%H%M%S")
                    vid_path  = os.path.join(VIDEO_DIR, f"fist_{ts}.avi")
                    json_path = os.path.join(JSON_DIR,  f"fist_{ts}.json")
                    fourcc    = cv2.VideoWriter_fourcc(*"XVID")
                    out       = cv2.VideoWriter(vid_path, fourcc, FPS, (width, height))
                    start_time = time.time()
                    recording  = True
                    landmarks_buf = []
                    count       = 0
                    prev_state  = "open"
                    print(f"-> Detected open fist, recording {RECORD_SECONDS}s to {vid_path} ...")
        else:
            elapsed = time.time() - start_time
            if not res.multi_hand_landmarks:
                print("-> Hand lost! Discarding clip.")
                out.release()
                os.remove(vid_path)
                recording = False
            else:
                lm = res.multi_hand_landmarks[0]
                # store landmarks
                landmarks_buf.append([(pt.x, pt.y, pt.z) for pt in lm.landmark])

                state = hand_state(lm)
                if prev_state == "open" and state == "closed":
                    count += 1
                if state in ("open","closed"):
                    prev_state = state

                out.write(frame)
                secs_left = max(0, RECORD_SECONDS - int(elapsed))
                cv2.putText(frame,
                            f"Recording... {secs_left}s | cycles: {count}",
                            (30,30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)

                if elapsed >= RECORD_SECONDS:
                    out.release()
                    print(f"-> Done! Saved video to {vid_path}")
                    print(f"-> You did {count} open->closed cycles.")

                    # save JSON
                    with open(json_path, "w") as f:
                        json.dump(landmarks_buf, f)
                    print(f"-> Saved landmarks to {json_path}")

                    # compute & plot metrics
                    times, amp, speed = compute_metrics(landmarks_buf, FPS)
                    plot_path = json_path.replace(".json", "_metrics.png")
                    plot_metrics(times, amp, speed, save_path=plot_path)
                    break

        # draw landmarks
        if res.multi_hand_landmarks:
            for lm in res.multi_hand_landmarks:
                mp.solutions.drawing_utils.draw_landmarks(
                    frame, lm, mp_hands.HAND_CONNECTIONS
                )

        cv2.imshow("Fist Cycle Recorder", frame)
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
