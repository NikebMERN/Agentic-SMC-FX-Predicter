# tests/test_threshold_service.py
"""Threshold versioning, activation, audit, cache."""
import json

import pytest

from db.models import AdminLog, ThresholdVersion
from db.session import SessionLocal
from services import threshold_service
from schemas.threshold_schema import merge_threshold_patch
from config.smc_ict_thresholds import DEFAULT_THRESHOLDS


@pytest.mark.usefixtures("initialized_db")
def test_seed_creates_active_v1():
    threshold_service.invalidate_cache()
    row = threshold_service.seed_initial_version()
    assert row is not None
    active = threshold_service.get_active_version()
    assert active is not None
    assert active.is_active is True


@pytest.mark.usefixtures("initialized_db")
def test_create_and_activate_version():
    threshold_service.seed_initial_version()
    config = merge_threshold_patch(DEFAULT_THRESHOLDS, {"decision": {"score_bias_minimum": 63}}).model_dump()
    row = threshold_service.create_version(config, "test-v2", admin_id=1, notes="test")
    assert row.is_active is False
    threshold_service.activate_version(row.id, admin_id=1)
    active = threshold_service.get_active_version()
    assert active.id == row.id


@pytest.mark.usefixtures("initialized_db")
def test_patch_creates_new_version():
    threshold_service.seed_initial_version()
    row = threshold_service.patch_active_version({"decision": {"score_wait_below": 58}}, admin_id=1)
    assert row.is_active is True
    resolved, vid = threshold_service.resolve_thresholds("EURUSD", "60min", "intraday")
    assert resolved.decision.score_wait_below == 58
    assert vid == row.id


@pytest.mark.usefixtures("initialized_db")
def test_override_and_cache_invalidation():
    threshold_service.seed_initial_version()
    threshold_service.save_override("GBPUSD", "60min", "intraday", {"spread": {"max_spread_pips_major": 1.8}})
    t1, _ = threshold_service.resolve_thresholds("GBPUSD", "60min", "intraday", use_cache=False)
    assert t1.spread.max_spread_pips_major == 1.8


@pytest.mark.usefixtures("initialized_db")
def test_audit_on_admin_action_via_api(client):
    threshold_service.seed_initial_version()
    token = client.post("/admin/api/login", json={"email": "admin@test.local", "password": "test-admin-pass"}).get_json()["token"]
    res = client.patch(
        "/admin/api/thresholds/active",
        json={"patch": {"decision": {"score_no_trade_below": 48}}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    db = SessionLocal()
    try:
        logs = db.query(AdminLog).filter(AdminLog.action == "threshold_version_create").all()
        assert len(logs) >= 1
    finally:
        db.close()
