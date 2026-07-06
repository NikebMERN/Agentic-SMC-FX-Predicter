"""Recency-weighted sample importance for training."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from utils import settings

DEFAULT_TIERS = [
    {"max_days": 30, "weight": 1.0},
    {"max_days": 90, "weight": 0.75},
    {"max_days": 180, "weight": 0.5},
    {"max_days": 365, "weight": 0.35},
    {"max_days": 99999, "weight": 0.2},
]


def get_recency_tiers() -> list[dict]:
    raw = settings.get("recency_weight_tiers")
    if not raw:
        return DEFAULT_TIERS
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else DEFAULT_TIERS
    except json.JSONDecodeError:
        return DEFAULT_TIERS


def calculate_sample_weight(record_date: datetime, *, reference: datetime | None = None) -> float:
    ref = reference or datetime.utcnow()
    age_days = max(0, (ref - record_date).days)
    for tier in get_recency_tiers():
        if age_days <= int(tier.get("max_days", 99999)):
            return float(tier.get("weight", 1.0))
    return 0.2
