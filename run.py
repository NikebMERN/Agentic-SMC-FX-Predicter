# run.py
"""SmartFlow AI - single entry point.

    python run.py                    Run EVERYTHING (build admin UI + API + bot + monitors)
    python run.py dev                Same + Vite admin dev server on :5174 (hot reload)
    python run.py build-admin        Build React admin panel only
    python run.py predict EURUSD     One-off prediction in the terminal
    python run.py api                API server only
    python run.py bot                Telegram bot only
    python run.py refresh            Refresh CSVs + models for all supported pairs

On Windows you can also double-click start.bat or run:  start.bat

The API is served with waitress (production WSGI). The Telegram bot, user web app
(Vite :5173), and admin UI run concurrently — one command starts everything.
"""
import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

from utils.config import API_HOST, API_PORT
from utils.error_tracking import init_error_tracking
from utils.logger import get_logger

log = get_logger("run")
init_error_tracking()

_child_processes: list[subprocess.Popen] = []
_shutdown_event = threading.Event()


def _handle_shutdown(signum, _frame) -> None:
    log.info("Received signal %s; beginning graceful shutdown", signum)
    _shutdown_event.set()


def install_signal_handlers() -> None:
    if threading.current_thread() is not threading.main_thread():
        return
    for signame in ("SIGTERM", "SIGINT"):
        signum = getattr(signal, signame, None)
        if signum is not None:
            signal.signal(signum, _handle_shutdown)


def _stop_monitors() -> None:
    try:
        from services.outcome_monitor import stop_outcome_monitor
        stop_outcome_monitor()
    except Exception:
        log.exception("Outcome monitor shutdown failed")
    try:
        from services.health_monitor import stop_health_monitor
        stop_health_monitor()
    except Exception:
        log.exception("Health monitor shutdown failed")
    try:
        from db.session import engine
        engine.dispose()
    except Exception:
        log.exception("Database pool shutdown failed")


def _database_startup_hint(exc: Exception) -> str:
    message = str(exc)
    dns_markers = (
        "Name or service not known",
        "Temporary failure in name resolution",
        "[Errno -2]",
        "nodename nor servname provided",
    )
    if not any(marker in message for marker in dns_markers):
        return ""
    try:
        from utils.config import DATABASE_URL
        host = urlsplit(DATABASE_URL).hostname or "configured database host"
    except Exception:
        host = "configured database host"
    return (
        f" Database hostname '{host}' does not resolve. Copy the exact MySQL "
        "Service URI/Host from Aiven Quick Connect, confirm the Aiven service "
        "is Running, then update Render DATABASE_URL."
    )


def _stop_child_processes() -> None:
    for proc in _child_processes:
        if proc.poll() is not None:
            continue
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    _child_processes.clear()


def _track_process(proc: subprocess.Popen | None) -> subprocess.Popen | None:
    if proc is not None:
        _child_processes.append(proc)
    return proc


