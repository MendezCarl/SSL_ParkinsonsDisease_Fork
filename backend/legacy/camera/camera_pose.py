import cv2
import mediapipe as mp
import time

# Initialize MediaPipe Pose
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_drawing = mp.solutions.drawing_utils

def process_pose(rtsp_url):
    # Open the RTSP stream for pose detection
    cap = cv2.VideoCapture(rtsp_url)
    time.sleep(2)
    if not cap.isOpened():
        print("Failed to open RTSP stream.")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to retrieve frame.")
            break

        # Resize the frame to 640x480
        frame = cv2.resize(frame, (640, 480))

        # Flip the frame horizontally for a mirror effect
        frame = cv2.flip(frame, 1)

        # Convert frame to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb_frame)

        # If pose landmarks are detected, draw them on the frame
        if results.pose_landmarks:
            mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)

        # Display the frame with pose landmarks
        cv2.imshow("Pose Estimation", frame)

        # Press 'q' to quit the window
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    # RTSP URL for the pose camera
    rtsp_url_pose = "rtsp://192.168.1.189:554/stream/main"  # Change this to your pose camera URL
    process_pose(rtsp_url_pose)
