import cv2
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import math
from ultralytics import YOLO
import matplotlib
matplotlib.use('Qt5Agg')


def calculate_angle(x1, y1, x2, y2):
    delta_x = x2 - x1
    delta_y = y2 - y1
    angle_radians = math.atan2(delta_y, delta_x)
    angle_degrees = math.degrees(angle_radians)
    return abs(angle_degrees)


def main():
    # Load YOLO model
    model_yolo = YOLO('yolov8m-pose.pt')

    # Open webcam
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open video.")
        return

    # Video properties
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS) or 30)  # fallback if FPS not detected

    output_file = 'output_video.avi'
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(output_file, fourcc, fps, (frame_width, frame_height))

    trackpoint1 = []
    trackpoint2 = []

    color1 = (255, 0, 0)  # Blue
    color2 = (0, 255, 0)  # Green

    angle_threshold = 95
    below_threshold_count = 0
    prev_angle = None
    step = 0

    fig, axes = plt.subplots(2, 1, figsize=(10, 10))
    lines1, = axes[0].plot([], [], 'b', label='X coordinates')
    lines1_y, = axes[0].plot([], [], 'r', label='Y coordinates')
    lines2, = axes[1].plot([], [], 'b', label='X coordinates')
    lines2_y, = axes[1].plot([], [], 'r', label='Y coordinates')

    axes[0].set_xlim(0, 1000)
    axes[0].set_ylim(0, frame_height)
    axes[0].set_title('Knee Coordinates vs Time Steps')
    axes[0].legend()

    axes[1].set_xlim(0, 1000)
    axes[1].set_ylim(0, frame_height)
    axes[1].set_title('Hips Coordinates vs Time Steps')
    axes[1].legend()

    plt.tight_layout()

    def update_plot(i):
        nonlocal step, below_threshold_count, prev_angle

        ret, frame = cap.read()
        if not ret:
            print("Reached end of video.")
            plt.close()
            return

        results = model_yolo(frame, stream=False, show=False)
        for result in results:
            keypoints = result.keypoints.xy
            matrix = np.asarray(keypoints[0])

            for point in matrix:
                if not np.array_equal(point, [0, 0]):
                    cv2.circle(frame, (int(point[0]), int(point[1])), 3, (255, 255, 255), -1)

            if len(matrix) > 16:
                point1 = matrix[13]
                point2 = matrix[11]

                if not np.array_equal(point1, [0, 0]):
                    trackpoint1.append((step, point1[0], point1[1]))
                if not np.array_equal(point2, [0, 0]):
                    trackpoint2.append((step, point2[0], point2[1]))

        for i in range(1, len(trackpoint1)):
            pt1 = (int(trackpoint1[i-1][1]), int(trackpoint1[i-1][2]))
            pt2 = (int(trackpoint1[i][1]), int(trackpoint1[i][2]))
            cv2.circle(frame, pt2, 3, color1, -1)
            cv2.line(frame, pt1, pt2, color1, 2)

        for i in range(1, len(trackpoint2)):
            pt1 = (int(trackpoint2[i-1][1]), int(trackpoint2[i-1][2]))
            pt2 = (int(trackpoint2[i][1]), int(trackpoint2[i][2]))
            cv2.circle(frame, pt2, 3, color2, -1)
            cv2.line(frame, pt1, pt2, color2, 2)

        if trackpoint1 and trackpoint2:
            x1, y1 = trackpoint1[-1][1], trackpoint1[-1][2]
            x2, y2 = trackpoint2[-1][1], trackpoint2[-1][2]
            angle = calculate_angle(x1, y1, x2, y2)

            if prev_angle is not None and prev_angle >= angle_threshold and angle < angle_threshold:
                below_threshold_count += 1

            prev_angle = angle

            cv2.putText(frame, f"Angle: {angle:.2f} degrees", (50, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(frame, f"Count: {below_threshold_count}", (50, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        out.write(frame)

        if trackpoint1:
            steps1, x_coords1, y_coords1 = zip(*trackpoint1)
            lines1.set_data(steps1, x_coords1)
            lines1_y.set_data(steps1, y_coords1)

        if trackpoint2:
            steps2, x_coords2, y_coords2 = zip(*trackpoint2)
            lines2.set_data(steps2, x_coords2)
            lines2_y.set_data(steps2, y_coords2)

        cv2.imshow('Pose Tracking', frame)
        step += 1

        if cv2.waitKey(1) & 0xFF == ord('q'):
            plt.close()

    ani = FuncAnimation(fig, update_plot, interval=10)
    plt.show()

    cap.release()
    out.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
