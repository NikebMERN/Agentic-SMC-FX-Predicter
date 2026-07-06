# tests/test_sessions.py
"""Session filter tests."""
import pandas as pd

from engine.ict import session_info


def test_session_info_returns_weight():
    ts = pd.Timestamp("2025-01-15 08:30:00")
    info = session_info(ts)
    assert "weight" in info
    assert 0 <= info["weight"] <= 1.0


def test_outside_session_lower_weight():
    ts = pd.Timestamp("2025-01-15 18:00:00")
    info = session_info(ts)
    assert info["weight"] <= 0.5
