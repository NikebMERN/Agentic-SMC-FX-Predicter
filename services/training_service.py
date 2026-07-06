# services/training_service.py
"""Training records from verified predictions + user feedback reconciliation."""
from __future__ import annotations

import json
from datetime import datetime

from db.models import MarketVerification, PredictionReview, SignalOutcome, TrainingRecord, User, UserFeedback
from db.session import SessionLocal
from engine.confluence import ACTION_BUY, ACTION_NO_TRADE, ACTION_SELL, ACTION_WAIT
from services.feedback_fields import effective_outcome_feedback
from utils.config import INTERVAL as DEFAULT_INTERVAL
from utils.logger import get_logger

log = get_logger("services.training_service")

FEEDBACK_LABEL_MAP = {
    "ENTERED": None,
    "SUCCESSFUL": "correct",
    "FAILED": "wrong",
    "DID_NOT_TAKE": "skipped",
    "UNCLEAR": "unclear",
}

MARKET_LABEL_MAP = {
    "UP": "up",
    "DOWN": "down",
    "SIDEWAYS": "flat",
}

BULLISH = frozenset({ACTION_BUY, "BUY", "BUY_BIAS"})
BEARISH = frozenset({ACTION_SELL, "SELL", "SELL_BIAS"})
NON_TRADE = frozenset({ACTION_NO_TRADE, ACTION_WAIT, "NO_TRADE", "WAIT_FOR_CONFIRMATION"})

VALID_TRAINING_LABELS = frozenset({"up", "down", "flat"})
MIN_FEATURE_KEYS = 8
AUTO_REVIEW_STATUSES = frozenset({"PENDING_REVIEW", "NEEDS_MORE_DATA"})


def _review_interval(review: PredictionReview | None) -> str:
    if review and review.interval:
        return review.interval
    return DEFAULT_INTERVAL


def _effective_features(row: TrainingRecord, review: PredictionReview | None, features: dict | None) -> dict:
    parsed = _parse_features(row.features_json) if row.features_json else {}
    if len(parsed) >= MIN_FEATURE_KEYS:
        return parsed
    if features and len(features) >= MIN_FEATURE_KEYS:
        return features
    if review and review.features_json:
        from_review = _parse_features(review.features_json)
        if len(from_review) >= MIN_FEATURE_KEYS:
            return from_review
    return parsed or features or {}


def needs_manual_review(row: TrainingRecord) -> bool:
    """Only conflicts require admin accept/reject."""
    return bool(row.conflict and row.admin_status == "PENDING_REVIEW")


