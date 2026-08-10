from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.export_vjepa2_embedding_from_video import _sample_indices, _window_ranges


def test_sample_indices_returns_four_64_frame_stride_views():
    views = _sample_indices(total_frames=256, frames_per_view=64, stride=2, view_count=4)

    assert len(views) == 4
    assert all(len(view) == 64 for view in views)
    assert np.all(np.diff(views[0]) == 2)
    assert views[0][0] == 0
    assert views[-1][-1] == 255


def test_sample_indices_pads_short_videos_by_repeating_indices():
    views = _sample_indices(total_frames=10, frames_per_view=64, stride=2, view_count=4)

    assert len(views) == 4
    assert all(len(view) == 64 for view in views)
    assert all(view.min() == 0 for view in views)
    assert all(view.max() == 9 for view in views)


def test_window_ranges_create_five_second_intervals():
    ranges = _window_ranges(total_frames=330, fps=30, window_seconds=5)

    assert [(start, end) for start, end, _, _ in ranges] == [(0.0, 5.0), (5.0, 10.0), (10.0, 11.0)]


def test_sample_indices_stays_inside_window():
    views = _sample_indices(
        total_frames=300,
        frames_per_view=64,
        stride=2,
        view_count=4,
        start_frame=150,
        end_frame=299,
    )

    assert all(view.min() >= 150 for view in views)
    assert all(view.max() <= 299 for view in views)
