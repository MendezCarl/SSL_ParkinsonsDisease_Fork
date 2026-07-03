# healthy_data/

Drop healthy-subject test videos into the appropriate subfolder.

```
healthy_data/
    finger-tapping/    <- .mp4/.mov/.webm of finger-tapping tests
    fist-open-close/   <- .mp4/.mov/.webm of fist open-close tests
    stand-and-sit/     <- .mp4/.mov/.webm of stand-and-sit tests
```

Then run the processing script from the `backend/` directory:

```bash
# Process all tests and rebuild templates
python process_healthy_videos.py

# Process a single test
python process_healthy_videos.py --test finger-tapping

# Re-process videos that were already extracted
python process_healthy_videos.py --force

# Extract keypoints only (don't overwrite templates yet)
python process_healthy_videos.py --no-rebuild-template
```

## What the script does

1. Iterates over videos in each subfolder.
2. Runs MediaPipe Hands (finger-tapping, fist-open-close) or MediaPipe Pose (stand-and-sit) on every frame.
3. Saves raw landmark data to `backend/data/jsons/<video_stem>_<timestamp>.json` — same format as the existing `tap_*.json` files.
4. Resamples all recordings to a common length and averages them into a single reference template at `backend/data/templates/<test>/hands.npz` (or `pose.npz`).

Already-extracted videos are cached by JSON name — use `--force` to re-run them.
