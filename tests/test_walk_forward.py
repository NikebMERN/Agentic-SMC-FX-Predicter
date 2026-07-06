"""Tests for walk-forward windows."""
from datetime import datetime, timedelta

from ml.walk_forward import generate_windows


def test_generate_windows():
    start = datetime(2024, 1, 1)
    end = start + timedelta(days=120)
    windows = generate_windows(start, end, train_days=45, test_days=7, step_days=7)
    assert len(windows) >= 1
    assert windows[0].train_start == start
