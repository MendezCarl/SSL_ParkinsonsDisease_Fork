#!/usr/bin/env python3
import os
import json
import base64
from io import BytesIO
import numpy as np
import matplotlib.pyplot as plt
from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from pathlib import Path

# Import functions from the finger_tapping.py
from finger_tapping import compute_metrics, plot_metrics

app = FastAPI(title="Finger Tapping Analysis Dashboard")

# Create directories for static files
os.makedirs("static", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)

# Setup static file serving and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Directories used by finger_tapping.py
VIDEO_DIR = "recordings"
JSON_DIR = "jsons"

os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)

# Create templates directory
os.makedirs("templates", exist_ok=True)


def get_recordings():
    """Get all recordings with their corresponding JSON and metrics files."""
    recordings = []

    # List all JSON files
    json_files = [f for f in os.listdir(JSON_DIR) if f.endswith('.json')]

    for json_file in json_files:
        base_name = json_file.replace('.json', '')
        video_file = f"{base_name}.avi"
        metrics_file = f"{base_name}_metrics.png"

        video_path = os.path.join(VIDEO_DIR, video_file)
        json_path = os.path.join(JSON_DIR, json_file)
        metrics_path = os.path.join(JSON_DIR, metrics_file)

        # Check if all files exist
        if os.path.exists(video_path) and os.path.exists(json_path):
            # Calculate tap count from JSON data
            tap_count = 0
            with open(json_path, 'r') as f:
                landmarks_list = json.load(f)

            # Compute metrics
            times, amp, _ = compute_metrics(landmarks_list, 20)  # FPS=20

            # Count taps using state machine
            states = []
            for d in amp:
                if d <= 0.5:
                    states.append("closed")
                elif d >= 0.8:
                    states.append("open")
                else:
                    states.append(None)

            # Count open->closed transitions
            prev = None
            for st in states:
                if prev == "open" and st == "closed":
                    tap_count += 1
                if st in ("open", "closed"):
                    prev = st

            # Add recording info to list
            recordings.append({
                "name": base_name,
                "video_path": video_path,
                "json_path": json_path,
                "metrics_path": metrics_path if os.path.exists(metrics_path) else None,
                "tap_count": tap_count,
                "timestamp": base_name.replace("tap_", "")
            })

    # Sort by timestamp (newest first)
    recordings.sort(key=lambda x: x["timestamp"], reverse=True)
    return recordings


def generate_plot_image(json_path):
    """Generate plot image from JSON data and return as base64 string."""
    with open(json_path, 'r') as f:
        landmarks_list = json.load(f)

    # Compute metrics
    times, amp, speed = compute_metrics(landmarks_list, 20)  # FPS=20

    # Create plot
    plt.figure(figsize=(10, 4))
    plt.subplot(1, 2, 1)
    plt.plot(times, amp)
    plt.title("Normalized Tap Amplitude")
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude (a.u.)")

    plt.subplot(1, 2, 2)
    plt.plot(times, speed)
    plt.title("Tap Speed")
    plt.xlabel("Time (s)")
    plt.ylabel("Speed (a.u./s)")
    plt.tight_layout()

    # Convert plot to base64 string
    buf = BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    img_str = base64.b64encode(buf.read()).decode('utf-8')
    return f"data:image/png;base64,{img_str}"


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    recordings = get_recordings()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "recordings": recordings}
    )


@app.get("/recording/{recording_name}")
async def get_recording_details(request: Request, recording_name: str):
    # Find the recording
    recordings = get_recordings()
    recording = next((r for r in recordings if r["name"] == recording_name), None)

    if not recording:
        return {"error": "Recording not found"}

    # Generate plot if not exists
    if not recording["metrics_path"] or not os.path.exists(recording["metrics_path"]):
        plot_img = generate_plot_image(recording["json_path"])
    else:
        # Read existing plot file
        with open(recording["metrics_path"], "rb") as f:
            img_data = base64.b64encode(f.read()).decode('utf-8')
            plot_img = f"data:image/png;base64,{img_data}"

    return templates.TemplateResponse(
        "recording_details.html",
        {
            "request": request,
            "recording": recording,
            "plot_img": plot_img
        }
    )


