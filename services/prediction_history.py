# services/prediction_history.py
"""User-facing prediction history stats and chart candle data."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import pandas as pd

from db.models import PredictionReview
from db.session import SessionLocal
from engine.data import csv_path, get_data, load_ohlc_csv
from services.prediction_review import list_reviews
from utils.logger import get_logger

log = get_logger("services.prediction_history")


def _count_outcomes(reviews: list[PredictionReview]) -> dict:
    correct = incorrect = pending = 0
    by_action: dict[str, int] = {}
    for r in reviews:
        by_action[r.predicted_action] = by_action.get(r.predicted_action, 0) + 1
        if r.was_correct is True:
            correct += 1
        elif r.was_correct is False:
            incorrect += 1
        else:
            pending += 1
    total = len(reviews)
    return {
        "total": total,
        "correct": correct,
        "incorrect": incorrect,
        "pending": pending,
        "accuracy": round(correct / (correct + incorrect), 4) if (correct + incorrect) else None,
        "by_action": by_action,
    }


def get_user_history(user_id: int, hours: int = 24, limit: int = 100) -> dict:
    """Summary stats and review list for the rolling window."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    db = SessionLocal()
    try:
        window_rows = (
            db.query(PredictionReview)
            .filter(
                PredictionReview.user_id == user_id,
                PredictionReview.predicted_at >= cutoff,
            )
            .order_by(PredictionReview.id.desc())
            .all()
        )
        all_rows = (
            db.query(PredictionReview)
            .filter(PredictionReview.user_id == user_id)
            .order_by(PredictionReview.id.desc())
            .limit(limit)
            .all()
        )
        all_reviews = list_reviews(user_id=user_id, limit=limit)
        cutoff_iso = cutoff.isoformat()
        reviews_24h = [
            r for r in all_reviews
            if r.get("predicted_at") and r["predicted_at"] >= cutoff_iso
        ]
        return {
            "window_hours": hours,
            "interval": "60min",
            "stats_24h": _count_outcomes(window_rows),
            "stats_all_time": _count_outcomes(all_rows),
            "reviews_24h": reviews_24h,
            "reviews": all_reviews,
        }
    finally:
        db.close()


def _load_snapshot(path: str) -> list[dict]:
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except Exception as exc:
        log.warning("Unreadable snapshot %s: %s", path, exc)
    return []


def _df_to_candles(df: pd.DataFrame, limit: int = 48) -> list[dict]:
    tail = df.tail(limit)
    out = []
    for ts, row in tail.iterrows():
        out.append({
            "time": str(ts),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row.get("Volume", 0)),
        })
    return out


def get_review_candles(user_id: int, review_id: int, bars: int = 48) -> dict | None:
    """Return 60min OHLC bars for a user's prediction chart."""
    db = SessionLocal()
    try:
        review = (
            db.query(PredictionReview)
            .filter(PredictionReview.id == review_id, PredictionReview.user_id == user_id)
            .first()
        )
        if not review:
            return None

        candles = _load_snapshot(review.snapshot_path)
        source = "snapshot"

        if not candles:
            interval = review.interval or "60min"
            try:
                df, data_source = get_data(review.symbol, interval, fetch=False)
                source = data_source
            except Exception:
                path = csv_path(review.symbol, interval)
                if not os.path.isfile(path):
                    return {
                        "review_id": review_id,
                        "symbol": review.symbol,
                        "interval": interval,
                        "candles": [],
                        "source": "none",
                        "entry_price": review.entry_price,
                        "target_price": review.target_price,
                        "invalidation_price": review.invalidation_price,
                        "predicted_at": review.predicted_at.isoformat() if review.predicted_at else None,
                        "actual_price": review.actual_price,
                    }
                df = load_ohlc_csv(path)
                source = "cache"

            if review.predicted_at and not df.empty:
                pred_ts = pd.Timestamp(review.predicted_at)
                if pred_ts.tzinfo is None:
                    pred_ts = pred_ts.tz_localize(None)
                idx = df.index
                if hasattr(idx, "tz") and idx.tz is not None and pred_ts.tzinfo is None:
                    pred_ts = pred_ts.tz_localize(idx.tz)
                mask = idx <= pred_ts
                if mask.any():
                    end_pos = mask.sum()
                    start = max(0, end_pos - bars)
                    df = df.iloc[start:end_pos]
                else:
                    df = df.tail(bars)
            else:
                df = df.tail(bars)
            candles = _df_to_candles(df, bars)

        return {
            "review_id": review_id,
            "symbol": review.symbol,
            "interval": review.interval or "60min",
            "candles": candles[-bars:],
            "source": source,
            "entry_price": review.entry_price,
            "target_price": review.target_price,
            "invalidation_price": review.invalidation_price,
            "predicted_at": review.predicted_at.isoformat() if review.predicted_at else None,
            "actual_price": review.actual_price,
            "predicted_action": review.predicted_action,
            "was_correct": review.was_correct,
        }
    finally:
        db.close()
