# services/feedback_service.py
"""Persist closed trade/signal outcomes as labeled training samples."""
import json

import pandas as pd

from db.models import FeedbackSample, ModelVersion
from db.session import SessionLocal
from utils.logger import get_logger

log = get_logger("services.feedback_service")


def record_feedback_sample(
    symbol: str,
    interval: str,
    features: dict,
    label: str,
    signal_id: int | None = None,
    trade_id: int | None = None,
):
    """Save a labeled feature vector for future training."""
    db = SessionLocal()
    try:
        db.add(FeedbackSample(
            symbol=symbol.upper(),
            interval=interval,
            features_json=json.dumps(features),
            label=label,
            signal_id=signal_id,
            trade_id=trade_id,
            used_in_training=False,
        ))
        db.commit()
    except Exception:
        log.exception("Failed to record feedback sample")
        db.rollback()
    finally:
        db.close()


def record_trade_outcome(trade, signal, label: str | None = None, features: dict | None = None):
    """Save a feedback sample from a closed trade or signal."""
    symbol = trade.symbol if trade else signal.symbol
    interval = "60min"
    if label is None and trade:
        if trade.outcome_score and trade.outcome_score > 0:
            label = "up" if trade.side == "BUY" else "down"
        elif trade.outcome_score and trade.outcome_score < 0:
            label = "down" if trade.side == "BUY" else "up"
        else:
            label = "flat"
    if label is None and signal and signal.outcome:
        label = "up" if signal.outcome == "win" and signal.side == "BUY" else (
            "down" if signal.outcome == "win" and signal.side == "SELL" else "flat"
        )
    if label is None:
        return

    if features is None:
        features = {
            "symbol": symbol,
            "side": trade.side if trade else signal.side,
            "confidence": trade.confidence if trade else signal.confidence,
            "entry": trade.entry_price if trade else signal.entry_price,
        }

    record_feedback_sample(
        symbol=symbol,
        interval=interval,
        features=features,
        label=label,
        signal_id=signal.id if signal else None,
        trade_id=trade.id if trade else None,
    )


def get_approved_training_samples(symbol: str | None = None, limit: int = 5000) -> list[dict]:
    """Approved training records for retraining (replaces auto FeedbackSample for feedback loop)."""
    from db.models import TrainingRecord
    db = SessionLocal()
    try:
        q = db.query(TrainingRecord).filter(TrainingRecord.admin_status == "APPROVED")
        rows = q.order_by(TrainingRecord.id.desc()).limit(limit).all()
        out = []
        for r in rows:
            if not r.final_label or not r.features_json:
                continue
            feat = json.loads(r.features_json)
            if symbol:
                from db.models import PredictionReview
                pr = db.query(PredictionReview).filter(PredictionReview.id == r.prediction_id).first()
                if not pr or pr.symbol.upper() != symbol.upper():
                    continue
            out.append({
                "id": r.id,
                "features": feat,
                "label": r.final_label,
            })
        return out
    except Exception:
        log.debug("Approved training samples unavailable")
        return []
    finally:
        db.close()


def approved_training_to_dataframe(pending: list[dict], feature_names: list[str]):
    return feedback_to_dataframe(pending, feature_names)


def mark_training_records_used(record_ids: list[int]):
    """No-op placeholder — approved records stay for audit; training marks via model version."""
    if record_ids:
        log.debug("Used %d approved training records", len(record_ids))


def get_pending_feedback(symbol: str, interval: str = "60min") -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(FeedbackSample)
            .filter(
                FeedbackSample.symbol == symbol.upper(),
                FeedbackSample.interval == interval,
                FeedbackSample.used_in_training.is_(False),
            )
            .all()
        )
        return [
            {"id": r.id, "features": json.loads(r.features_json), "label": r.label}
            for r in rows
        ]
    finally:
        db.close()


def feedback_to_dataframe(pending: list[dict], feature_names: list[str]) -> tuple[pd.DataFrame, pd.Series, list[int]]:
    """Convert pending feedback rows into training rows aligned to feature_names."""
    if not pending:
        return pd.DataFrame(columns=feature_names), pd.Series(dtype=str), []

    rows, labels, ids = [], [], []
    for item in pending:
        feat = item["features"]
        row = {col: feat.get(col, 0.0) for col in feature_names}
        rows.append(row)
        labels.append(item["label"])
        ids.append(item["id"])
    return pd.DataFrame(rows), pd.Series(labels, dtype=str), ids


def mark_samples_used(sample_ids: list[int]):
    if not sample_ids:
        return
    db = SessionLocal()
    try:
        db.query(FeedbackSample).filter(FeedbackSample.id.in_(sample_ids)).update(
            {FeedbackSample.used_in_training: True}, synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def get_active_model_version(symbol: str, interval: str = "60min") -> ModelVersion | None:
    db = SessionLocal()
    try:
        return (
            db.query(ModelVersion)
            .filter(
                ModelVersion.symbol == symbol.upper(),
                ModelVersion.interval == interval,
                ModelVersion.is_active.is_(True),
            )
            .first()
        )
    finally:
        db.close()


def get_model_candidates(symbol: str | None = None, interval: str = "60min") -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(ModelVersion).filter(ModelVersion.is_active.is_(False))
        if symbol:
            q = q.filter(ModelVersion.symbol == symbol.upper(), ModelVersion.interval == interval)
        rows = q.order_by(ModelVersion.id.desc()).limit(50).all()
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "interval": r.interval,
                "path": r.path,
                "val_accuracy": r.val_accuracy,
                "samples": r.samples,
                "trained_at": r.trained_at.isoformat() if r.trained_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


def promote_model_version(version_id: int) -> ModelVersion | None:
    db = SessionLocal()
    try:
        row = db.query(ModelVersion).filter(ModelVersion.id == version_id).first()
        if not row:
            return None
        db.query(ModelVersion).filter(
            ModelVersion.symbol == row.symbol,
            ModelVersion.interval == row.interval,
        ).update({ModelVersion.is_active: False}, synchronize_session=False)
        row.is_active = True
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


def save_model_version(symbol: str, interval: str, path: str, metrics: dict, promote: bool) -> ModelVersion:
    db = SessionLocal()
    try:
        if promote:
            db.query(ModelVersion).filter(
                ModelVersion.symbol == symbol.upper(),
                ModelVersion.interval == interval,
            ).update({ModelVersion.is_active: False}, synchronize_session=False)
        row = ModelVersion(
            symbol=symbol.upper(),
            interval=interval,
            path=path,
            val_accuracy=metrics.get("val_accuracy", 0.0),
            samples=metrics.get("samples", 0),
            is_active=promote,
            metrics_json=json.dumps(metrics),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()