def _migrate_schema(engine):
    """Add columns/tables introduced after the original schema."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    column_migrations = {
        "users": {
            "role": "ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'user'",
            "status": "ALTER TABLE users ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'pending'",
            "is_active": "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 0",
            "must_change_password": "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0",
            "signals_remaining": "ALTER TABLE users ADD COLUMN signals_remaining INTEGER NOT NULL DEFAULT 0",
            "risk_disclosure_accepted_at": "ALTER TABLE users ADD COLUMN risk_disclosure_accepted_at DATETIME",
        },
        "signals": {
            "stop_loss": "ALTER TABLE signals ADD COLUMN stop_loss FLOAT",
            "take_profit": "ALTER TABLE signals ADD COLUMN take_profit FLOAT",
            "status": "ALTER TABLE signals ADD COLUMN status VARCHAR(16) DEFAULT 'OPEN'",
            "outcome": "ALTER TABLE signals ADD COLUMN outcome VARCHAR(16)",
            "closed_at": "ALTER TABLE signals ADD COLUMN closed_at DATETIME",
        },
        "prediction_reviews": {
            "horizon": "ALTER TABLE prediction_reviews ADD COLUMN horizon VARCHAR(16) DEFAULT 'intraday'",
            "direction": "ALTER TABLE prediction_reviews ADD COLUMN direction VARCHAR(16)",
            "invalidation_price": "ALTER TABLE prediction_reviews ADD COLUMN invalidation_price FLOAT",
            "target_price": "ALTER TABLE prediction_reviews ADD COLUMN target_price FLOAT",
            "scores_json": "ALTER TABLE prediction_reviews ADD COLUMN scores_json TEXT",
            "signals_json": "ALTER TABLE prediction_reviews ADD COLUMN signals_json TEXT",
            "snapshot_path": "ALTER TABLE prediction_reviews ADD COLUMN snapshot_path VARCHAR(512)",
            "model_version": "ALTER TABLE prediction_reviews ADD COLUMN model_version VARCHAR(64)",
            "strategy_mode": "ALTER TABLE prediction_reviews ADD COLUMN strategy_mode VARCHAR(16) DEFAULT 'both'",
            "retry_count": "ALTER TABLE prediction_reviews ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
            "feedback_due_at": "ALTER TABLE prediction_reviews ADD COLUMN feedback_due_at DATETIME",
            "feedback_reminder_sent": "ALTER TABLE prediction_reviews ADD COLUMN feedback_reminder_sent BOOLEAN NOT NULL DEFAULT 0",
            "threshold_version_id": "ALTER TABLE prediction_reviews ADD COLUMN threshold_version_id INTEGER",
            "model_version_id": "ALTER TABLE prediction_reviews ADD COLUMN model_version_id INTEGER",
            "rule_engine_version": "ALTER TABLE prediction_reviews ADD COLUMN rule_engine_version VARCHAR(32) DEFAULT 'v1'",
            "feature_schema_version": "ALTER TABLE prediction_reviews ADD COLUMN feature_schema_version VARCHAR(16) DEFAULT 'v1'",
            "meta_ml_probability": "ALTER TABLE prediction_reviews ADD COLUMN meta_ml_probability FLOAT",
            "confidence_before_ml": "ALTER TABLE prediction_reviews ADD COLUMN confidence_before_ml FLOAT",
            "final_confidence": "ALTER TABLE prediction_reviews ADD COLUMN final_confidence FLOAT",
            "trading_style": "ALTER TABLE prediction_reviews ADD COLUMN trading_style VARCHAR(16) DEFAULT 'intraday'",
            "risk_reward_planned": "ALTER TABLE prediction_reviews ADD COLUMN risk_reward_planned FLOAT",
            "risk_reward_achieved": "ALTER TABLE prediction_reviews ADD COLUMN risk_reward_achieved FLOAT",
            "account_type": "ALTER TABLE prediction_reviews ADD COLUMN account_type VARCHAR(32)",
            "volatility": "ALTER TABLE prediction_reviews ADD COLUMN volatility FLOAT",
            "spread": "ALTER TABLE prediction_reviews ADD COLUMN spread FLOAT",
            "execution_delay_ms": "ALTER TABLE prediction_reviews ADD COLUMN execution_delay_ms INTEGER",
            "manual_notes": "ALTER TABLE prediction_reviews ADD COLUMN manual_notes TEXT",
        },
        "model_versions": {
            "display_name": "ALTER TABLE model_versions ADD COLUMN display_name VARCHAR(64)",
            "trading_style": "ALTER TABLE model_versions ADD COLUMN trading_style VARCHAR(16) NOT NULL DEFAULT 'intraday'",
            "model_type": "ALTER TABLE model_versions ADD COLUMN model_type VARCHAR(16) NOT NULL DEFAULT 'RANDOM_FOREST'",
            "calibrator_path": "ALTER TABLE model_versions ADD COLUMN calibrator_path VARCHAR(512)",
            "feature_schema_version": "ALTER TABLE model_versions ADD COLUMN feature_schema_version VARCHAR(16) DEFAULT 'v1'",
            "threshold_version_id": "ALTER TABLE model_versions ADD COLUMN threshold_version_id INTEGER",
            "rule_engine_version": "ALTER TABLE model_versions ADD COLUMN rule_engine_version VARCHAR(32) DEFAULT 'v1'",
            "training_data_start": "ALTER TABLE model_versions ADD COLUMN training_data_start DATETIME",
            "training_data_end": "ALTER TABLE model_versions ADD COLUMN training_data_end DATETIME",
            "training_record_count": "ALTER TABLE model_versions ADD COLUMN training_record_count INTEGER NOT NULL DEFAULT 0",
            "walk_forward_score": "ALTER TABLE model_versions ADD COLUMN walk_forward_score FLOAT",
            "precision": "ALTER TABLE model_versions ADD COLUMN `precision` FLOAT",
            "recall": "ALTER TABLE model_versions ADD COLUMN recall FLOAT",
            "f1": "ALTER TABLE model_versions ADD COLUMN f1 FLOAT",
            "brier_score": "ALTER TABLE model_versions ADD COLUMN brier_score FLOAT",
            "log_loss": "ALTER TABLE model_versions ADD COLUMN log_loss FLOAT",
            "win_rate": "ALTER TABLE model_versions ADD COLUMN win_rate FLOAT",
            "accepted_signal_count": "ALTER TABLE model_versions ADD COLUMN accepted_signal_count INTEGER NOT NULL DEFAULT 0",
            "rejected_signal_count": "ALTER TABLE model_versions ADD COLUMN rejected_signal_count INTEGER NOT NULL DEFAULT 0",
            "status": "ALTER TABLE model_versions ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'CANDIDATE'",
            "promoted_from_version_id": "ALTER TABLE model_versions ADD COLUMN promoted_from_version_id INTEGER",
            "promoted_at": "ALTER TABLE model_versions ADD COLUMN promoted_at DATETIME",
            "created_at": "ALTER TABLE model_versions ADD COLUMN created_at DATETIME",
        },
        "user_feedback": {
            "trade_entry": "ALTER TABLE user_feedback ADD COLUMN trade_entry VARCHAR(16)",
            "screenshot_path": "ALTER TABLE user_feedback ADD COLUMN screenshot_path VARCHAR(512)",
            "account_type": "ALTER TABLE user_feedback ADD COLUMN account_type VARCHAR(32)",
            "execution_delay_ms": "ALTER TABLE user_feedback ADD COLUMN execution_delay_ms INTEGER",
            "manual_notes": "ALTER TABLE user_feedback ADD COLUMN manual_notes TEXT",
            "payload_hash": "ALTER TABLE user_feedback ADD COLUMN payload_hash VARCHAR(64)",
        },
        "training_records": {
            "dataset_tier": "ALTER TABLE training_records ADD COLUMN dataset_tier VARCHAR(24) NOT NULL DEFAULT 'PENDING_REVIEW'",
            "validation_score": "ALTER TABLE training_records ADD COLUMN validation_score FLOAT",
            "validation_reasons_json": "ALTER TABLE training_records ADD COLUMN validation_reasons_json TEXT",
            "duplicate_of_id": "ALTER TABLE training_records ADD COLUMN duplicate_of_id INTEGER",
            "suspicious": "ALTER TABLE training_records ADD COLUMN suspicious BOOLEAN NOT NULL DEFAULT 0",
            "institutional_example": "ALTER TABLE training_records ADD COLUMN institutional_example BOOLEAN NOT NULL DEFAULT 0",
        },
    }
    with engine.begin() as conn:
        for table, cols in column_migrations.items():
            if table not in tables:
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for column, statement in cols.items():
                if column not in existing:
                    conn.execute(text(statement))
                    log.info("Migrated %s: added %s", table, column)

        # Backfill: existing active users without status → active
        if "users" in tables:
            existing = {c["name"] for c in inspector.get_columns("users")}
            if "status" in existing:
                conn.execute(text(
                    "UPDATE users SET status='active', is_active=1 "
                    "WHERE role='admin' AND (status IS NULL OR status='pending')"
                ))
                conn.execute(text(
                    "UPDATE users SET status='active', is_active=1 "
                    "WHERE is_active=1 AND status='pending'"
                ))

        if "model_versions" in tables:
            existing = {c["name"] for c in inspector.get_columns("model_versions")}
            if "status" in existing:
                conn.execute(text(
                    "UPDATE model_versions SET status='ACTIVE' WHERE is_active=1 "
                    "AND (status IS NULL OR status='CANDIDATE')"
                ))
                conn.execute(text(
                    "UPDATE model_versions SET status='ARCHIVED' WHERE is_active=0 "
                    "AND (status IS NULL OR status='CANDIDATE')"
                ))

        if "user_feedback" in tables:
            uf_cols = {c["name"] for c in inspector.get_columns("user_feedback")}
            if "trade_entry" in uf_cols:
                conn.execute(text(
                    "UPDATE user_feedback SET trade_entry = feedback, feedback = NULL "
                    "WHERE trade_entry IS NULL AND feedback IN ('ENTERED', 'DID_NOT_TAKE')"
                ))

    # Create any new ML platform tables missing from older deployments.
    from db.session import Base
    import db.models  # noqa: F401
    Base.metadata.create_all(bind=engine)


def _run_alembic():
    try:
        from alembic.config import Config
        from alembic import command
        ini = os.path.join(os.path.dirname(__file__), "alembic.ini")
        if os.path.exists(ini):
            cfg = Config(ini)
            command.upgrade(cfg, "head")
            log.info("Alembic migrations applied.")
    except Exception as exc:
        log.warning("Alembic upgrade skipped or failed: %s", exc)


def _stamp_alembic_head_if_unversioned(engine) -> None:
    """Mark the verified create_all/compatibility schema at the current revision."""
    try:
        from alembic.config import Config
        from alembic import command
        ini = os.path.join(os.path.dirname(__file__), "alembic.ini")
        if not os.path.exists(ini):
            return
        cfg = Config(ini)
        command.stamp(cfg, "head")
        log.info("Verified compatibility schema stamped at Alembic head.")
    except Exception as exc:
        log.warning("Alembic stamp skipped or failed: %s", exc)


def _verify_schema(engine) -> None:
    """Fail if the database is missing ORM tables or columns after startup sync."""
    from sqlalchemy import inspect
    from db.session import Base
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    problems: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            problems.append(f"missing table {table.name}")
            continue
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in existing_columns:
                problems.append(f"missing column {table.name}.{column.name}")
    if problems:
        preview = "; ".join(problems[:12])
        extra = "" if len(problems) <= 12 else f"; +{len(problems) - 12} more"
        raise RuntimeError(f"Database schema verification failed: {preview}{extra}")


def _bootstrap_admin():
    """Create (or promote) the admin account from ADMIN_EMAIL/ADMIN_PASSWORD."""
    from utils.config import ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_USERNAME
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        log.info("ADMIN_EMAIL/ADMIN_PASSWORD not set — skipping admin bootstrap.")
        return
    from db.models import User
    from db.session import SessionLocal
    from utils.security import hash_password, is_weak_password
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        weak = is_weak_password(ADMIN_PASSWORD)
        if user:
            changed = False
            if user.role != "admin":
                user.role = "admin"
                changed = True
            if getattr(user, "status", None) != "active":
                user.status = "active"
                changed = True
            if not getattr(user, "is_active", True):
                user.is_active = True
                changed = True
            # Never re-force password change on startup (env password may stay weak).
            if user.must_change_password:
                user.must_change_password = False
                changed = True
            if changed:
                db.commit()
                log.info("Promoted/updated admin %s.", ADMIN_EMAIL)
        else:
            db.add(User(
                username=ADMIN_USERNAME,
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                role="admin",
                status="active",
                is_active=True,
                must_change_password=False,
                signals_remaining=1000,
            ))
            db.commit()
            log.info("Created admin account %s.", ADMIN_EMAIL)
        if weak:
            log.warning(
                "Admin bootstrap password is weak — consider changing it in the admin panel."
            )
    finally:
        db.close()


_OLD_MAJOR_SEVEN = {
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
}


def _seed_default_settings() -> None:
    """Persist the full FX pair catalog; upgrade legacy short lists on startup."""
    from db.models import Setting
    from db.session import SessionLocal
    from utils.pairs import DEFAULT_FX_PAIRS, catalog_version, merge_pairs

    canonical = ",".join(DEFAULT_FX_PAIRS)
    db = SessionLocal()
    try:
        row = db.query(Setting).filter(Setting.key == "supported_pairs").first()
        ver = db.query(Setting).filter(Setting.key == "pairs_catalog_version").first()

        if not row:
            db.add(Setting(key="supported_pairs", value=canonical))
            db.add(Setting(key="pairs_catalog_version", value=catalog_version()))
            db.commit()
            log.info("Seeded supported_pairs (%d pairs).", len(DEFAULT_FX_PAIRS))
            return

        current_list = [p.strip().upper() for p in row.value.split(",") if p.strip()]
        current = set(current_list)

        if current == _OLD_MAJOR_SEVEN:
            row.value = canonical
            if ver:
                ver.value = catalog_version()
            else:
                db.add(Setting(key="pairs_catalog_version", value=catalog_version()))
            db.commit()
            log.info("Upgraded legacy major-seven supported_pairs to full catalog.")
            return

        if not ver or ver.value != catalog_version():
            merged = merge_pairs(current_list, DEFAULT_FX_PAIRS)
            row.value = ",".join(merged)
            if ver:
                ver.value = catalog_version()
            else:
                db.add(Setting(key="pairs_catalog_version", value=catalog_version()))
            db.commit()
            log.info(
                "Merged catalog %s into supported_pairs (%d stored).",
                catalog_version(),
                len(merged),
            )
    except Exception as exc:
        log.debug("Settings seed skipped: %s", exc)
        db.rollback()
    finally:
        db.close()


def _seed_ml_settings() -> None:
    """Default ML platform settings."""
    from db.models import Setting
    from db.session import SessionLocal
    import json
    from ml.promotion_gate import DEFAULT_GATE

    defaults = {
        "ml_mode": "active",
        "model_promotion_enabled": "false",
        "ml_blend_rule_weight": "0.55",
        "ml_blend_ml_weight": "0.45",
        "ml_downgrade_no_trade_below": "0.50",
        "ml_downgrade_wait_below": "0.60",
        "ml_confidence_cap": "0.85",
        "promotion_gate_json": json.dumps(DEFAULT_GATE),
        "walk_forward_train_days": "45",
        "walk_forward_test_days": "7",
        "walk_forward_step_days": "7",
    }
    db = SessionLocal()
    try:
        for key, value in defaults.items():
            if not db.query(Setting).filter(Setting.key == key).first():
                db.add(Setting(key=key, value=value))
        db.commit()
    except Exception as exc:
        log.debug("ML settings seed skipped: %s", exc)
        db.rollback()
    finally:
        db.close()


def _seed_threshold_versions() -> None:
    try:
        from services.threshold_service import seed_initial_version
        seed_initial_version()
    except Exception as exc:
        log.debug("Threshold version seed skipped: %s", exc)


def init_database() -> bool:
    """Create tables if the database is reachable. Non-fatal on failure -
    prediction endpoints work without MySQL."""
    try:
        from utils.config import APP_ENV
        from db.session import Base, engine
        import db.models  # noqa: F401  (registers the models)
        Base.metadata.create_all(bind=engine)
        _migrate_schema(engine)
        _stamp_alembic_head_if_unversioned(engine)
        _run_alembic()
        _verify_schema(engine)
        _bootstrap_admin()
        _seed_default_settings()
        _seed_threshold_versions()
        _seed_ml_settings()
        log.info("Database tables ready.")
        return True
    except Exception as exc:
        if APP_ENV == "production":
            hint = _database_startup_hint(exc)
            raise RuntimeError(
                f"Database initialization failed in production: {exc}{hint}"
            ) from exc
        log.warning("Database unavailable (%s) - auth/trade routes will fail until it is up.", exc)
        return False


def production_config_issues(role: str | None = None) -> list[str]:
    """Return production misconfiguration issues that must be fixed before boot."""
    from utils.config import (
        ALLOW_CACHE_ONLY_PRODUCTION,
        ALPHA_VANTAGE_API_KEY,
        ADMIN_PASSWORD,
        APP_ENV,
        CORS_ORIGINS,
        DATA_PROVIDER,
        DATABASE_URL,
        OANDA_API_KEY,
        RATELIMIT_STORAGE_URI,
    )
    from utils.mailer import is_configured
    from utils.security import SECRET_KEY, is_weak_password

    if APP_ENV != "production":
        return []

    role = (role or os.getenv("SERVICE_ROLE") or "all").lower()
    validate_api = role in {"all", "api", "web"}
    validate_market_data = role in {"all", "ai-worker", "worker", "scheduler"}
    issues: list[str] = []
    if not SECRET_KEY or SECRET_KEY == "change-me":
        issues.append("SECRET_KEY is missing or unsafe.")
    if validate_api and CORS_ORIGINS == ["*"]:
        issues.append("CORS_ORIGINS is set to '*' - restrict to your domain in production.")
    if validate_api and not is_configured():
        issues.append("SMTP is not configured - password reset emails will fail.")
    if DATABASE_URL and DATABASE_URL.startswith("sqlite"):
        issues.append("DATABASE_URL uses SQLite - use MySQL for production.")
    if validate_api and (not ADMIN_PASSWORD or is_weak_password(ADMIN_PASSWORD)):
        issues.append("ADMIN_PASSWORD is missing or weak - set a strong bootstrap password.")
    if validate_api and RATELIMIT_STORAGE_URI == "memory://":
        issues.append("RATELIMIT_STORAGE_URI uses memory:// - use Redis in production.")
    provider = (DATA_PROVIDER or "auto").lower()
    if validate_market_data and provider == "oanda" and not OANDA_API_KEY:
        issues.append("DATA_PROVIDER=oanda but OANDA_API_KEY is missing.")
    if validate_market_data and provider == "alphavantage" and not ALPHA_VANTAGE_API_KEY:
        issues.append("DATA_PROVIDER=alphavantage but ALPHA_VANTAGE_API_KEY is missing.")
    if validate_market_data and provider == "auto" and not (
        OANDA_API_KEY or ALPHA_VANTAGE_API_KEY or ALLOW_CACHE_ONLY_PRODUCTION
    ):
        issues.append(
            "No live data provider key is configured - set OANDA_API_KEY or "
            "ALPHA_VANTAGE_API_KEY, or explicitly set ALLOW_CACHE_ONLY_PRODUCTION=true."
        )
    return issues


def log_production_warnings() -> None:
    """Log a single banner of production misconfiguration."""
    issues = production_config_issues()
    if not issues:
        return

    log.warning(
        "Production configuration warnings:\n%s",
        "\n".join(f"  • {item}" for item in issues),
    )


def assert_production_ready(role: str | None = None) -> None:
    issues = production_config_issues(role)
    if not issues:
        return
    raise RuntimeError(
        "Unsafe production configuration:\n"
        + "\n".join(f"  - {item}" for item in issues)
    )


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    import socket
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(1.0)
        return probe.connect_ex((host, port)) == 0
    finally:
        probe.close()


def _pids_listening_on_port(port: int) -> list[int]:
    """Return PIDs with a listener on *port* (best effort, Windows + Unix)."""
    pids: list[int] = []
    try:
        if os.name == "nt":
            out = subprocess.check_output(
                ["netstat", "-ano"],
                text=True,
                errors="replace",
            )
            token = f":{port}"
            for line in out.splitlines():
                if "LISTENING" not in line.upper() or token not in line:
                    continue
                parts = line.split()
                if parts and parts[-1].isdigit():
                    pids.append(int(parts[-1]))
        else:
            out = subprocess.check_output(
                ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                text=True,
                errors="replace",
            )
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))
    except (FileNotFoundError, subprocess.CalledProcessError, OSError):
        pass
    return list(dict.fromkeys(pids))


def _kill_pid(pid: int) -> None:
    if pid in (0, os.getpid()):
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                check=False,
                capture_output=True,
            )
        else:
            import signal
            os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def _release_ports(ports: list[int]) -> list[int]:
    """Stop stale listeners from a prior run. Returns ports still blocked."""
    blocked = [p for p in ports if _port_in_use(p)]
    if not blocked:
        return []
    log.warning(
        "Port(s) %s still in use — stopping leftover process(es) from a previous run.",
        blocked,
    )
    skip = {os.getpid()}
    for port in blocked:
        for pid in _pids_listening_on_port(port):
            if pid in skip:
                continue
            log.info("Releasing port %s (PID %s)", port, pid)
            _kill_pid(pid)
    time.sleep(0.6)
    return [p for p in blocked if _port_in_use(p)]


def _assert_port_free():
    """Fail fast if another instance already serves the API port."""
    if _port_in_use(API_PORT):
        raise RuntimeError(
            f"Port {API_PORT} is already in use. Stop the other SmartFlow instance "
            f"or change API_PORT in .env."
        )


def serve_api():
    log_production_warnings()
    try:
        assert_production_ready()
    except RuntimeError as exc:
        log.error("%s", exc)
        raise
    try:
        _assert_port_free()
    except RuntimeError as exc:
        log.error("%s", exc)
        return
    from app import app
    try:
        from waitress import serve
        log.info("API listening on http://127.0.0.1:%s (waitress)", API_PORT)
        serve(app, host=API_HOST, port=API_PORT, threads=8)
    except ImportError:
        log.warning("waitress not installed - falling back to the Flask dev server.")
        app.run(host=API_HOST, port=API_PORT, debug=False, use_reloader=False, threaded=True)
    except OSError as exc:
        log.error("API failed to bind port %s: %s", API_PORT, exc)
    except Exception:
        log.exception("API server crashed")


def _start_api_thread() -> threading.Thread:
    thread = threading.Thread(target=serve_api, name="api-server", daemon=True)
    thread.start()
    return thread


def _prepare_platform_ports(dev_mode: bool) -> None:
    """Free API + Vite ports left over when a prior run was interrupted."""
    ports = [API_PORT]
    if dev_mode:
        ports.extend([5173, 5174])
    still_blocked = _release_ports(ports)
    if still_blocked:
        raise SystemExit(
            "Could not start — port(s) still in use after cleanup: "
            f"{still_blocked}. Close other apps using those ports and retry."
        )


def _start_frontend_processes(dev_mode: bool) -> None:
    """Launch Vite dev servers in development; production serves built static files."""
    if not dev_mode:
        from utils.config import API_PORT
        log.info("User app (built)  → http://127.0.0.1:%s/app/", API_PORT)
        log.info("Admin panel (built) → http://127.0.0.1:%s/admin/", API_PORT)
        return

    from scripts.frontend import start_admin_dev_server, start_smc_dev_server

    def _launch(name: str, starter, url: str) -> None:
        def _run():
            proc = _track_process(starter())
            if proc:
                log.info("%s → %s", name, url)
            else:
                log.warning("%s not started (Node.js/npm missing?)", name)

        threading.Thread(target=_run, name=f"start-{name}", daemon=True).start()

    _launch("User web app (Vite)", start_smc_dev_server, "http://127.0.0.1:5173/")
    _launch("Admin dev UI (Vite)", start_admin_dev_server, "http://127.0.0.1:5174/admin/")


def _wait_for_platform(api_thread: threading.Thread, dev_mode: bool) -> None:
    """Keep the process alive while API, bot, and optional Vite servers run."""
    time.sleep(0.8)
    if dev_mode:
        log.info(
            "All services running — API :%s | User :5173 | Admin :5174/admin/ | Ctrl+C stops everything",
            API_PORT,
        )
    else:
        log.info(
            "Production stack running — API + built SPAs on :%s | Ctrl+C stops everything",
            API_PORT,
        )
    try:
        while True:
            if not api_thread.is_alive():
                log.error(
                    "API server stopped unexpectedly — check logs above for port %s errors.",
                    API_PORT,
                )
                break
            for proc in list(_child_processes):
                code = proc.poll()
                if code is not None:
                    log.warning("Frontend dev server exited (code %s).", code)
                    _child_processes.remove(proc)
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down all services…")
    finally:
        _stop_child_processes()


def start_background_services():
    """Start outcome monitor, health monitor, scheduler, and Telegram bot."""
    from services.outcome_monitor import start_outcome_monitor
    from services.health_monitor import start_health_monitor
    start_outcome_monitor()
    start_health_monitor()
    start_scheduler()
    start_bot_thread()


def start_scheduler():
    """APScheduler: nightly retrain + alert scanner."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        import os

        cron = os.getenv("NIGHTLY_RETRAIN_CRON", "0 2 * * *")
        tz = os.getenv("NIGHTLY_RETRAIN_TZ", "America/New_York")
        parts = cron.split()
        if len(parts) == 5:
            minute, hour, day, month, dow = parts
            trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow, timezone=tz)
        else:
            trigger = CronTrigger(hour=2, minute=0, timezone=tz)

        sched = BackgroundScheduler(
            timezone=tz,
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 900},
        )

        def _nightly():
            from services.nightly_retrain import run_retrain
            run_retrain(run_type="NIGHTLY")

        def _alerts():
            from services.alert_scanner import run_alert_scan
            run_alert_scan()

        sched.add_job(_nightly, trigger, id="nightly_retrain", replace_existing=True)
        sched.add_job(_alerts, "interval", minutes=15, id="alert_scanner", replace_existing=True)
        sched.start()
        log.info("APScheduler started (nightly retrain + 15m alert scan)")
        return sched
    except Exception as exc:
        log.warning("Scheduler not started: %s", exc)
        return None


