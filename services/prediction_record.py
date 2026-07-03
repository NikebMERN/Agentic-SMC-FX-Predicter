# services/prediction_record.py
"""Shared prediction review creation for web API and Telegram bot."""
from __future__ import annotations

from services.prediction_review import create_review


def record_prediction_from_result(
    *,
    user_id: int | None,
    result: dict,
    horizon: str = "intraday",
    signal_id: int | None = None,
    source: str = "web",
):
    """Persist a pipeline result as a tracked prediction review."""
    decision = result.get("decision") or {}
    entry = decision.get("entry")
    if entry is None and result.get("analysis_summary"):
        entry = result["analysis_summary"].get("price")
    return create_review(
        signal_id=signal_id,
        user_id=user_id,
        symbol=result.get("symbol", ""),
        interval=result.get("interval", "60min"),
        predicted_action=decision.get("action", "NO_TRADE"),
        predicted_confidence=float(decision.get("confidence", 0)),
        entry_price=float(entry or 0),
        features=result.get("feature_snapshot"),
        horizon=horizon,
        direction=decision.get("direction"),
        invalidation_price=decision.get("invalidation_price"),
        target_price=decision.get("target_liquidity"),
        component_scores=decision.get("component_scores"),
        signals=result.get("structured_signals"),
        strategy_mode=result.get("strategy", "both"),
        snapshot_records=result.get("candle_snapshot"),
        source=source,
    )
