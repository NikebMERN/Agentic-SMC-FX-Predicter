"""Frozen meta-feature schema for WILL_RULE_SIGNAL_WIN models."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

FEATURE_SCHEMA_VERSION = "v1"


class MetaFeatureSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = FEATURE_SCHEMA_VERSION
    symbol: str
    interval: str
    trading_style: str = "intraday"
    rule_direction: str | None = None
    rule_action: str
    rule_confidence: float = 0.0
    rule_score: float = 0.0
    bullish_score: float = 0.0
    bearish_score: float = 0.0
    confluence_count: int = 0
    veto_count: int = 0
    htf_bias: str = "NEUTRAL"
    htf_aligned: bool = False
    structure_trend: int = 0
    structure_events: int = 0
    has_displacement: bool = False
    has_sweep: bool = False
    has_fvg: bool = False
    has_order_block: bool = False
    premium_discount_zone: str = "equilibrium"
    premium_discount_position: float = 0.5
    killzone_active: bool = False
    session_weight: float = 0.5
    risk_reward: float | None = None
    sl_pips: float | None = None
    tp_pips: float | None = None
    atr: float = 0.0
    spread_ok: bool = True
    data_valid: bool = True
    execution_confirmed: bool = False
    score_htf_bias: float = 0.0
    score_structure: float = 0.0
    score_liquidity: float = 0.0
    score_displacement: float = 0.0
    score_zones: float = 0.0
    score_premium_discount: float = 0.0
    score_session: float = 0.0
    score_risk_filter: float = 0.0
    hour_of_day: int = 0
    day_of_week: int = 0
    threshold_version_id: int | None = None
    rule_engine_version: str = "v1"

    def feature_vector(self) -> dict[str, float | int | bool]:
        return self.model_dump(exclude={"schema_version", "symbol", "interval", "trading_style", "rule_action"})


def feature_names() -> list[str]:
    snap = MetaFeatureSnapshot(
        symbol="EURUSD",
        interval="60min",
        rule_action="BUY_BIAS",
    )
    return list(snap.feature_vector().keys())