def _bot_supervisor():
    """Run Telegram polling in a loop; auto-restart if polling stops or crashes."""
    from utils.config import TELEGRAM_BOT_TOKEN
    from utils.telegram_http import bot_enabled, is_telegram_network_error, telegram_api_status
    import time
    from bot import run_bot

    if not TELEGRAM_BOT_TOKEN:
        log.warning(
            "TELEGRAM_BOT_TOKEN not set — web/API will run without the Telegram bot. "
            "Add the token to .env and restart."
        )
        return

    if not bot_enabled():
        log.info("Telegram bot disabled (TELEGRAM_BOT_ENABLED=false). Web/API only.")
        return

    backoff = 30
    while True:
        ok, detail = telegram_api_status()
        if not ok:
            log.warning(
                "Telegram API unreachable — will retry in %ss "
                "(set TELEGRAM_PROXY_URL or TELEGRAM_BOT_ENABLED=false)",
                backoff,
            )
            log.warning("Telegram API status detail: %s", detail)
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
            continue

        backoff = 30
        try:
            if run_bot(in_thread=True):
                log.warning(
                    "Telegram bot polling stopped — restarting in %ss (web/API keeps running)",
                    backoff,
                )
        except Exception as exc:
            if is_telegram_network_error(exc):
                log.warning(
                    "Telegram bot network error — retrying in %ss: %s",
                    backoff,
                    exc,
                )
            else:
                log.exception(
                    "Telegram bot error — restarting in %ss (web/API keeps running)",
                    backoff,
                )
        time.sleep(backoff)
        backoff = min(backoff * 2, 300)


