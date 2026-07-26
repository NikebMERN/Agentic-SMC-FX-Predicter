import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def _review(symbol="EURUSD", interval="60min"):
    from db.models import PredictionReview

    return PredictionReview(
        symbol=symbol,
        interval=interval,
        predicted_action="BUY_BIAS",
        predicted_confidence=0.78,
        entry_price=1.10,
        invalidation_price=1.095,
        target_price=1.11,
        risk_reward_planned=2.0,
        account_type="demo",
        volatility=0.0012,
        spread=0.0001,
        execution_delay_ms=120,
        manual_notes="clean execution",
        evaluate_at=datetime.utcnow() + timedelta(hours=4),
    )


def test_prediction_feedback_fields_and_dataset_versions_are_immutable(initialized_db):
    from db.models import DatasetVersion, PredictionReview, TrainingRecord
    from db.session import SessionLocal
    from services.dataset_service import create_dataset_version, promote_dataset

    features = {f"feature_{index}": float(index) for index in range(8)}
    db = SessionLocal()
    try:
        review = _review()
        db.add(review)
        db.flush()
        record = TrainingRecord(
            prediction_id=review.id,
            features_json=json.dumps(features),
            final_label="win",
            admin_status="APPROVED",
            dataset_tier="APPROVED",
            validation_score=0.9,
        )
        db.add(record)
        db.commit()
        record_id = record.id
        review_id = review.id
    finally:
        db.close()

    first = create_dataset_version("APPROVED")
    assert first.record_count == 1
    first_manifest = first.manifest_json

    db = SessionLocal()
    try:
        row = db.query(TrainingRecord).filter_by(id=record_id).one()
        row.features_json = json.dumps({**features, "feature_0": 99.0})
        db.commit()
    finally:
        db.close()

    second = create_dataset_version("APPROVED", parent_version_id=first.id)
    assert second.content_hash != first.content_hash
    assert promote_dataset(second.id)
    assert promote_dataset(first.id)

    db = SessionLocal()
    try:
        stored_first = db.query(DatasetVersion).filter_by(id=first.id).one()
        stored_second = db.query(DatasetVersion).filter_by(id=second.id).one()
        stored_review = db.query(PredictionReview).filter_by(id=review_id).one()
        assert stored_first.manifest_json == first_manifest
        assert stored_first.status == "ACTIVE"
        assert stored_second.status == "ARCHIVED"
        assert stored_review.risk_reward_planned == 2.0
        assert stored_review.execution_delay_ms == 120
    finally:
        db.close()


def test_feedback_validation_rejects_duplicate_evidence(initialized_db):
    from db.models import TrainingRecord, User, UserFeedback
    from db.session import SessionLocal
    from services.feedback_validation import feedback_hash, validate_feedback

    db = SessionLocal()
    try:
        user = User(username="feedback-validator", email="feedback-validator@test.local", password_hash="x")
        first_review = _review("GBPUSD")
        second_review = _review("USDJPY")
        db.add_all([user, first_review, second_review])
        db.flush()
        first = UserFeedback(
            prediction_id=first_review.id,
            user_id=user.id,
            trade_entry="ENTERED",
            feedback="SUCCESSFUL",
            comment="same copied evidence",
        )
        first.payload_hash = feedback_hash(first)
        db.add(first)
        db.flush()
        second = UserFeedback(
            prediction_id=second_review.id,
            user_id=user.id,
            trade_entry="ENTERED",
            feedback="SUCCESSFUL",
            comment="same copied evidence",
        )
        record = TrainingRecord(
            prediction_id=second_review.id,
            final_label="win",
            conflict=False,
            institutional_example=False,
        )
        db.add_all([second, record])
        db.commit()
        result = validate_feedback(record, second_review, second, None, None)
        assert result["tier"] == "REJECTED"
        assert result["suspicious"] is True
        assert result["duplicate_feedback_id"] == first.id
    finally:
        db.close()


def test_model_promotion_requires_economic_and_statistical_improvement(monkeypatch):
    import ml.promotion_gate as gate_module

    monkeypatch.setattr(gate_module, "promotion_enabled", lambda: True)
    candidate = {
        "walk_forward_score": 0.70, "precision": 0.72, "f1": 0.71,
        "brier_score": 0.18, "samples": 500, "total_signals": 500,
        "profit_factor": 1.45, "expectancy": 0.20, "sharpe_ratio": 1.1,
        "max_drawdown": 8.0, "win_rate": 0.62,
    }
    active = {
        "precision": 0.67, "f1": 0.66, "total_signals": 500, "win_rate": 0.54,
    }
    assert gate_module.evaluate_promotion(candidate, active)["passed"] is True

    weak = {**candidate, "profit_factor": 0.95}
    result = gate_module.evaluate_promotion(weak, active)
    assert result["passed"] is False
    assert any("profit_factor" in reason for reason in result["reasons"])


def test_training_selects_features_and_handles_imbalance():
    from ml.train_model import train_candidate

    rows = 80
    signal = np.linspace(-1, 1, rows)
    X = pd.DataFrame({
        "signal": signal,
        "signal_duplicate": signal,
        "constant": np.ones(rows),
        "noise": np.sin(np.arange(rows)),
    })
    y = pd.Series(([0] * 60) + ([1] * 20))
    result = train_candidate(X, y)
    assert result is not None
    assert "signal" in result["feature_names"]
    assert "signal_duplicate" not in result["feature_names"]
    assert "constant" not in result["feature_names"]
    assert result["metrics"]["confusion_matrix"]
    assert result["metrics"]["feature_importance"]


def test_admin_can_review_and_promote_feedback_record(client, admin_token):
    from db.models import TrainingRecord
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        review = _review("AUDCAD", "30min")
        db.add(review)
        db.flush()
        record = TrainingRecord(
            prediction_id=review.id,
            features_json=json.dumps({f"feature_{index}": float(index) for index in range(8)}),
            final_label="win",
            admin_status="PENDING_REVIEW",
            dataset_tier="PENDING_REVIEW",
            validation_score=0.95,
        )
        db.add(record)
        db.commit()
        record_id = record.id
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.patch(
        f"/admin/api/training-records/{record_id}/governance",
        headers=headers,
        json={"institutional_example": True, "admin_notes": "verified replay"},
    )
    assert response.status_code == 200
    governed = response.get_json()["record"]
    assert governed["institutional_example"] is True
    assert governed["dataset_tier"] == "GOLD"

    response = client.get("/admin/api/training-records?status=PENDING_REVIEW", headers=headers)
    assert response.status_code == 200
    listed = next(row for row in response.get_json()["records"] if row["id"] == record_id)
    assert listed["dataset_tier"] == "GOLD"
    assert listed["validation_score"] == 0.95