@app.get("/video/{recording_name}")
async def get_video(recording_name: str):
    video_path = os.path.join(VIDEO_DIR, f"{recording_name}.avi")
    if os.path.exists(video_path):
        return FileResponse(video_path, media_type="video/x-msvideo")
    return {"error": "Video not found"}


# Create HTML templates
index_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Finger Tapping Analysis Dashboard</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #ddd;
            padding-bottom: 10px;
        }
        .recordings-list {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
        }
        .recording-card {
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            width: 300px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        .recording-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }
        .recording-card h2 {
            margin-top: 0;
            font-size: 1.2em;
        }
        .stats {
            margin: 15px 0;
        }
        .stats div {
            margin-bottom: 8px;
        }
        .view-btn {
            display: inline-block;
            background-color: #4CAF50;
            color: white;
            padding: 8px 16px;
            text-decoration: none;
            border-radius: 4px;
            transition: background-color 0.3s;
        }
        .view-btn:hover {
            background-color: #45a049;
        }
        .no-recordings {
            font-style: italic;
            color: #666;
            text-align: center;
            padding: 50px 0;
        }
    </style>
</head>
<body>
    <h1>Finger Tapping Analysis Dashboard</h1>

    <div class="recordings-list">
        {% if recordings %}
            {% for recording in recordings %}
                <div class="recording-card">
                    <h2>{{ recording.name }}</h2>
                    <div class="stats">
                        <div><strong>Tap Count:</strong> {{ recording.tap_count }}</div>
                        <div><strong>Recorded:</strong> {{ recording.timestamp }}</div>
                    </div>
                    <a href="/recording/{{ recording.name }}" class="view-btn">View Details</a>
                </div>
            {% endfor %}
        {% else %}
            <p class="no-recordings">No recordings found. Run the finger_tapping.py script to create some recordings.</p>
        {% endif %}
    </div>
</body>
</html>
"""

details_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Recording Details - {{ recording.name }}</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>

        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #ddd;
            padding-bottom: 10px;
        }
        .back-link {
            display: inline-block;
            margin-bottom: 20px;
            color: #4CAF50;
            text-decoration: none;
        }
        .back-link:hover {
            text-decoration: underline;
        }
        .details-container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        .video-container {
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            background-color: #f9f9f9;
        }
        .metrics-container {
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            background-color: #f9f9f9;
        }
        .metrics-img {
            width: 100%;
            border-radius: 4px;
        }
        .stats-box {
            background-color: #e9f7ef;
            border: 1px solid #c5e1d0;
            border-radius: 8px;
            padding: 15px;
            margin-top: 20px;
        }
        .stats-box h3 {
            margin-top: 0;
            color: #2e7d32;
        }
        video {
            width: 100%;
            border-radius: 4px;
        }
        @media (max-width: 768px) {
            .details-container {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <a href="/" class="back-link">-- Back to Dashboard</a>
    <h1>Recording: {{ recording.name }}</h1>

    <div class="details-container">
        <div class="video-container">
            <h2>Finger Tapping Video</h2>
            <video controls>
                <source src="/video/{{ recording.name }}" type="video/x-msvideo">
                Your browser does not support the video tag.
            </video>
        </div>

        <div class="metrics-container">
            <h2>Performance Metrics</h2>
            <img src="{{ plot_img }}" alt="Metrics Plot" class="metrics-img">

            <div class="stats-box">
                <h3>Tap Statistics</h3>
                <p><strong>Total Taps:</strong> {{ recording.tap_count }}</p>
                <p><strong>Recording Date:</strong> {{ recording.timestamp }}</p>
                <p><strong>Taps per Second:</strong> {{ (recording.tap_count / 10) | round(2) }}</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

# Create template files
with open("templates/index.html", "w", encoding="utf-8") as f:
    f.write(index_html)

with open("templates/recording_details.html", "w", encoding="utf-8") as f:
    f.write(details_html)

if __name__ == "__main__":
    print("Starting Finger Tapping Analysis Dashboard...")
    print("Open your browser and go to http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
