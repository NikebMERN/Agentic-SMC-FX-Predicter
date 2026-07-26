"""Evidence-based feedback validation and dataset-tier assignment."""
from __future__ import annotations

import hashlib
import json

from db.models import TrainingRecord, UserFeedback
from db.session import SessionLocal

TIERS = {"PENDING_REVIEW", "APPROVED", "REJECTED", "GOLD"}


def feedback_hash(feedback: UserFeedback) -> str:
    payload = {
        "user_id": feedback.user_id,
        "trade_entry": feedback.trade_entry,
        "feedback": feedback.feedback,
        "comment": (feedback.comment or "").strip().lower(),
        "screenshot_path": feedback.screenshot_path,
        "account_type": feedback.account_type,
        "execution_delay_ms": feedback.execution_delay_ms,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def validate_feedback(record: TrainingRecord, review, feedback, verification, signal_outcome) -> dict:
    reasons = []
    score = 0.0
    duplicate_id = None
    if not review:
        reasons.append("prediction missing")
    else:
        score += 0.15
    if verification and verification.verified_at and verification.outcome:
        score += 0.30
    else:
        reasons.append("market replay incomplete")
    if signal_outcome and signal_outcome.meta_label is not None:
        score += 0.25
    else:
        reasons.append("SL/TP path not verified")
    if feedback:
        digest = feedback_hash(feedback)
        feedback.payload_hash = digest
        db = SessionLocal()
        try:
            duplicate = db.query(UserFeedback).filter(
                UserFeedback.payload_hash == digest,
                UserFeedback.id != feedback.id,
            ).first()
            duplicate_id = duplicate.id if duplicate else None
        finally:
            db.close()
        if duplicate_id:
            reasons.append(f"duplicate feedback #{duplicate_id}")
        else:
            score += 0.10
        if feedback.screenshot_path:
            score += 0.05
        if feedback.execution_delay_ms is not None and feedback.execution_delay_ms >= 0:
            score += 0.05
    else:
        reasons.append("user feedback absent")
    if record.conflict:
        reasons.append("user outcome conflicts with market")
        score -= 0.25
    if review and review.risk_reward_achieved is not None:
        score += 0.10

    score = max(0.0, min(1.0, score))
    suspicious = bool(duplicate_id or record.conflict)
    if suspicious or score < 0.45:
        tier = "REJECTED"
    elif score >= 0.90 and record.institutional_example:
        tier = "GOLD"
    elif score >= 0.75:
        tier = "APPROVED"
    else:
        tier = "PENDING_REVIEW"
    return {
        "tier": tier, "score": score, "reasons": reasons,
        "suspicious": suspicious, "duplicate_feedback_id": duplicate_id,
    }
