"""Rolling walk-forward window generation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from utils import settings


@dataclass
class WalkForwardWindow:
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime


def walk_forward_params() -> tuple[int, int, int]:
    train_days = int(settings.get("walk_forward_train_days", "45") or 45)
    test_days = int(settings.get("walk_forward_test_days", "7") or 7)
    step_days = int(settings.get("walk_forward_step_days", "7") or 7)
    return train_days, test_days, step_days


def generate_windows(
    start: datetime,
    end: datetime,
    *,
    train_days: int | None = None,
    test_days: int | None = None,
    step_days: int | None = None,
) -> list[WalkForwardWindow]:
    td, vd, sd = walk_forward_params()
    train_days = train_days or td
    test_days = test_days or vd
    step_days = step_days or sd
    windows: list[WalkForwardWindow] = []
    cursor = start
    while True:
        train_end = cursor + timedelta(days=train_days)
        test_start = train_end
        test_end = test_start + timedelta(days=test_days)
        if test_end > end:
            break
        windows.append(WalkForwardWindow(cursor, train_end, test_start, test_end))
        cursor += timedelta(days=step_days)
    return windows
