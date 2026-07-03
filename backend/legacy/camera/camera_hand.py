import cv2
import mediapipe as mp
import time
# Initialize MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.6, min_tracking_confidence=0.6)
mp_drawing = mp.solutions.drawing_utils

def process_hand(rtsp_url):
    # Open the RTSP stream for hand tracking
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
        results = hands.process(rgb_frame)

        # If hand landmarks are detected, draw them on the frame
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

        # Display the frame with hand landmarks
        cv2.imshow("Hand Tracking", frame)

        # Press 'q' to quit the window
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    # RTSP URL for the hand camera
    rtsp_url_hand = "rtsp://192.168.1.121:554/stream/main"  # Change this to your hand camera URL
    process_hand(rtsp_url_hand)
