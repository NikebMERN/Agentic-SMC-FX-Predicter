"""Tests for nightly retrain lock and listing."""
from services.nightly_retrain import acquire_lock, list_training_runs, release_lock


def test_training_runs_list(initialized_db):
    rows = list_training_runs(limit=5)
    assert isinstance(rows, list)


def test_redis_lock_acquire_release():
    assert acquire_lock() is True
    release_lock()
