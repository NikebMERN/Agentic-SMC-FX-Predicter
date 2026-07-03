# utils/settings.py
"""Admin-editable runtime settings, stored in the `settings` table.

These override env defaults so the admin panel can reconfigure the
platform without touching the server. Every read fails soft: if the
database is unreachable, the env/default value is used and the platform
keeps running.

Known keys:
    supported_pairs        comma-separated extra pairs merged into the full FX catalog
    min_final_confidence   blended confidence floor for a trade (0..1)
    broadcast_signals      when true, push new signals to linked Telegram users (quota applies)
"""
import time

from utils import config
from utils.logger import get_logger

log = get_logger("settings")

_CACHE_TTL_SECONDS = 30
_cache: dict[str, tuple[float, str]] = {}


def _read_db(key: str) -> str | None:
    from db.models import Setting
    from db.session import SessionLocal
    db = SessionLocal()
    try:
        row = db.query(Setting).filter(Setting.key == key).first()
        return row.value if row else None
    finally:
        db.close()


def get(key: str, default: str | None = None) -> str | None:
    """Setting value with a short cache; env/default when DB is down."""
    now = time.time()
    cached = _cache.get(key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1] if cached[1] is not None else default
    try:
        value = _read_db(key)
    except Exception:
        return default
    _cache[key] = (now, value)
    return value if value is not None else default


def set(key: str, value: str) -> None:
    """Upsert a setting (raises when the DB is unavailable — the admin
    must know their change did not persist)."""
    from db.models import Setting
    from db.session import SessionLocal
    db = SessionLocal()
    try:
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value))
        db.commit()
        _cache[key] = (time.time(), value)
        log.info("Setting %s = %s", key, value)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def all_settings() -> dict:
    from db.models import Setting
    from db.session import SessionLocal
    db = SessionLocal()
    try:
        return {row.key: row.value for row in db.query(Setting).all()}
    except Exception:
        return {}
    finally:
        db.close()


# ---- typed helpers ---------------------------------------------------
def get_float(key: str, default: float) -> float:
    raw = get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("Setting %s has non-numeric value %r — using default", key, raw)
        return default


def get_supported_pairs() -> list[str]:
    from engine.data import DATA_DIR, INTERVAL
    from utils.pairs import DEFAULT_FX_PAIRS, merge_pairs, pairs_from_data_dir

    # Full catalog is always available in menus (web, admin, Telegram).
    # Use disabled_pairs in admin settings to block specific symbols.
    base = list(DEFAULT_FX_PAIRS)
    raw = get("supported_pairs")
    if raw:
        extra = [p.strip().upper() for p in raw.split(",") if p.strip()]
        if extra:
            return merge_pairs(base, extra)
    return merge_pairs(base, config.SUPPORTED_PAIRS, pairs_from_data_dir(DATA_DIR, INTERVAL))


def get_broadcast_signals() -> bool:
    raw = get("broadcast_signals", "false")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}
