"""Build meta feature vector from analysis + rule decision at signal time."""
from __future__ import annotations

from datetime import datetime

from engine.confluence import ACTION_BUY, ACTION_SELL
from schemas.meta_feature_schema import FEATURE_SCHEMA_VERSION, MetaFeatureSnapshot

RULE_ENGINE_VERSION = "v1"


def _direction_from_action(action: str, direction: str | None) -> str | None:
    if direction:
        return direction
    if action in (ACTION_BUY, "BUY", "BUY_BIAS"):
        return "bullish"
    if action in (ACTION_SELL, "SELL", "SELL_BIAS"):
        return "bearish"
    return None


def build_meta_features(
    analysis: dict,
    decision: dict,
    *,
    spread_ok: bool = True,
    data_valid: bool = True,
    threshold_version_id: int | None = None,
) -> MetaFeatureSnapshot:
    """Snapshot meta features for ML quality gate and training."""
    action = decision.get("action", "NO_TRADE")
    direction = _direction_from_action(action, decision.get("direction"))
    htf = analysis.get("htf_bias") or {}
    htf_label = analysis.get("higher_timeframe_bias") or htf.get("bias_label", "NEUTRAL")
    htf_dir = htf.get("direction", "neutral")
    pd_info = analysis.get("premium_discount") or decision.get("premium_discount") or {}
    events = analysis.get("structure", {}).get("events", [])
    last_ev = events[-1] if events else {}
    session = analysis.get("session") or {}
    comps = decision.get("component_scores") or {}
    now = analysis.get("last_time")
    if hasattr(now, "to_pydatetime"):
        now = now.to_pydatetime()
    elif isinstance(now, str):
        try:
            now = datetime.fromisoformat(now.replace("Z", "+00:00"))
        except ValueError:
            now = datetime.utcnow()
    elif now is None:
        now = datetime.utcnow()

    hour_of_day = int(getattr(now, "hour", 12))
    day_of_week = int(now.weekday()) if hasattr(now, "weekday") and callable(now.weekday) else 0

    return MetaFeatureSnapshot(
        schema_version=FEATURE_SCHEMA_VERSION,
        symbol=analysis.get("symbol", ""),
        interval=analysis.get("interval", "60min"),
        trading_style=analysis.get("trading_style", "intraday"),
        rule_direction=direction,
        rule_action=action,
        rule_confidence=float(decision.get("rule_confidence", decision.get("confidence", 0))),
        rule_score=float(decision.get("score", 0)),
        bullish_score=float(decision.get("scores", {}).get("bullish", 0)),
        bearish_score=float(decision.get("scores", {}).get("bearish", 0)),
        confluence_count=int(decision.get("confluences", 0)),
        veto_count=len(decision.get("vetoes") or []),
        htf_bias=str(htf_label),
        htf_aligned=bool(direction and htf_dir == direction),
        structure_trend=int(analysis.get("structure", {}).get("trend", 0)),
        structure_events=len(events),
        has_displacement=bool(last_ev.get("displacement")),
        has_sweep=any(s.get("bias") == direction for s in analysis.get("sweeps", [])),
        has_fvg=bool(analysis.get("fvgs")),
        has_order_block=bool(analysis.get("valid_order_blocks")),
        premium_discount_zone=str(pd_info.get("zone", "equilibrium")),
        premium_discount_position=float(pd_info.get("position", 0.5)),
        killzone_active=bool(analysis.get("killzone")),
        session_weight=float(session.get("weight", 0.5)),
        risk_reward=decision.get("risk_reward"),
        sl_pips=decision.get("sl_pips"),
        tp_pips=decision.get("tp_pips"),
        atr=float(analysis.get("atr", 0)),
        spread_ok=spread_ok,
        data_valid=data_valid,
        execution_confirmed=bool(analysis.get("execution_confirmed", False)),
        score_htf_bias=float(comps.get("htf_bias", 0)),
        score_structure=float(comps.get("structure", 0)),
        score_liquidity=float(comps.get("liquidity", 0)),
        score_displacement=float(comps.get("displacement", 0)),
        score_zones=float(comps.get("zones", 0)),
        score_premium_discount=float(comps.get("premium_discount", 0)),
        score_session=float(comps.get("session", 0)),
        score_risk_filter=float(comps.get("risk_filter", 0)),
        hour_of_day=hour_of_day,
        day_of_week=day_of_week,
        threshold_version_id=threshold_version_id,
        rule_engine_version=RULE_ENGINE_VERSION,
    )
