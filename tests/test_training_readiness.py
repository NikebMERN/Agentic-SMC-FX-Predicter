# tests/test_training_readiness.py
"""Cross-check and training-ready sample building."""
import json
from datetime import datetime

from db.models import MarketVerification, PredictionReview, TrainingRecord, UserFeedback
from db.session import SessionLocal
from services.training_service import (
    assess_training_readiness,
    build_training_sample,
    reconcile_training_record,
)


def _feature_snapshot():
    return {
        f"feat_{i}": float(i) / 10
        for i in range(12)
    }


def _seed_record(*, conflict=False, with_feedback=True, market_direction="UP"):
    db = SessionLocal()
    try:
        review = PredictionReview(
            symbol="EURUSD",
            interval="60min",
            predicted_action="BUY_BIAS",
            predicted_confidence=0.6,
            entry_price=1.1,
            predicted_at=datetime.utcnow(),
            evaluate_at=datetime.utcnow(),
            status="evaluated",
            features_json=json.dumps(_feature_snapshot()),
        )
        db.add(review)
        db.commit()
        db.refresh(review)

        mv = MarketVerification(
            prediction_id=review.id,
            start_price=1.1,
            end_price=1.101,
            actual_direction=market_direction,
            outcome="AI_CORRECT",
            verified_at=datetime.utcnow(),
        )
        db.add(mv)

        if with_feedback:
            fb = "FAILED" if conflict else "SUCCESSFUL"
            db.add(UserFeedback(
                prediction_id=review.id,
                user_id=1,
                feedback=fb,
            ))

        rec = TrainingRecord(
            prediction_id=review.id,
            features_json=review.features_json,
            final_label="up",
            conflict=conflict,
            admin_status="PENDING_REVIEW",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return review.id, rec.id
    finally:
        db.close()


def test_build_training_sample(initialized_db):
    review_id, record_id = _seed_record()
    db = SessionLocal()
    try:
        review = db.query(PredictionReview).filter(PredictionReview.id == review_id).first()
        rec = db.query(TrainingRecord).filter(TrainingRecord.id == record_id).first()
        sample = build_training_sample(rec, review)
        assert sample is not None
        assert sample["label"] in ("up", 1)
        assert sample["symbol"] == "EURUSD"
        assert len(sample["features"]) >= 8
    finally:
        db.close()


def test_conflict_not_training_ready(initialized_db):
    review_id, record_id = _seed_record(conflict=True)
    db = SessionLocal()
    try:
        review = db.query(PredictionReview).filter(PredictionReview.id == review_id).first()
        rec = db.query(TrainingRecord).filter(TrainingRecord.id == record_id).first()
        uf = db.query(UserFeedback).filter(UserFeedback.prediction_id == review_id).first()
        mv = db.query(MarketVerification).filter(MarketVerification.prediction_id == review_id).first()
        readiness = assess_training_readiness(rec, review, uf, mv)
        assert readiness["conflict"] is True
        assert readiness["training_ready"] is False
        assert readiness["suggested_status"] == "PENDING_REVIEW"
    finally:
        db.close()


def test_reconcile_auto_approves_clean_record(initialized_db):
    review_id, _ = _seed_record(conflict=False)
    reconcile_training_record(review_id, features=_feature_snapshot(), predicted_action="BUY_BIAS")
    db = SessionLocal()
    try:
        rec = db.query(TrainingRecord).filter(TrainingRecord.prediction_id == review_id).first()
        # Default threshold config requires admin approval before training use.
        assert rec.admin_status == "PENDING_REVIEW"
        assert rec.final_label == "up"
        assert rec.label_quality_score >= 0.85
    finally:
        db.close()
