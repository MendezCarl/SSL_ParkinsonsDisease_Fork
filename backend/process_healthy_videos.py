#!/usr/bin/env python3
"""
process_healthy_videos.py
=========================
Processes healthy-subject videos from backend/healthy_data/<test>/ and
rebuilds the DTW reference templates in backend/data/templates/<test>/<model>.npz

Directory layout expected:
    backend/
        healthy_data/
            finger-tapping/   <- drop .mp4 / .mov / .webm videos here
            fist-open-close/
            stand-and-sit/
        data/
            templates/        <- rebuilt .npz files written here
            jsons/            <- per-video keypoint JSONs archived here

Usage:
    # Process all tests
    python process_healthy_videos.py

    # Process one test only
    python process_healthy_videos.py --test finger-tapping

    # Process but skip template rebuild (just extract keypoints)
    python process_healthy_videos.py --no-rebuild-template

    # Force re-process already-extracted videos
    python process_healthy_videos.py --force
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from scipy.interpolate import interp1d
from storage_paths import JSONS_DIR, TEMPLATES_DIR

# ─────────────────────────── Paths ───────────────────────────
BACKEND_DIR    = Path(__file__).resolve().parent
HEALTHY_DIR    = BACKEND_DIR / "healthy_data"
MODELS_DIR     = BACKEND_DIR / "models"
HAND_MODEL     = str(MODELS_DIR / "hand_landmarker.task")
POSE_MODEL     = str(MODELS_DIR / "pose_landmarker_lite.task")

JSONS_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────── Config ───────────────────────────
TEST_MODEL: dict[str, str] = {
    "finger-tapping":  "hands",
    "fist-open-close": "hands",
    "stand-and-sit":   "pose",
}

VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}

# ─────────────────────────── Feature extraction (Tasks API) ───────────────────────────
def _hands_features_from_pts(pts: np.ndarray) -> np.ndarray:
    """21 x 2 (x,y) landmarks -> 42D wrist-normalised feature vector."""
    ref   = pts[0]
    rel   = pts - ref
    scale = np.linalg.norm(pts[9] - ref) + 1e-6
    return (rel / scale).reshape(-1)   # (42,)


def _pose_features_from_pts(pts: np.ndarray) -> np.ndarray:
    """33 x 2 (x,y) landmarks -> 66D hip-normalised feature vector."""
    mid_hips   = (pts[23] + pts[24]) / 2.0
    rel        = pts - mid_hips
    shoulder_w = np.linalg.norm(pts[11] - pts[12]) + 1e-6
    return (rel / shoulder_w).reshape(-1)   # (66,)


def _make_hand_landmarker():
    import mediapipe as mp
    import mediapipe.tasks as mp_tasks
    vision = mp_tasks.vision
    if not Path(HAND_MODEL).exists():
        raise FileNotFoundError(
            f"Hand landmarker model not found at {HAND_MODEL}.\n"
            "Run: curl -L https://storage.googleapis.com/mediapipe-models/"
            "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task "
            f"-o {HAND_MODEL}"
        )
    options = vision.HandLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=HAND_MODEL),
        running_mode=vision.RunningMode.IMAGE,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.HandLandmarker.create_from_options(options)


def _make_pose_landmarker():
    import mediapipe as mp
    import mediapipe.tasks as mp_tasks
    vision = mp_tasks.vision
    if not Path(POSE_MODEL).exists():
        raise FileNotFoundError(
            f"Pose landmarker model not found at {POSE_MODEL}.\n"
            "Run: curl -L https://storage.googleapis.com/mediapipe-models/"
            "pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task "
            f"-o {POSE_MODEL}"
        )
    options = vision.PoseLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=POSE_MODEL),
        running_mode=vision.RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.PoseLandmarker.create_from_options(options)


# ─────────────────────────── Video processing ───────────────────────────
def extract_keypoints_from_video(
    video_path: Path,
    model: str,
) -> tuple[list[list[list[float]]], list[np.ndarray]]:
    """
    Run MediaPipe Tasks API on every frame of a video.

    Returns:
        raw_frames  - list of per-frame landmark arrays (for JSON archival)
        feat_frames - list of feature vectors (for DTW template)
    """
    import mediapipe as mp

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    solution = _make_hand_landmarker() if model == "hands" else _make_pose_landmarker()

    raw_frames:  list[list[list[float]]] = []
    feat_frames: list[np.ndarray]        = []

    total     = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    processed = 0

    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break

            rgb      = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result   = solution.detect(mp_image)

            if model == "hands":
                if not result.hand_landmarks:
                    processed += 1
                    continue
                lm_list = result.hand_landmarks[0]   # first hand
                raw  = [[lm.x, lm.y, lm.z] for lm in lm_list]
                pts  = np.array([[lm.x, lm.y] for lm in lm_list], dtype=np.float32)
                feat = _hands_features_from_pts(pts)
            else:
                if not result.pose_landmarks:
                    processed += 1
                    continue
                lm_list = result.pose_landmarks[0]
                raw  = [[lm.x, lm.y, lm.z] for lm in lm_list]
                pts  = np.array([[lm.x, lm.y] for lm in lm_list], dtype=np.float32)
                feat = _pose_features_from_pts(pts)

            raw_frames.append(raw)
            feat_frames.append(feat)

            processed += 1
            if processed % 100 == 0:
                pct = f"{processed}/{total}" if total > 0 else str(processed)
                print(f"    {pct} frames processed …", end="\r", flush=True)
    finally:
        cap.release()
        try:
            solution.close()
        except Exception:
            pass

    print()  # newline after \r progress
    return raw_frames, feat_frames


# ─────────────────────────── Template builder ───────────────────────────
def build_template(feat_sets: list[list[np.ndarray]]) -> np.ndarray:
    """
    Resample all recordings to the median length then average them
    into a single (T, D) reference template.
    """
    sequences = [np.stack(fs, axis=0).astype(np.float32) for fs in feat_sets]
    target_len = int(np.median([s.shape[0] for s in sequences]))
    D = sequences[0].shape[1]

    resampled = []
    for s in sequences:
        T    = s.shape[0]
        xold = np.linspace(0, 1, T)
        xnew = np.linspace(0, 1, target_len)
        interped = np.stack(
            [interp1d(xold, s[:, d])(xnew) for d in range(D)], axis=1
        )
        resampled.append(interped)

    return np.mean(resampled, axis=0).astype(np.float32)


# ─────────────────────────── Per-test pipeline ───────────────────────────
def process_test(test: str, force: bool, rebuild: bool) -> None:
    model      = TEST_MODEL[test]
    video_dir  = HEALTHY_DIR / test
    out_dir    = TEMPLATES_DIR / test
    out_dir.mkdir(parents=True, exist_ok=True)

    videos = [p for p in video_dir.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS]
    if not videos:
        print(f"  [skip] No videos found in {video_dir}")
        return

    print(f"\n{'─'*60}")
    print(f"  Test : {test}  |  model : {model}  |  videos : {len(videos)}")
    print(f"{'─'*60}")

    all_feat_sets: list[list[np.ndarray]] = []

    for video_path in sorted(videos):
        ts_str   = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        stem     = video_path.stem
        json_out = JSONS_DIR / f"{stem}_{ts_str}.json"

        # Skip if already extracted (unless --force)
        existing = list(JSONS_DIR.glob(f"{stem}_*.json"))
        if existing and not force:
            print(f"  [cached] {video_path.name} -> {existing[-1].name}")
            # Load existing features from JSON for template rebuild
            raw_data = json.loads(existing[-1].read_text())
            feat_list: list[np.ndarray] = []
            for frame in raw_data:
                lm_arr = np.array(frame, dtype=np.float32)  # (21,3) or (33,3)
                pts    = lm_arr[:, :2]
                if model == "hands":
                    feat_list.append(_hands_features_from_pts(pts))
                else:
                    feat_list.append(_pose_features_from_pts(pts))
            if feat_list:
                all_feat_sets.append(feat_list)
            continue

        print(f"  Processing {video_path.name} …")
        try:
            raw_frames, feat_frames = extract_keypoints_from_video(video_path, model)
        except Exception as exc:
            print(f"  [ERROR] {video_path.name}: {exc}")
            continue

        if not feat_frames:
            print(f"  [warn] No landmarks detected in {video_path.name}, skipping.")
            continue

        # Archive raw keypoints JSON
        json_out.write_text(json.dumps(raw_frames))
        print(f"  Saved keypoints: {json_out.name}  ({len(feat_frames)} frames)")

        all_feat_sets.append(feat_frames)

    if not all_feat_sets:
        print(f"  [skip] No usable feature sets for {test}.")
        return

    if not rebuild:
        print(f"  [skip] --no-rebuild-template set; skipping template write.")
        return

    # Build + save template
    template = build_template(all_feat_sets)
    template_path = out_dir / f"{model}.npz"
    np.savez_compressed(str(template_path), X=template)

    print(f"\n  Template saved -> {template_path}")
    print(f"  Shape: {template.shape}  ({len(all_feat_sets)} recordings averaged)")


# ─────────────────────────── CLI ───────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Process healthy-subject videos into DTW reference templates."
    )
    ap.add_argument(
        "--test",
        choices=list(TEST_MODEL.keys()),
        default=None,
        help="Process only this test (default: all tests).",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-process videos even if keypoint JSON already exists.",
    )
    ap.add_argument(
        "--no-rebuild-template",
        action="store_true",
        dest="no_rebuild",
        help="Extract keypoints only; do not rebuild the .npz template.",
    )
    args = ap.parse_args()

    tests = [args.test] if args.test else list(TEST_MODEL.keys())

    print(f"\nHealthy video processor")
    print(f"  healthy_data  : {HEALTHY_DIR}")
    print(f"  templates out : {TEMPLATES_DIR}")
    print(f"  keypoints out : {JSONS_DIR}")
    print(f"  tests         : {tests}")
    print(f"  force         : {args.force}")
    print(f"  rebuild       : {not args.no_rebuild}")

    for test in tests:
        process_test(test, force=args.force, rebuild=not args.no_rebuild)

    print("\nDone.")


if __name__ == "__main__":
    main()
