"""Tests for recency weight tiers."""
from datetime import datetime, timedelta

from ml.recency import calculate_sample_weight, get_recency_tiers


def test_recency_tiers_default():
    tiers = get_recency_tiers()
    assert len(tiers) >= 3


def test_recency_weight_recent():
    w = calculate_sample_weight(datetime.utcnow() - timedelta(days=5))
    assert w == 1.0


def test_recency_weight_old():
    w = calculate_sample_weight(datetime.utcnow() - timedelta(days=400))
    assert w <= 0.35