def start_bot_thread() -> threading.Thread | None:
    from utils.config import TELEGRAM_BOT_TOKEN
    from utils.telegram_http import bot_enabled
    if not TELEGRAM_BOT_TOKEN or not bot_enabled():
        if TELEGRAM_BOT_TOKEN and not bot_enabled():
            log.info("Telegram bot supervisor skipped (TELEGRAM_BOT_ENABLED=false).")
        return None
    # Daemon thread: exits with the process on Ctrl+C; supervisor restarts polling after errors.
    thread = threading.Thread(target=_bot_supervisor, daemon=True, name="telegram-bot")
    thread.start()
    log.info("Telegram bot supervisor started (runs in parallel with the web API).")
    return thread


def _background_services_enabled_by_default() -> bool:
    from utils.config import APP_ENV
    raw = os.getenv("BACKGROUND_SERVICES_ENABLED")
    if raw is None:
        return APP_ENV == "production"
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def cmd_worker() -> None:
    """Run schedulers, monitors, and Telegram bot without serving HTTP."""
    assert_production_ready()
    init_database()
    install_signal_handlers()
    start_background_services()
    log.info("Background worker running - monitors, scheduler, and Telegram supervisor active.")
    try:
        while not _shutdown_event.wait(5):
            pass
    except KeyboardInterrupt:
        _shutdown_event.set()
    finally:
        _stop_monitors()
        log.info("Worker shut down cleanly.")


