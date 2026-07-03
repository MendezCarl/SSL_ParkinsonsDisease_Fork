#!/usr/bin/env python3
# webcam_keypoints_display.py
import json
import cv2
import numpy as np
import mediapipe as mp

def extract_nose_from_webcam(normalized=False, max_frames=300, out_file="webcam_keypoints.json"):
    """
    Capture webcam frames, extract nose keypoints, and display them live.
    Press 'q' to quit early.
    """
    cap = cv2.VideoCapture(0)  # webcam index 0
    if not cap.isOpened():
        raise RuntimeError("Could not access webcam")

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1

    mp_pose = mp.solutions.pose
    mp_drawing = mp.solutions.drawing_utils
    pose = mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    frames, nose_x, nose_y = [], [], []
    idx = 0

    try:
        while idx < max_frames:
            ok, frame = cap.read()
            if not ok:
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb)

            if results.pose_landmarks:
                # Draw the full pose skeleton
                mp_drawing.draw_landmarks(
                    frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=2),
                    connection_drawing_spec=mp_drawing.DrawingSpec(color=(0,0,255), thickness=2),
                )

                # Nose is landmark 0
                lm = results.pose_landmarks.landmark[0]
                if normalized:
                    x_out, y_out = float(lm.x), float(lm.y)
                    cx, cy = int(lm.x * width), int(lm.y * height)
                else:
                    x_out, y_out = float(lm.x * width), float(lm.y * height)
                    cx, cy = int(x_out), int(y_out)

                # Draw a red circle on the nose
                cv2.circle(frame, (cx, cy), 6, (0,0,255), -1)
            else:
                x_out, y_out = np.nan, np.nan

            frames.append(idx)
            nose_x.append(x_out)
            nose_y.append(y_out)
            idx += 1

            # Show annotated frame
            cv2.imshow("Webcam Pose - Press q to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        pose.close()
        cap.release()
        cv2.destroyAllWindows()

    # Save JSON
    data = {"frames": frames, "nose_x": nose_x, "nose_y": nose_y}
    with open(out_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Keypoints saved to {out_file}")
    print(f"Frames: {len(frames)}, NaNs: {sum(np.isnan(nose_x))}")

if __name__ == "__main__":
    extract_nose_from_webcam(normalized=False, max_frames=500, out_file="webcam_keypoints.json")
