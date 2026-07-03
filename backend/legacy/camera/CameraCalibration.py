import numpy as np
import cv2 as cv
import glob
import pickle

# Termination criteria for corner sub-pixel refinement
criteria = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 30, 0.001)

# Prepare object points (3D points in real-world space)
objp = np.zeros((6*7, 3), np.float32)
objp[:, :2] = np.mgrid[0:7, 0:6].T.reshape(-1, 2)

# Arrays to store object points and image points
objpoints = []  # 3D points
imgpoints = []  # 2D points

# Load images
images = glob.glob('images/*.jpg')

for fname in images:
    img = cv.imread(fname)
    gray = cv.cvtColor(img, cv.COLOR_BGR2GRAY)

    # Find chessboard corners
    ret, corners = cv.findChessboardCorners(gray, (7, 6), None)

    if ret:
        objpoints.append(objp)
        corners2 = cv.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        imgpoints.append(corners2)

        # Draw and display corners
        cv.drawChessboardCorners(img, (7, 6), corners2, ret)
        cv.imshow('Chessboard', img)
        cv.waitKey(500)

cv.destroyAllWindows()

# Camera calibration
ret, mtx, dist, rvecs, tvecs = cv.calibrateCamera(objpoints, imgpoints, gray.shape[::-1], None, None)

# Undistortion process
img = cv.imread('images/left12.jpg')
h, w = img.shape[:2]
newcameramtx, roi = cv.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))

# Calculate reprojection error
mean_error = 0
for i in range(len(objpoints)):
    imgpoints2, _ = cv.projectPoints(objpoints[i], rvecs[i], tvecs[i], mtx, dist)
    error = cv.norm(imgpoints[i], imgpoints2, cv.NORM_L2) / len(imgpoints2)
    mean_error += error

print(f"Total error: {mean_error / len(objpoints)}")

# Save calibration data
calibration_data = {
    "ret": ret,
    "mtx": mtx,
    "dist": dist,
    "rvecs": rvecs,
    "tvecs": tvecs,
    "newcameramtx": newcameramtx,
    "roi": roi
}

with open("calibration.pkl", "wb") as f:
    pickle.dump(calibration_data, f)

# Video capture with calibration applied
cap = cv.VideoCapture(0)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("End of video stream or error occurred.")
        break

    # Undistort the current frame using the calibration parameters
    undistorted_frame = cv.undistort(frame, mtx, dist, None, newcameramtx)

    # Display the undistorted frame
    cv.imshow('Undistorted Video', undistorted_frame)

    # Press 'q' to exit
    if cv.waitKey(25) & 0xFF == ord('q'):
        break

cap.release()
cv.destroyAllWindows()