def cmd_ai_worker() -> None:
    """Run continuous monitors, queued delivery, and Telegram without cron jobs."""
    assert_production_ready("ai-worker")
    init_database()
    from services.outcome_monitor import start_outcome_monitor
    from services.health_monitor import start_health_monitor
    install_signal_handlers()
    start_outcome_monitor()
    start_health_monitor()
    start_bot_thread()
    log.info("AI worker running - market monitors, notification delivery, and Telegram active.")
    try:
        while not _shutdown_event.is_set():
            from services.notification_queue import process_pending
            from services.runtime_monitor import record_heartbeat
            record_heartbeat("ai-worker")
            process_pending()
            _shutdown_event.wait(30)
    except KeyboardInterrupt:
        _shutdown_event.set()
    finally:
        _stop_monitors()
        log.info("AI worker shut down cleanly.")


def cmd_scheduler() -> None:
    """Run the singleton APScheduler process."""
    assert_production_ready("scheduler")
    init_database()
    install_signal_handlers()
    scheduler = start_scheduler()
    if not scheduler:
        raise SystemExit("Scheduler failed to start")
    log.info("Scheduler service running.")
    try:
        while not _shutdown_event.is_set():
            if not scheduler.running:
                raise RuntimeError("Scheduler stopped unexpectedly")
            from services.runtime_monitor import record_heartbeat
            record_heartbeat("scheduler")
            _shutdown_event.wait(30)
    except KeyboardInterrupt:
        _shutdown_event.set()
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=True)
        try:
            from db.session import engine
            engine.dispose()
        except Exception:
            log.exception("Database pool shutdown failed")
        log.info("Scheduler shut down cleanly.")


