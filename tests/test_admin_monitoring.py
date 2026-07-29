import json
from datetime import datetime, timedelta

from tests.helpers import auth


def test_system_health_exposes_resources_queues_and_services(client, admin_token, monkeypatch):
    import services.runtime_monitor as runtime

    monkeypatch.setattr(runtime, "system_resources", lambda: {
        "available": True, "cpu_percent": 12.5, "ram_percent": 40.0,
        "process_rss_mb": 128.0,
    })
    monkeypatch.setattr(runtime, "redis_health", lambda: {
        "configured": True, "healthy": True, "latency_ms": 1.2,
    })
    response = client.get("/admin/api/system/health", headers=auth(admin_token))
    assert response.status_code == 200
    body = response.get_json()
    assert body["database"]["healthy"] is True
    assert body["resources"]["cpu_percent"] == 12.5
    assert body["redis"]["healthy"] is True
    assert "queue_size" in body
    assert {row["service"] for row in body["services"]} == {
        "api",
        "ai-worker",
        "scheduler",
        "telegram",
    }


def test_ml_monitoring_exposes_governance_and_history(client, admin_token):
    response = client.get("/admin/api/ml/monitoring", headers=auth(admin_token))
    assert response.status_code == 200
    body = response.get_json()
    assert set(body["tiers"]) == {"PENDING_REVIEW", "APPROVED", "REJECTED", "GOLD"}
    assert "datasets" in body
    assert "models" in body
    assert "training_history" in body
    assert "promotion_history" in body


def test_performance_dashboard_groups_verified_results(client, admin_token):
    from db.models import PredictionReview, SignalOutcome
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        review = PredictionReview(
            symbol="EURUSD", interval="15min", horizon="intraday",
            predicted_action="BUY_BIAS", predicted_confidence=0.75,
            entry_price=1.10, invalidation_price=1.095, target_price=1.11,
            risk_reward_planned=2.0, risk_reward_achieved=1.8,
            strategy_mode="ict", trading_style="intraday",
            evaluate_at=datetime.utcnow() + timedelta(hours=2),
        )
        db.add(review)
        db.flush()
        db.add(SignalOutcome(
            prediction_id=review.id, rule_direction="bullish",
            entry_price=1.10, tp_price=1.11, sl_price=1.095,
            outcome="TP_HIT", meta_label=1,
        ))
        db.commit()
    finally:
        db.close()

    response = client.get("/admin/api/performance/overview", headers=auth(admin_token))
    assert response.status_code == 200
    body = response.get_json()
    pair = next(row for row in body["pairs"] if row["name"] == "EURUSD")
    strategy = next(row for row in body["strategies"] if row["name"] == "ict")
    assert pair["win_rate"] == 1.0
    assert pair["expectancy"] == 1.8
    assert strategy["signals"] >= 1


def test_restart_control_is_guarded(client, admin_token):
    headers = auth(admin_token)
    invalid = client.post(
        "/admin/api/system/restart",
        headers=headers,
        json={"service": "api", "confirmation": "yes"},
    )
    assert invalid.status_code == 400
    unavailable = client.post(
        "/admin/api/system/restart",
        headers=headers,
        json={"service": "api", "confirmation": "RESTART api"},
    )
    assert unavailable.status_code == 503
    assert "SYSTEM_RESTART_WEBHOOK" in unavailable.get_json()["error"]


def test_job_monitoring_endpoint(client, admin_token):
    response = client.get("/admin/api/jobs", headers=auth(admin_token))
    assert response.status_code == 200
    assert set(response.get_json()) == {"training", "exports", "deliveries"}


def test_render_services_share_production_redis():
    text = __import__("pathlib").Path("render.yaml").read_text(encoding="utf-8")
    assert "type: keyvalue" in text
    assert "name: smartflow-cache" in text
    assert text.count("key: REDIS_URL") == 4
    assert "property: connectionString" in text
