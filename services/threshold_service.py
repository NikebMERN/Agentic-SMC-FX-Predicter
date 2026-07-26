# services/threshold_service.py
"""Load, resolve, version, and cache SMC/ICT threshold configuration."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from config.smc_ict_thresholds import DEFAULT_THRESHOLDS, resolve_thresholds as _resolve_pure
from db.models import PairThreshold, ThresholdOverride, ThresholdVersion
from db.session import SessionLocal
from schemas.threshold_schema import (
    SmcIctThresholds,
    ThresholdValidationError,
    merge_threshold_patch,
    validate_threshold_config,
)
from utils.logger import get_logger

log = get_logger("services.threshold_service")

_CACHE_TTL_SECONDS = 60
_cache: dict[tuple, tuple[float, SmcIctThresholds, int | None]] = {}


def _flat_to_nested_patch(flat: dict) -> dict:
    """Convert legacy flat threshold keys to nested section patches."""
    patch: dict[str, Any] = {}
    if "minCandlesRequired" in flat:
        patch.setdefault("data_quality", {})["min_candles_required"] = int(flat["minCandlesRequired"])
    if "minBosBreakPips" in flat:
        v = float(flat["minBosBreakPips"])
        patch.setdefault("bos", {}).update({
            "min_bos_break_pips_m5": v,
            "min_bos_break_pips_m15": v,
            "min_bos_break_pips_h1": v,
        })
    if "minChochBreakPips" in flat:
        v = float(flat["minChochBreakPips"])
        patch.setdefault("choch_mss", {}).update({
            "min_choch_break_pips_m5": v,
            "min_choch_break_pips_m15": v,
            "min_choch_break_pips_h1": v,
        })
    if "minFvgSizePips" in flat:
        v = float(flat["minFvgSizePips"])
        patch.setdefault("fvg", {}).update({
            "min_fvg_size_pips_m5": v,
            "min_fvg_size_pips_m15": v,
            "min_fvg_size_pips_h1": v,
        })
    if "minDisplacementAtrMultiplier" in flat:
        patch.setdefault("volatility", {})["displacement_atr_multiplier"] = float(flat["minDisplacementAtrMultiplier"])
    if "maxSpreadPips" in flat:
        v = float(flat["maxSpreadPips"])
        patch.setdefault("spread", {}).update({
            "max_spread_pips_major": v,
            "max_spread_pips_minor": v,
        })
    if "minRiskReward" in flat:
        v = float(flat["minRiskReward"])
        patch.setdefault("risk_reward", {}).update({
            "min_risk_reward_scalp": v,
            "min_risk_reward_intraday": v,
            "min_risk_reward_swing": v,
        })
    if "minConfidenceForBias" in flat:
        patch.setdefault("decision", {})["min_confidence_for_bias"] = float(flat["minConfidenceForBias"])
    if "minConfidenceForStrongBias" in flat:
        patch.setdefault("decision", {})["min_confidence_for_strong_bias"] = float(flat["minConfidenceForStrongBias"])
    if "equalHighLowTolerancePips" in flat:
        patch.setdefault("swing", {})["equal_high_low_tolerance_pips"] = float(flat["equalHighLowTolerancePips"])
    if "minScoreForBias" in flat:
        patch.setdefault("decision", {})["score_bias_minimum"] = int(flat["minScoreForBias"])
    if "minScoreForWait" in flat:
        patch.setdefault("decision", {})["score_no_trade_below"] = int(flat["minScoreForWait"])
    if "equilibriumLow" in flat:
        patch.setdefault("premium_discount", {})["equilibrium_zone_low_percent"] = int(float(flat["equilibriumLow"]) * 100)
    if "equilibriumHigh" in flat:
        patch.setdefault("premium_discount", {})["equilibrium_zone_high_percent"] = int(float(flat["equilibriumHigh"]) * 100)
    return patch


def invalidate_cache() -> None:
    _cache.clear()


def get_active_version() -> ThresholdVersion | None:
    db = SessionLocal()
    try:
        return (
            db.query(ThresholdVersion)
            .filter(ThresholdVersion.is_active.is_(True))
            .order_by(ThresholdVersion.id.desc())
            .first()
        )
    finally:
        db.close()


def _active_version_config() -> dict | None:
    version = get_active_version()
    if not version or not version.config_json:
        return None
    try:
        data = json.loads(version.config_json)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        log.warning("Invalid config_json on active threshold version %s", version.id)
        return None


def _load_override_patch(symbol: str, interval: str, trading_style: str) -> dict | None:
    sym = (symbol or "*").upper()
    iv = interval or "*"
    style = (trading_style or "*").lower()
    db = SessionLocal()
    try:
        candidates = [
            (sym, iv, style),
            (sym, iv, "*"),
            (sym, "*", style),
            (sym, "*", "*"),
            ("*", iv, style),
            ("*", "*", style),
            ("*", iv, "*"),
            ("*", "*", "*"),
        ]
        for s, i, st in candidates:
            row = (
                db.query(ThresholdOverride)
                .filter(
                    ThresholdOverride.symbol == s,
                    ThresholdOverride.interval == i,
                    ThresholdOverride.trading_style == st,
                )
                .first()
            )
            if row and row.patch_json:
                try:
                    patch = json.loads(row.patch_json)
                    if isinstance(patch, dict) and patch:
                        return patch
                except json.JSONDecodeError:
                    continue
        return None
    finally:
        db.close()


def resolve_thresholds(
    pair: str,
    timeframe: str = "60min",
    trading_style: str = "intraday",
    *,
    use_cache: bool = True,
) -> tuple[SmcIctThresholds, int | None]:
    """Return resolved thresholds and active version id (if any)."""
    try:
        version = get_active_version()
    except Exception as exc:
        log.warning("Threshold database unavailable; using built-in defaults: %s", exc)
        return _resolve_pure(pair, timeframe, trading_style), None
    version_id = version.id if version else None
    cache_key = (version_id, pair.upper(), timeframe, trading_style.lower())
    now = time.time()
    if use_cache and cache_key in _cache:
        ts, cached, vid = _cache[cache_key]
        if now - ts < _CACHE_TTL_SECONDS:
            return cached, vid

    try:
        version_config = _active_version_config()
        override = _load_override_patch(pair, timeframe, trading_style)
    except Exception as exc:
        log.warning("Threshold overrides unavailable; using built-in defaults: %s", exc)
        version_config = None
        override = None
    resolved = _resolve_pure(
        pair,
        timeframe,
        trading_style,
        version_config=version_config,
        override_patch=override,
    )
    _cache[cache_key] = (now, resolved, version_id)
    return resolved, version_id


def resolve_thresholds_model(
    pair: str,
    timeframe: str = "60min",
    trading_style: str = "intraday",
) -> SmcIctThresholds:
    thresholds, _ = resolve_thresholds(pair, timeframe, trading_style)
    return thresholds


def get_active_version_payload() -> dict:
    version = get_active_version()
    config = DEFAULT_THRESHOLDS.model_dump()
    if version and version.config_json:
        try:
            patch = json.loads(version.config_json)
            config = merge_threshold_patch(DEFAULT_THRESHOLDS, patch).model_dump()
        except (json.JSONDecodeError, ThresholdValidationError):
            pass
    return {
        "version": _serialize_version(version) if version else None,
        "config": config,
        "defaults": DEFAULT_THRESHOLDS.model_dump(),
    }


def _serialize_version(row: ThresholdVersion | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.id,
        "version_tag": row.version_tag,
        "is_active": row.is_active,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "notes": row.notes,
    }


def list_history(limit: int = 50) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(ThresholdVersion)
            .order_by(ThresholdVersion.id.desc())
            .limit(min(limit, 200))
            .all()
        )
        return [_serialize_version(r) for r in rows]
    finally:
        db.close()


def list_overrides() -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.query(ThresholdOverride).order_by(
            ThresholdOverride.symbol, ThresholdOverride.interval, ThresholdOverride.trading_style
        ).all()
        out = []
        for r in rows:
            try:
                patch = json.loads(r.patch_json) if r.patch_json else {}
            except json.JSONDecodeError:
                patch = {}
            out.append({
                "symbol": r.symbol,
                "interval": r.interval,
                "trading_style": r.trading_style,
                "patch": patch,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            })
        return out
    finally:
        db.close()


def create_version(
    config: dict,
    tag: str,
    admin_id: int | None = None,
    notes: str | None = None,
    *,
    activate: bool = False,
) -> ThresholdVersion:
    validated = validate_threshold_config(config)
    db = SessionLocal()
    try:
        existing = db.query(ThresholdVersion).filter(ThresholdVersion.version_tag == tag).first()
        if existing:
            raise ValueError(f"Version tag already exists: {tag}")
        row = ThresholdVersion(
            version_tag=tag,
            config_json=json.dumps(validated.model_dump()),
            is_active=False,
            created_by=admin_id,
            notes=notes,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        if activate:
            activate_version(row.id, admin_id)
            db.refresh(row)
        return row
    finally:
        db.close()


def activate_version(version_id: int, admin_id: int | None = None) -> ThresholdVersion:
    db = SessionLocal()
    try:
        row = db.query(ThresholdVersion).filter(ThresholdVersion.id == version_id).first()
        if not row:
            raise ValueError("Threshold version not found")
        db.query(ThresholdVersion).filter(ThresholdVersion.is_active.is_(True)).update({"is_active": False})
        row.is_active = True
        db.commit()
        db.refresh(row)
        invalidate_cache()
        return row
    finally:
        db.close()


def patch_active_version(patch: dict, admin_id: int | None = None, notes: str | None = None) -> ThresholdVersion:
    active = get_active_version()
    base_config = DEFAULT_THRESHOLDS.model_dump()
    if active and active.config_json:
        try:
            base_config = merge_threshold_patch(
                DEFAULT_THRESHOLDS,
                json.loads(active.config_json),
            ).model_dump()
        except json.JSONDecodeError:
            pass
    merged = merge_threshold_patch(validate_threshold_config(base_config), patch)
    tag = f"v-{uuid.uuid4().hex[:12]}"
    return create_version(merged.model_dump(), tag, admin_id, notes or "Patched from active version", activate=True)


def save_override(
    symbol: str,
    interval: str,
    trading_style: str,
    patch: dict,
    admin_id: int | None = None,
) -> dict:
    validate_threshold_config(merge_threshold_patch(DEFAULT_THRESHOLDS, patch))
    sym = (symbol or "*").upper()
    iv = interval or "*"
    style = (trading_style or "*").lower()
    db = SessionLocal()
    try:
        row = (
            db.query(ThresholdOverride)
            .filter(
                ThresholdOverride.symbol == sym,
                ThresholdOverride.interval == iv,
                ThresholdOverride.trading_style == style,
            )
            .first()
        )
        if row:
            row.patch_json = json.dumps(patch)
        else:
            row = ThresholdOverride(
                symbol=sym,
                interval=iv,
                trading_style=style,
                patch_json=json.dumps(patch),
            )
            db.add(row)
        db.commit()
        invalidate_cache()
        return {"symbol": sym, "interval": iv, "trading_style": style, "patch": patch}
    finally:
        db.close()


def migrate_pair_thresholds_to_overrides() -> int:
    """One-time migration from legacy pair_thresholds rows."""
    db = SessionLocal()
    count = 0
    try:
        rows = db.query(PairThreshold).all()
        for r in rows:
            try:
                flat = json.loads(r.thresholds_json) if r.thresholds_json else {}
            except json.JSONDecodeError:
                continue
            if not flat:
                continue
            patch = _flat_to_nested_patch(flat)
            if not patch:
                continue
            sym = r.symbol.upper()
            iv = r.interval or "*"
            existing = (
                db.query(ThresholdOverride)
                .filter(ThresholdOverride.symbol == sym, ThresholdOverride.interval == iv, ThresholdOverride.trading_style == "*")
                .first()
            )
            if existing:
                existing.patch_json = json.dumps(patch)
            else:
                db.add(ThresholdOverride(symbol=sym, interval=iv, trading_style="*", patch_json=json.dumps(patch)))
            count += 1
        db.commit()
        return count
    finally:
        db.close()


def seed_initial_version() -> ThresholdVersion | None:
    """Create active v1 from defaults if no versions exist."""
    db = SessionLocal()
    try:
        if db.query(ThresholdVersion).count() > 0:
            return get_active_version()
        config = DEFAULT_THRESHOLDS.model_dump()
        row = ThresholdVersion(
            version_tag="v1.0.0",
            config_json=json.dumps(config),
            is_active=True,
            notes="Initial defaults seeded at startup",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        migrate_pair_thresholds_to_overrides()
        invalidate_cache()
        log.info("Seeded threshold version v1.0.0 (id=%s)", row.id)
        return row
    except Exception as exc:
        log.debug("Threshold seed skipped: %s", exc)
        db.rollback()
        return None
    finally:
        db.close()
