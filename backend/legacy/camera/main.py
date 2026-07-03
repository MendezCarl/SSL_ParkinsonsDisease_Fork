import multiprocessing
import subprocess

# def run_camera_pose():
#     # Run the camera pose detection script as a separate process
#     subprocess.run(["python3", "camera_pose.py"])

def run_camera_hand():
    # Run the camera hand tracking script as a separate process
    subprocess.run(["python3", "camera_hand.py"])

if __name__ == "__main__":
    # Start both camera processes (pose and hand tracking)
    # pose_process = multiprocessing.Process(target=run_camera_pose)
    hand_process = multiprocessing.Process(target=run_camera_hand)
    
    # Start the processes
    pose_process.start()
    hand_process.start()

    # Join the processes to make sure they finish
    pose_process.join()
    hand_process.join()
