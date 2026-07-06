"""Pair/timeframe performance aggregation for leaderboard."""
from __future__ import annotations

from datetime import datetime

from db.models import PairPerformance, PredictionReview, SignalOutcome
from db.session import SessionLocal
from utils.logger import get_logger

log = get_logger("services.pair_performance")


def _status_recommendation(win_rate: float | None, precision: float | None, sample_count: int) -> str:
    if sample_count < 10:
        return "WATCHLIST"
    if win_rate is None or precision is None:
        return "WATCHLIST"
    if win_rate < 0.40 or precision < 0.45:
        return "DISABLE"
    if win_rate < 0.50 or precision < 0.50:
        return "WATCHLIST"
    return "ACTIVE"


def aggregate_pair_performance(
    symbol: str,
    interval: str,
    trading_style: str = "intraday",
    model_version_id: int | None = None,
) -> PairPerformance | None:
    db = SessionLocal()
    try:
        q = (
            db.query(PredictionReview, SignalOutcome)
            .outerjoin(SignalOutcome, SignalOutcome.prediction_id == PredictionReview.id)
            .filter(
                PredictionReview.symbol == symbol.upper(),
                PredictionReview.interval == interval,
                PredictionReview.trading_style == trading_style,
            )
        )
        rows = q.all()
        if not rows:
            return None

        total = len(rows)
        accepted = sum(
            1 for pr, _ in rows
            if pr.predicted_action.upper() in ("BUY_BIAS", "SELL_BIAS", "BUY", "SELL")
        )
        rejected = total - accepted
        labels = [so.meta_label for _, so in rows if so and so.meta_label is not None]
        win_rate = sum(labels) / len(labels) if labels else None
        precision = win_rate  # binary meta-label proxy

        confidences = [pr.final_confidence or pr.predicted_confidence for pr, _ in rows if pr.predicted_confidence]
        avg_conf = sum(confidences) / len(confidences) if confidences else None

        rec = _status_recommendation(win_rate, precision, len(labels))
        perf = (
            db.query(PairPerformance)
            .filter(
                PairPerformance.symbol == symbol.upper(),
                PairPerformance.interval == interval,
                PairPerformance.trading_style == trading_style,
            )
            .first()
        )
        if not perf:
            perf = PairPerformance(
                symbol=symbol.upper(),
                interval=interval,
                trading_style=trading_style,
            )
            db.add(perf)

        perf.model_version_id = model_version_id
        perf.total_signals = total
        perf.accepted_signals = accepted
        perf.rejected_signals = rejected
        perf.win_rate = win_rate
        perf.precision = precision
        perf.avg_confidence = avg_conf
        perf.status_recommendation = rec
        perf.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(perf)
        return perf
    except Exception:
        log.exception("Pair performance aggregation failed")
        db.rollback()
        return None
    finally:
        db.close()


def list_pair_performance(limit: int = 100) -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.query(PairPerformance).order_by(PairPerformance.updated_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "interval": r.interval,
                "trading_style": r.trading_style,
                "total_signals": r.total_signals,
                "accepted_signals": r.accepted_signals,
                "rejected_signals": r.rejected_signals,
                "win_rate": r.win_rate,
                "precision": r.precision,
                "avg_confidence": r.avg_confidence,
                "brier_score": r.brier_score,
                "status_recommendation": r.status_recommendation,
                "model_version_id": r.model_version_id,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()