def cmd_telegram_worker() -> None:
    """Run Telegram polling under the restart supervisor as a dedicated service."""
    assert_production_ready("telegram")
    init_database()
    install_signal_handlers()
    def heartbeat():
        from services.runtime_monitor import record_heartbeat
        while not _shutdown_event.is_set():
            record_heartbeat("telegram")
            _shutdown_event.wait(30)
    threading.Thread(target=heartbeat, daemon=True, name="telegram-heartbeat").start()
    log.info("Dedicated Telegram worker starting.")
    _bot_supervisor()


def cmd_all(build_frontend: bool = True, dev_frontend: bool = False):
    from utils.config import IS_DEVELOPMENT, TELEGRAM_BOT_TOKEN

    dev_mode = dev_frontend or IS_DEVELOPMENT
    force_build = dev_mode
    assert_production_ready()

    if build_frontend:
        from scripts.frontend import build_admin_frontend, build_smc_frontend
        if not build_admin_frontend(force=force_build):
            log.warning(
                "Admin UI build skipped or failed — use `python run.py dev` for Vite hot reload."
            )
        if not build_smc_frontend(force=force_build):
            log.warning("User app build skipped or failed.")

    init_database()
    _prepare_platform_ports(dev_mode)
    start_background_services()

    api_thread = _start_api_thread()
    _start_frontend_processes(dev_mode)

    if dev_mode:
        log.info(
            "Platform ready — API http://127.0.0.1:%s | User http://127.0.0.1:5173/ | "
            "Admin http://127.0.0.1:5174/admin/ | Telegram: %s",
            API_PORT,
            "enabled" if TELEGRAM_BOT_TOKEN else "disabled",
        )
    else:
        log.info(
            "Platform ready — API http://127.0.0.1:%s | User /app/ | Admin /admin/ | Telegram: %s",
            API_PORT,
            "enabled" if TELEGRAM_BOT_TOKEN else "disabled",
        )
    _wait_for_platform(api_thread, dev_mode)