def _parse_features(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _user_aligns_with_market(user_feedback: str | None, actual_direction: str | None, predicted_action: str) -> bool | None:
    if not user_feedback or user_feedback in ("DID_NOT_TAKE", "UNCLEAR", "ENTERED"):
        return None
    if not actual_direction:
        return None
    favored = _market_favored_prediction(predicted_action, actual_direction)
    if favored is None:
        return None
    if user_feedback == "SUCCESSFUL":
        return favored
    if user_feedback == "FAILED":
        return not favored
    return None


META_BINARY_LABELS = frozenset({"win", "loss", "1", "0"})


def _meta_label_from_outcome(review: PredictionReview | None, db) -> str | None:
    if not review:
        return None
    so = db.query(SignalOutcome).filter(SignalOutcome.prediction_id == review.id).first()
    if not so or so.meta_label is None:
        return None
    return "win" if so.meta_label == 1 else "loss"


def build_training_sample(
    row: TrainingRecord,
    review: PredictionReview | None,
) -> dict | None:
    """Raw ML row: meta feature vector + verified label (prefer TP/SL outcome)."""
    if not review:
        return None
    features = _parse_features(row.features_json)
    meta = features.get("meta_features") or features
    if isinstance(meta, dict) and len(meta) >= MIN_FEATURE_KEYS:
        feature_source = meta
    elif len(features) >= MIN_FEATURE_KEYS:
        feature_source = features
    else:
        return None

    label = row.final_label
    if label in META_BINARY_LABELS or label in ("1", "0"):
        binary = 1 if label in ("win", "1") else 0
    elif label in VALID_TRAINING_LABELS:
        # Legacy direction labels — map to binary when action was trade
        action = review.predicted_action or ""
        if action in BULLISH and label == "up":
            binary = 1
        elif action in BEARISH and label == "down":
            binary = 1
        elif label == "flat":
            return None
        else:
            binary = 0
    else:
        return None

    cleaned = {
        k: (
            None if v is None
            else (1.0 if v is True else 0.0 if v is False else float(v))
        )
        for k, v in feature_source.items()
        if isinstance(v, (int, float, bool)) or v is None
    }
    if len(cleaned) < MIN_FEATURE_KEYS:
        return None
    return {
        "record_id": row.id,
        "prediction_id": row.prediction_id,
        "symbol": review.symbol,
        "interval": _review_interval(review),
        "label": binary,
        "features": cleaned,
    }


def assess_training_readiness(
    row: TrainingRecord,
    review: PredictionReview | None,
    uf: UserFeedback | None,
    mv: MarketVerification | None,
) -> dict:
    """Cross-check user feedback vs market verification and decide if ML-ready."""
    features = _parse_features(row.features_json)
    feature_count = len(features)
    blockers: list[str] = []
    user_feedback = effective_outcome_feedback(uf)
    market_direction = mv.actual_direction if mv else None
    market_outcome = mv.outcome if mv else None
    aligned = _user_aligns_with_market(
        user_feedback,
        market_direction,
        review.predicted_action if review else "",
    )

    if not review:
        blockers.append("Missing prediction review")
    if not mv or not market_direction:
        blockers.append("Market verification incomplete")
    if row.final_label not in VALID_TRAINING_LABELS and row.final_label not in META_BINARY_LABELS:
        blockers.append("No verified label (market or TP/SL outcome)")
    if feature_count < MIN_FEATURE_KEYS:
        blockers.append(f"Feature snapshot incomplete ({feature_count}/{MIN_FEATURE_KEYS} keys)")

    if row.conflict:
        blockers.append("User feedback conflicts with market direction")

    review_status = review.status if review else None
    if review_status == "verification_failed":
        blockers.append("Market verification failed")

    training_sample = build_training_sample(row, review) if not blockers else None
    training_ready = training_sample is not None and not row.conflict

    summary_parts = []
    if market_direction:
        summary_parts.append(f"Market {market_direction}")
    if market_outcome:
        summary_parts.append(f"outcome {market_outcome}")
    if user_feedback:
        summary_parts.append(f"user {user_feedback}")
    if aligned is True:
        summary_parts.append("aligned")
    elif aligned is False:
        summary_parts.append("misaligned")
    elif user_feedback:
        summary_parts.append("user skipped/unclear — using market label")
    summary = " · ".join(summary_parts) if summary_parts else "Awaiting cross-check data"

    suggested_status = row.admin_status
    suggested_quality = row.label_quality_score
    training_cfg = None
    if review:
        from services.threshold_service import resolve_thresholds_model
        training_cfg = resolve_thresholds_model(review.symbol, review.interval, review.horizon or "intraday").training
    min_quality = training_cfg.min_training_label_quality if training_cfg else 0.8
    auto_approve = training_cfg.auto_approve_clean_records if training_cfg else False
    if row.admin_status in AUTO_REVIEW_STATUSES:
        if row.conflict and training_cfg and training_cfg.conflict_requires_admin_review:
            suggested_status = "PENDING_REVIEW"
            suggested_quality = 0.35
        elif review_status == "verification_failed" or not mv or not market_direction:
            suggested_status = "NEEDS_MORE_DATA"
            suggested_quality = 0.2
        elif feature_count < MIN_FEATURE_KEYS or row.final_label not in VALID_TRAINING_LABELS:
            suggested_status = "NEEDS_MORE_DATA"
            suggested_quality = 0.25
        elif auto_approve and training_ready:
            suggested_status = "APPROVED"
            suggested_quality = max(min_quality, 0.92 if aligned is True else 0.85)
        else:
            suggested_status = "APPROVED" if not (training_cfg and training_cfg.admin_approval_required_for_training) else "PENDING_REVIEW"
            suggested_quality = max(min_quality, 0.92 if aligned is True else 0.85)

    requires_manual = row.conflict and suggested_status == "PENDING_REVIEW"

    return {
        "market_verified": bool(mv and market_direction),
        "market_direction": market_direction,
        "market_outcome": market_outcome,
        "user_feedback": user_feedback,
        "user_aligns_with_market": aligned,
        "conflict": row.conflict,
        "features_present": feature_count,
        "features_sufficient": feature_count >= MIN_FEATURE_KEYS,
        "label": row.final_label,
        "blockers": blockers,
        "summary": summary,
        "training_ready": training_ready,
        "training_sample": training_sample,
        "suggested_status": suggested_status,
        "suggested_quality_score": suggested_quality,
        "requires_manual_review": requires_manual,
    }


def _apply_cross_check(row: TrainingRecord, review: PredictionReview | None, uf: UserFeedback | None, mv: MarketVerification | None) -> dict:
    readiness = assess_training_readiness(row, review, uf, mv)
    if row.admin_status in AUTO_REVIEW_STATUSES:
        row.admin_status = readiness["suggested_status"]
        row.label_quality_score = readiness["suggested_quality_score"]
        if row.admin_status == "APPROVED" and not row.reviewed_at:
            row.reviewed_at = datetime.utcnow()
            row.admin_notes = row.admin_notes or "Auto-approved: market verified, training sample ready"
    return readiness


def _market_favored_prediction(predicted_action: str, actual_direction: str | None) -> bool | None:
    if not actual_direction:
        return None
    if predicted_action in BULLISH:
        return actual_direction == "UP"
    if predicted_action in BEARISH:
        return actual_direction == "DOWN"
    if predicted_action in NON_TRADE:
        return actual_direction == "SIDEWAYS"
    return None


def detect_conflict(
    user_feedback: str | None,
    actual_direction: str | None,
    predicted_action: str,
) -> bool:
    """True when user feedback disagrees with measured market direction."""
    if not user_feedback or user_feedback in ("DID_NOT_TAKE", "UNCLEAR", "ENTERED"):
        return False
    favored = _market_favored_prediction(predicted_action, actual_direction)
    if favored is None:
        return False
    if user_feedback == "SUCCESSFUL":
        return not favored
    if user_feedback == "FAILED":
        return favored
    return False


def reconcile_training_record(
    prediction_id: int,
    *,
    features: dict | None = None,
    predicted_action: str | None = None,
) -> TrainingRecord | None:
    db = SessionLocal()
    try:
        review = db.query(PredictionReview).filter(PredictionReview.id == prediction_id).first()
        uf = db.query(UserFeedback).filter(UserFeedback.prediction_id == prediction_id).first()
        mv = db.query(MarketVerification).filter(MarketVerification.prediction_id == prediction_id).first()
        so = db.query(SignalOutcome).filter(SignalOutcome.prediction_id == prediction_id).first()
        row = db.query(TrainingRecord).filter(TrainingRecord.prediction_id == prediction_id).first()
        action = predicted_action or (review.predicted_action if review else "")

        label_market = MARKET_LABEL_MAP.get(mv.actual_direction) if mv and mv.actual_direction else None
        outcome_fb = effective_outcome_feedback(uf)
        label_user = FEEDBACK_LABEL_MAP.get(outcome_fb) if outcome_fb else None
        meta_label = _meta_label_from_outcome(review, db)
        conflict = detect_conflict(
            outcome_fb,
            mv.actual_direction if mv else None,
            action,
        )
        if meta_label:
            final_label = meta_label
        else:
            final_label = label_market or ("flat" if action in NON_TRADE else None)

        if not row:
            row = TrainingRecord(prediction_id=prediction_id)
            db.add(row)

        was_conflict = row.conflict
        row.user_feedback_id = uf.id if uf else row.user_feedback_id
        row.market_verification_id = mv.id if mv else row.market_verification_id
        effective = _effective_features(row, review, features)
        if effective:
            row.features_json = json.dumps(effective)
        row.label_from_market = label_market
        row.label_from_user = label_user
        row.final_label = final_label
        row.conflict = conflict
        readiness = _apply_cross_check(row, review, uf, mv)
        db.commit()
        db.refresh(row)

        if conflict and not was_conflict and review and review.user_id:
            user = db.query(User).filter(User.id == review.user_id).first()
            username = user.username if user else f"user#{review.user_id}"
            notify_admin(
                f"Feedback conflict: {username} reported {outcome_fb or '?'} on "
                f"{review.symbol} {review.predicted_action}, but market moved {mv.actual_direction if mv else '?'}."
            )
            log.warning(
                "Feedback conflict for user %s review %s: user=%s market=%s",
                username, prediction_id, outcome_fb, mv.actual_direction if mv else None,
            )
        if readiness.get("training_ready"):
            log.info(
                "Training record %s ready for model: %s %s label=%s features=%s",
                row.id,
                review.symbol if review else "?",
                review.interval if review else "?",
                row.final_label,
                readiness.get("features_present"),
            )
        return row
    except Exception:
        log.exception("Failed to reconcile training record for prediction %s", prediction_id)
        db.rollback()
        return None
    finally:
        db.close()


def sync_training_records(limit: int = 500) -> int:
    """Re-run cross-check and auto-approve clean records (backfill stale rows)."""
    db = SessionLocal()
    try:
        rows = db.query(TrainingRecord).order_by(TrainingRecord.id.desc()).limit(limit).all()
        prediction_ids = [r.prediction_id for r in rows]
    finally:
        db.close()
    updated = 0
    for pid in prediction_ids:
        if reconcile_training_record(pid):
            updated += 1
    return updated


def list_training_records(
    status: str | None = None,
    limit: int = 100,
    *,
    ready_only: bool = False,
    conflicts_only: bool = False,
) -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(TrainingRecord).order_by(TrainingRecord.id.desc())
        if conflicts_only:
            q = q.filter(TrainingRecord.conflict.is_(True), TrainingRecord.admin_status == "PENDING_REVIEW")
        elif status:
            q = q.filter(TrainingRecord.admin_status == status.upper())
        rows = q.limit(limit).all()
        out = []
        for r in rows:
            review = db.query(PredictionReview).filter(PredictionReview.id == r.prediction_id).first()
            user = None
            if review and review.user_id:
                user = db.query(User).filter(User.id == review.user_id).first()
            uf = db.query(UserFeedback).filter(UserFeedback.prediction_id == r.prediction_id).first()
            mv = db.query(MarketVerification).filter(MarketVerification.prediction_id == r.prediction_id).first()
            readiness = assess_training_readiness(r, review, uf, mv)
            if ready_only and not readiness["training_ready"]:
                continue
            quality = r.label_quality_score
            if quality is None:
                quality = readiness["suggested_quality_score"]
            reviewed_at = r.reviewed_at.isoformat() if r.reviewed_at else None
            if not reviewed_at and r.admin_status == "APPROVED":
                reviewed_at = r.created_at.isoformat() if r.created_at else None
            out.append({
                "id": r.id,
                "prediction_id": r.prediction_id,
                "user_id": review.user_id if review else None,
                "username": user.username if user else None,
                "symbol": review.symbol if review else None,
                "interval": _review_interval(review),
                "predicted_action": review.predicted_action if review else None,
                "user_feedback": effective_outcome_feedback(uf),
                "market_direction": mv.actual_direction if mv else None,
                "market_outcome": mv.outcome if mv else None,
                "label_from_market": r.label_from_market or (
                    MARKET_LABEL_MAP.get(mv.actual_direction) if mv and mv.actual_direction else None
                ),
                "label_from_user": r.label_from_user,
                "final_label": r.final_label or readiness.get("label"),
                "conflict": r.conflict,
                "user_truthful": not r.conflict if uf and mv else None,
                "label_quality_score": quality,
                "admin_status": r.admin_status,
                "admin_notes": r.admin_notes,
                "auto_approved": r.admin_status == "APPROVED" and (r.admin_notes or "").startswith("Auto-approved"),
                "needs_manual_review": needs_manual_review(r),
                "reviewed_at": reviewed_at,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "cross_check": {
                    "summary": readiness["summary"],
                    "market_verified": readiness["market_verified"],
                    "user_aligns_with_market": readiness["user_aligns_with_market"],
                    "blockers": readiness["blockers"],
                },
                "training_ready": readiness["training_ready"],
                "training_sample": readiness["training_sample"],
            })
        return out
    finally:
        db.close()


def review_training_record(
    record_id: int,
    admin_status: str,
    admin_notes: str | None = None,
    label_quality_score: float | None = None,
) -> TrainingRecord | None:
    db = SessionLocal()
    try:
        row = db.query(TrainingRecord).filter(TrainingRecord.id == record_id).first()
        if not row:
            return None
        row.admin_status = admin_status.upper()
        row.admin_notes = admin_notes
        if label_quality_score is not None:
            row.label_quality_score = label_quality_score
        row.reviewed_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


def export_approved_records(limit: int = 5000) -> list[dict]:
    return export_training_dataset(limit=limit, approved_only=True)


def export_training_dataset(
    limit: int = 5000,
    *,
    symbol: str | None = None,
    approved_only: bool = True,
) -> list[dict]:
    """Export raw ML rows: features + verified market label, cross-checked."""
    db = SessionLocal()
    try:
        q = db.query(TrainingRecord).order_by(TrainingRecord.id.desc())
        if approved_only:
            q = q.filter(TrainingRecord.admin_status == "APPROVED")
        rows = q.limit(limit).all()
        out = []
        for r in rows:
            review = db.query(PredictionReview).filter(PredictionReview.id == r.prediction_id).first()
            if symbol and (not review or review.symbol.upper() != symbol.upper()):
                continue
            uf = db.query(UserFeedback).filter(UserFeedback.prediction_id == r.prediction_id).first()
            mv = db.query(MarketVerification).filter(MarketVerification.prediction_id == r.prediction_id).first()
            readiness = assess_training_readiness(r, review, uf, mv)
            sample = readiness.get("training_sample")
            if not sample:
                continue
            out.append({
                **sample,
                "metadata": {
                    "predicted_action": review.predicted_action if review else None,
                    "market_direction": mv.actual_direction if mv else None,
                    "market_outcome": mv.outcome if mv else None,
                    "user_feedback": effective_outcome_feedback(uf),
                    "conflict": r.conflict,
                    "label_quality_score": r.label_quality_score,
                    "admin_status": r.admin_status,
                    "cross_check_summary": readiness["summary"],
                },
            })
        return out
    finally:
        db.close()