def cmd_predict(args):
    from engine.pipeline import predict_symbol, format_result_text

    def on_progress(stage, message):
        print(f"[{stage.upper()}] {message}")

    result = predict_symbol(
        args.symbol,
        interval=args.interval,
        fetch=not args.no_fetch,
        strategy_mode=args.strategy,
        on_progress=on_progress,
    )
    print("\n" + "=" * 60)
    print(format_result_text(result))
    print("=" * 60)


def cmd_backup() -> int:
    """Dump MySQL or copy SQLite to backups/."""
    import shutil
    import subprocess
    from datetime import datetime
    from urllib.parse import unquote, urlparse

    from utils.config import DATABASE_URL

    backup_dir = os.path.join(os.path.dirname(__file__), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not DATABASE_URL:
        log.error("DATABASE_URL is not configured.")
        return 1

    if DATABASE_URL.startswith("sqlite"):
        db_path = DATABASE_URL.replace("sqlite:///", "", 1)
        if not os.path.isabs(db_path):
            db_path = os.path.join(os.path.dirname(__file__), db_path)
        if not os.path.isfile(db_path):
            log.error("SQLite database file not found: %s", db_path)
            return 1
        dest = os.path.join(backup_dir, f"smartflow_{ts}.db")
        shutil.copy2(db_path, dest)
        print(dest)
        return 0

    if "mysql" in DATABASE_URL:
        url = DATABASE_URL.replace("mysql+pymysql://", "mysql://")
        parsed = urlparse(url)
        db_name = parsed.path.lstrip("/")
        host = parsed.hostname or "localhost"
        port = str(parsed.port or 3306)
        user = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        dest = os.path.join(backup_dir, f"smartflow_{ts}.sql")
        env = os.environ.copy()
        if password:
            env["MYSQL_PWD"] = password
        cmd = [
            "mysqldump",
            "-h", host,
            "-P", port,
            "-u", user,
            db_name,
        ]
        try:
            with open(dest, "w", encoding="utf-8") as out:
                subprocess.run(cmd, check=True, stdout=out, env=env)
        except FileNotFoundError:
            log.error("mysqldump not found — install MySQL client tools.")
            return 1
        except subprocess.CalledProcessError as exc:
            log.error("mysqldump failed: %s", exc)
            return 1
        print(dest)
        return 0

    log.error("Unsupported DATABASE_URL scheme: %s", DATABASE_URL)
    return 1


def cmd_backtest(args) -> int:
    """Run walk-forward backtest over cached CSVs."""
    import json
    from datetime import datetime, timezone

    import pandas as pd

    from engine.backtest import run_backtest
    from engine.data import csv_path
    from utils.config import INTERVAL
    from utils.settings import get_supported_pairs

    symbol_arg = (args.symbol or "all").upper()
    symbols = get_supported_pairs() if symbol_arg == "ALL" else [symbol_arg]
    results = []

    for sym in symbols:
        path = csv_path(sym, INTERVAL)
        if not os.path.isfile(path):
            log.warning("No CSV for %s — skipping", sym)
            continue
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        report = run_backtest(df, sym)
        results.append(report)
        if report.get("error"):
            print(f"{sym}: {report['error']}")
        else:
            print(
                f"{sym}: win_rate={report['win_rate']:.1%} trades={report['trades']} "
                f"avg_rr={report['avg_rr']} max_dd={report['max_drawdown_pct']}%"
            )

    if not results:
        log.error("No backtest results — refresh CSV data first.")
        return 1

    logs_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    out_path = os.path.join(logs_dir, "backtest_report.json")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interval": INTERVAL,
        "pairs": results,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"Report written → {out_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="SmartFlow AI - SMC/ICT forex signal platform")
    sub = parser.add_subparsers(dest="command")

    p_predict = sub.add_parser("predict", help="one-off prediction")
    p_predict.add_argument("symbol", help="currency pair, e.g. EURUSD")
    p_predict.add_argument("--interval", default=None)
    p_predict.add_argument("--no-fetch", action="store_true", help="use cached CSV")
    p_predict.add_argument(
        "--strategy",
        default="both",
        choices=["both", "smc", "ict"],
        help="confluence mode: both (default), smc only, or ict only",
    )

    p_api = sub.add_parser("api", help="API server only")
    p_api.add_argument(
        "--with-background",
        action="store_true",
        help="also start monitors, scheduler, and Telegram supervisor",
    )
    p_api.add_argument(
        "--no-background",
        action="store_true",
        help="do not start background services, even in production",
    )
    sub.add_parser("worker", help="background services only")
    sub.add_parser("ai-worker", help="continuous monitors, queue, and Telegram")
    sub.add_parser("scheduler", help="singleton scheduled jobs only")
    sub.add_parser("telegram-worker", help="dedicated supervised Telegram polling")
    sub.add_parser("migrate", help="create, migrate, verify, and seed the database")
    sub.add_parser("bot", help="Telegram bot only")
    sub.add_parser("refresh", help="refresh data + models for all pairs")
    sub.add_parser("build-admin", help="build React admin panel (admin-frontend)")
    sub.add_parser("backup", help="backup database to backups/")
    p_backtest = sub.add_parser("backtest", help="walk-forward backtest on cached CSVs")
    p_backtest.add_argument("symbol", nargs="?", default="all", help="pair symbol or 'all'")
    p_dev = sub.add_parser("dev", help="run everything + Vite admin dev server (:5174)")
    p_dev.add_argument("--no-build", action="store_true", help="skip production admin build")

    p_all = sub.add_parser("start", help="alias for default: run everything")
    p_all.add_argument("--no-build", action="store_true", help="skip admin UI npm build")

    args = parser.parse_args()

    if args.command == "predict":
        cmd_predict(args)
    elif args.command == "api":
        from utils.config import TELEGRAM_BOT_TOKEN
        assert_production_ready()
        init_database()
        _prepare_platform_ports(dev_mode=False)
        run_background = (
            not args.no_background
            and (args.with_background or _background_services_enabled_by_default())
        )
        if run_background:
            start_background_services()
        log.info(
            "Web/API http://127.0.0.1:%s  |  Telegram bot: %s",
            API_PORT,
            "enabled (parallel)" if (run_background and TELEGRAM_BOT_TOKEN) else "separate/disabled",
        )
        api_thread = _start_api_thread()
        _wait_for_platform(api_thread, dev_mode=False)
    elif args.command == "worker":
        cmd_worker()
    elif args.command == "ai-worker":
        cmd_ai_worker()
    elif args.command == "scheduler":
        cmd_scheduler()
    elif args.command == "telegram-worker":
        cmd_telegram_worker()
    elif args.command == "migrate":
        if not init_database():
            raise SystemExit(1)
    elif args.command == "bot":
        from bot import run_bot
        run_bot()
    elif args.command == "refresh":
        from batch_fetch import refresh_all
        refresh_all()
    elif args.command == "backup":
        sys.exit(cmd_backup())
    elif args.command == "backtest":
        sys.exit(cmd_backtest(args))
    elif args.command == "build-admin":
        from scripts.frontend import build_admin_frontend
        ok = build_admin_frontend(force=True)
        sys.exit(0 if ok else 1)
    elif args.command == "dev":
        cmd_all(build_frontend=not args.no_build, dev_frontend=True)
    elif args.command == "start":
        cmd_all(build_frontend=not args.no_build, dev_frontend=False)
    else:
        cmd_all(build_frontend=True, dev_frontend=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Shutting down.")
        _stop_child_processes()
        sys.exit(0)
