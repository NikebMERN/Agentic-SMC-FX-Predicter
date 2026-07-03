# admin_panel.py
"""Admin panel: UI (served at /admin) + JSON API (/admin/api/*).

Everything on the platform is controllable from here:
  - dashboard: totals, system health, data freshness
  - users: search, promote/demote, ban/unban, delete
  - signals: list, create manual signal (override the AI)
  - trades: list all, force-close
  - models & data: per-pair model metrics, retrain, delete, refresh CSVs
  - predict: run the full pipeline for any pair from the browser
  - settings: supported pairs and confidence floor, persisted in DB
  - logs: live tail of the application log

Every /admin/api/* route (except login) requires a JWT belonging to a
user with role='admin'.
"""
import glob
import json
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import joblib
from flask import Blueprint, jsonify, request, send_from_directory  # type: ignore

from engine.data import DATA_DIR, active_provider, csv_path, get_data, normalize_symbol, validate_interval, supported_intervals
from engine.model_trainer import MODEL_DIR, train_and_predict
from engine.pipeline import predict_symbol
from utils import settings
from utils.config import (
    ALPHA_VANTAGE_API_KEY, CORS_ORIGINS, DATA_PROVIDER, FETCH_COOLDOWN_MINUTES,
    INTERVAL, OANDA_API_KEY, OANDA_ENV, TELEGRAM_BOT_TOKEN,
)
from utils.logger import LOG_FILE, get_logger
from utils.security import admin_required, check_password, hash_password
from utils import mailer
from services.user_service import login_user
from services.signal_service import create_signal
from services.trade_service import close_trade, OUTCOME_WIN, OUTCOME_LOSS, OUTCOME_NEUTRAL
from services.admin_audit import log_admin_action
from db.models import (
    Account, AdminLog, ModelVersion, PasswordReset, PredictionReview,
    Setting, Signal, TelegramLink, Trade, TrainingRecord, User, UserFeedback,
)
from db.session import SessionLocal

log = get_logger("admin")

admin_bp = Blueprint("admin", __name__)

_refresh_state = {"running": False, "progress": "", "started_at": None}

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__)))
ADMIN_DIST = os.path.join(PROJECT_ROOT, "static", "admin")


def _serialize(obj):
    out = {}
    for c in obj.__table__.columns:
        val = getattr(obj, c.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        out[c.name] = val
    return out


def _outcome_score_meta(score: int | None) -> dict:
    if score == OUTCOME_WIN:
        return {
            "outcome_score_label": "Win +10",
            "scoring_help": "Profitable close — +10 points for model feedback weighting.",
        }
    if score == OUTCOME_LOSS:
        return {
            "outcome_score_label": "Loss -5",
            "scoring_help": "Losing close — -5 points for model feedback weighting.",
        }
    if score == OUTCOME_NEUTRAL:
        return {
            "outcome_score_label": "Neutral 0",
            "scoring_help": "Breakeven close — 0 points.",
        }
    return {
        "outcome_score_label": "—",
        "scoring_help": "Outcome score is set when a trade closes: +10 win, -5 loss, 0 breakeven.",
    }


def _serialize_trade(trade: Trade) -> dict:
    row = _serialize(trade)
    row.update(_outcome_score_meta(trade.outcome_score))
    return row


def _backtest_summary(report: dict | None) -> dict | None:
    if not report:
        return None
    pairs = report.get("pairs") or []
    if not pairs and report.get("symbol"):
        pairs = [report]
    if not pairs:
        return None
    best = max(pairs, key=lambda p: (p.get("win_rate") or 0, p.get("trades") or 0))
    return {
        "symbol": best.get("symbol"),
        "win_rate": best.get("win_rate"),
        "trades": best.get("trades"),
        "avg_rr": best.get("avg_rr"),
        "generated_at": report.get("generated_at"),
    }


def _read_latest_backtest() -> dict | None:
    path = os.path.join(PROJECT_ROOT, "logs", "backtest_report.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            report = json.load(fh)
        report["summary"] = _backtest_summary(report)
        return report
    except Exception:
        return None


def _persist_backtest_result(symbol: str, result: dict) -> None:
    logs_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    path = os.path.join(logs_dir, "backtest_report.json")
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "interval": INTERVAL, "pairs": []}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                existing = json.load(fh)
            payload["pairs"] = [
                p for p in (existing.get("pairs") or [])
                if p.get("symbol", "").upper() != symbol.upper()
            ]
        except Exception:
            pass
    payload["pairs"].append(result)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


# ---------------------------------------------------------------------
# React admin UI (built to static/admin) + JSON API (/admin/api/*)
# ---------------------------------------------------------------------
@admin_bp.route("/admin")
@admin_bp.route("/admin/")
@admin_bp.route("/admin/<path:path>")
def admin_ui(path=""):
    """Serve the React admin SPA; fallback message if not built yet."""
    dist = ADMIN_DIST
    index = os.path.join(dist, "index.html")
    if not os.path.isdir(dist) or not os.path.exists(index):
        return (
            "<h1>Admin UI not built</h1>"
            "<p>Run <code>python run.py build-admin</code> or "
            "<code>python run.py</code> (builds automatically).</p>"
            "<p>Dev mode: <code>python run.py dev</code> → "
            "<a href='http://127.0.0.1:5174/admin/'>http://127.0.0.1:5174/admin/</a></p>",
            503,
        )
    if path and os.path.isfile(os.path.join(dist, path)):
        return send_from_directory(dist, path)
    return send_from_directory(dist, "index.html")


@admin_bp.route("/admin/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    email, password = data.get("email"), data.get("password")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    result, err = login_user(email=email, password=password)
    if err == "pending_approval":
        return jsonify({"error": "Account pending approval."}), 403
    if err == "account_suspended":
        return jsonify({"error": "Account suspended."}), 403
    if not result:
        return jsonify({"error": "Invalid credentials"}), 401
    if getattr(result["user"], "role", "user") != "admin":
        return jsonify({"error": "Admin access required"}), 403
    return jsonify({
        "token": result["token"],
        "refresh_token": result.get("refresh_token"),
        "username": result["user"].username,
        "must_change_password": result.get("must_change_password", False),
    })


# ---------------------------------------------------------------------
# Password reset (forgot / reset / change)
# ---------------------------------------------------------------------
RESET_CODE_TTL_MINUTES = 15
RESET_MAX_ATTEMPTS = 5
MIN_PASSWORD_LENGTH = 8
_GENERIC_FORGOT_MSG = (
    "If that email belongs to an admin account, a reset code has been sent. "
    "It is valid for 15 minutes."
)


@admin_bp.route("/admin/api/forgot", methods=["POST"])
def api_forgot():
    """Issue a 6-digit reset code for an ADMIN account.

    The response never reveals whether the email exists (no account
    enumeration). The code is stored hashed with a 15-minute expiry.
    When SMTP is not configured the code is written to the server log so
    the operator can complete the reset from the machine itself.
    """
    email = ((request.get_json(silent=True) or {}).get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "Email required"}), 400

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or getattr(user, "role", "user") != "admin" or not user.is_active:
            log.info("Password reset requested for non-admin/unknown email %s", email)
            return jsonify({"message": _GENERIC_FORGOT_MSG})

        code = f"{secrets.randbelow(1_000_000):06d}"

        # One live code per user: retire any previous ones.
        db.query(PasswordReset).filter(
            PasswordReset.user_id == user.id, PasswordReset.used == False  # noqa: E712
        ).update({PasswordReset.used: True})
        db.add(PasswordReset(
            user_id=user.id,
            code_hash=hash_password(code),
            expires_at=datetime.utcnow() + timedelta(minutes=RESET_CODE_TTL_MINUTES),
        ))
        db.commit()

        sent = mailer.send_email(
            to=user.email,
            subject="SmartFlow AI — admin password reset code",
            body=(
                f"Hello {user.username},\n\n"
                f"Your admin password reset code is: {code}\n\n"
                f"It expires in {RESET_CODE_TTL_MINUTES} minutes. "
                "If you did not request this, you can ignore this email.\n"
            ),
        )
        if not sent:
            # Self-hosted fallback: the operator reads the code from the
            # server log (logs/smartflow.log). Configure SMTP_* to email it.
            log.warning(
                "SMTP unavailable — password reset code for %s: %s (valid %d min)",
                user.email, code, RESET_CODE_TTL_MINUTES,
            )
        return jsonify({"message": _GENERIC_FORGOT_MSG})
    finally:
        db.close()


@admin_bp.route("/admin/api/reset", methods=["POST"])
def api_reset():
    """Set a new password given a valid, unexpired reset code."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    new_password = data.get("new_password") or ""

    if not email or not code:
        return jsonify({"error": "Email and code required"}), 400
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return jsonify({"error": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}), 400

    invalid = jsonify({"error": "Invalid or expired reset code"}), 400
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return invalid
        reset = (
            db.query(PasswordReset)
            .filter(
                PasswordReset.user_id == user.id,
                PasswordReset.used == False,  # noqa: E712
                PasswordReset.expires_at > datetime.utcnow(),
            )
            .order_by(PasswordReset.id.desc())
            .first()
        )
        if not reset or reset.attempts >= RESET_MAX_ATTEMPTS:
            return invalid

        if not check_password(code, reset.code_hash):
            reset.attempts += 1
            if reset.attempts >= RESET_MAX_ATTEMPTS:
                reset.used = True  # burn the code after too many tries
            db.commit()
            return invalid

        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        reset.used = True
        db.commit()
        log.info("Password reset completed for %s", user.email)
        return jsonify({"message": "Password reset. You can sign in with the new password."})
    finally:
        db.close()


@admin_bp.route("/admin/api/change-password", methods=["POST"])
@admin_required
def api_change_password(admin_id):
    """Logged-in password change (requires the current password)."""
    data = request.get_json(silent=True) or {}
    current = data.get("current_password") or ""
    new_password = data.get("new_password") or ""
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return jsonify({"error": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}), 400

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == admin_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        if not getattr(user, "must_change_password", False):
            if not check_password(current, user.password_hash):
                return jsonify({"error": "Current password is incorrect"}), 401
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        db.commit()
        log.info("Admin %s changed their password", admin_id)
        log_admin_action(admin_id, "change_password", "user", admin_id)
        return jsonify({"message": "Password changed."})
    finally:
        db.close()


# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------
@admin_bp.route("/admin/api/overview")
@admin_required
def overview(admin_id):
    stats = {"users": 0, "accounts": 0, "signals": 0, "trades": 0, "open_trades": 0}
    db_ok = True
    db = SessionLocal()
    try:
        stats["users"] = db.query(User).count()
        stats["accounts"] = db.query(Account).count()
        stats["signals"] = db.query(Signal).count()
        stats["trades"] = db.query(Trade).count()
        stats["open_trades"] = db.query(Trade).filter(Trade.status == "OPEN").count()
    except Exception as exc:
        db_ok = False
        log.warning("overview: DB stats unavailable: %s", exc)
    finally:
        db.close()

    pairs = settings.get_supported_pairs()
    data_status = []
    cache_pairs_count = 0
    for pair in pairs:
        path = csv_path(pair, INTERVAL)
        entry = {"symbol": pair, "exists": os.path.exists(path)}
        if entry["exists"]:
            cache_pairs_count += 1
            entry["age_minutes"] = round((time.time() - os.path.getmtime(path)) / 60, 1)
            entry["size_kb"] = round(os.path.getsize(path) / 1024, 1)
        data_status.append(entry)

    cached_csv_files = len(glob.glob(os.path.join(DATA_DIR, f"*_{INTERVAL}.csv")))
    if cache_pairs_count == 0 and cached_csv_files > 0:
        cache_pairs_count = cached_csv_files

    provider = active_provider()
    oanda_set = bool(OANDA_API_KEY)
    av_set = bool(ALPHA_VANTAGE_API_KEY)
    any_key_set = oanda_set or av_set
    live_fetch = provider != "none"

    return jsonify({
        "stats": stats,
        "health": {
            "database": db_ok,
            "data_provider_config": DATA_PROVIDER,
            "data_provider": provider,
            "active_provider": provider,
            "oanda_key_set": oanda_set,
            "alpha_vantage_key_set": av_set,
            "alpha_vantage_key": av_set,
            "any_api_key_set": any_key_set,
            "live_fetch_available": live_fetch,
            "cache_pairs_count": cache_pairs_count,
            "cached_csv_files": cached_csv_files,
            "data_ready": live_fetch or any_key_set or cache_pairs_count > 0,
            "telegram_bot": bool(TELEGRAM_BOT_TOKEN),
            "models_on_disk": len(glob.glob(os.path.join(MODEL_DIR, "*_*.joblib"))),
            "log_file_kb": round(os.path.getsize(LOG_FILE) / 1024, 1) if os.path.exists(LOG_FILE) else 0,
            "refresh_running": _refresh_state["running"],
        },
        "data_status": data_status,
        "interval": INTERVAL,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "latest_backtest": _read_latest_backtest(),
    })


# ---------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------
@admin_bp.route("/admin/api/users")
@admin_required
def list_users(admin_id):
    q = (request.args.get("q") or "").strip()
    db = SessionLocal()
    try:
        query = db.query(User)
        if q:
            like = f"%{q}%"
            query = query.filter((User.username.like(like)) | (User.email.like(like)))
        users = query.order_by(User.id.desc()).limit(200).all()
        out = []
        for u in users:
            row = _serialize(u)
            row.pop("password_hash", None)
            out.append(row)
        return jsonify({"users": out})
    finally:
        db.close()


@admin_bp.route("/admin/api/users/<int:user_id>")
@admin_required
def get_user_detail(admin_id, user_id):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        tg = db.query(TelegramLink).filter(TelegramLink.user_id == user_id).first()
        profile = _serialize(user)
        profile.pop("password_hash", None)
        counts = {
            "signals": db.query(Signal).filter(Signal.user_id == user_id).count(),
            "trades": db.query(Trade).filter(Trade.user_id == user_id).count(),
            "predictions": db.query(PredictionReview).filter(PredictionReview.user_id == user_id).count(),
            "feedback": db.query(UserFeedback).join(
                PredictionReview, UserFeedback.prediction_id == PredictionReview.id
            ).filter(PredictionReview.user_id == user_id).count(),
        }
        log_admin_action(admin_id, "view_user", "user", user_id)
        return jsonify({
            "user": profile,
            "telegram": {
                "linked": tg is not None,
                "chat_id": tg.chat_id if tg else None,
            },
            "counts": counts,
        })
    finally:
        db.close()


@admin_bp.route("/admin/api/users/<int:user_id>/history")
@admin_required
def get_user_history(admin_id, user_id):
    from services.prediction_review import list_reviews
    from services.training_service import list_training_records

    limit = min(int(request.args.get("limit", 50)), 200)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        signals = (
            db.query(Signal).filter(Signal.user_id == user_id)
            .order_by(Signal.id.desc()).limit(limit).all()
        )
        trades = (
            db.query(Trade).filter(Trade.user_id == user_id)
            .order_by(Trade.id.desc()).limit(limit).all()
        )
        predictions = list_reviews(user_id=user_id, limit=limit)
        all_records = list_training_records(limit=500)
        pred_ids = {p["id"] for p in predictions}
        training = [r for r in all_records if r.get("user_id") == user_id or r.get("prediction_id") in pred_ids]
        log_admin_action(admin_id, "view_user_history", "user", user_id)
        return jsonify({
            "user_id": user_id,
            "predictions": predictions,
            "signals": [_serialize(s) for s in signals],
            "trades": [_serialize_trade(t) for t in trades],
            "training_records": training[:limit],
        })
    finally:
        db.close()


@admin_bp.route("/admin/api/users/<int:user_id>/role", methods=["POST"])
@admin_required
def set_role(admin_id, user_id):
    role = (request.get_json(silent=True) or {}).get("role")
    if role not in ("user", "admin"):
        return jsonify({"error": "role must be 'user' or 'admin'"}), 400
    if user_id == admin_id and role != "admin":
        return jsonify({"error": "You cannot demote yourself"}), 400
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        user.role = role
        db.commit()
        log_admin_action(admin_id, "set_role", "user", user_id, {"role": role})
        log.info("Admin %s set role of user %s to %s", admin_id, user_id, role)
        return jsonify({"message": f"User {user_id} is now {role}"})
    finally:
        db.close()


@admin_bp.route("/admin/api/users/<int:user_id>/ban", methods=["POST"])
@admin_required
def set_ban(admin_id, user_id):
    banned = bool((request.get_json(silent=True) or {}).get("banned", True))
    if user_id == admin_id:
        return jsonify({"error": "You cannot ban yourself"}), 400
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        if banned:
            user.status = "banned"
            user.is_active = False
        elif user.status == "banned":
            user.status = "active"
            user.is_active = True
        db.commit()
        log_admin_action(admin_id, "ban" if banned else "unban", "user", user_id)
        log.info("Admin %s %s user %s", admin_id, "banned" if banned else "unbanned", user_id)
        return jsonify({"message": f"User {user_id} {'banned' if banned else 'unbanned'}"})
    finally:
        db.close()


@admin_bp.route("/admin/api/users/<int:user_id>/approve", methods=["POST"])
@admin_required
def approve_user_route(admin_id, user_id):
    from services.user_service import approve_user
    from services.user_access import DEFAULT_SIGNALS_QUOTA

    data = request.get_json(silent=True) or {}
    quota = int(data.get("signals_remaining", DEFAULT_SIGNALS_QUOTA))
    user = approve_user(user_id, quota)
    if not user:
        return jsonify({"error": "User not found"}), 404
    log_admin_action(
        admin_id, "approve_user", "user", user_id,
        {"signals_remaining": quota},
    )
    log.info("Admin %s approved user %s with quota %s", admin_id, user_id, quota)
    from services.notification_service import notify_quota_updated
    notify_quota_updated(user.id, signals_remaining=user.signals_remaining, reason="approved")
    return jsonify({
        "message": f"User {user_id} approved with {quota} predictions",
        "user": {k: v for k, v in _serialize(user).items() if k != "password_hash"},
    })


@admin_bp.route("/admin/api/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(admin_id, user_id):
    if user_id == admin_id:
        return jsonify({"error": "You cannot delete yourself"}), 400
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        db.delete(user)
        db.commit()
        log_admin_action(admin_id, "delete_user", "user", user_id)
        log.info("Admin %s deleted user %s", admin_id, user_id)
        return jsonify({"message": f"User {user_id} deleted"})
    finally:
        db.close()


# ---------------------------------------------------------------------
# Signals & trades
# ---------------------------------------------------------------------
@admin_bp.route("/admin/api/signals")
@admin_required
def list_all_signals(admin_id):
    symbol = (request.args.get("symbol") or "").strip().upper()
    db = SessionLocal()
    try:
        query = db.query(Signal)
        if symbol:
            query = query.filter(Signal.symbol == symbol)
        signals = query.order_by(Signal.id.desc()).limit(100).all()
        return jsonify({"signals": [_serialize(s) for s in signals]})
    finally:
        db.close()


@admin_bp.route("/admin/api/signals", methods=["POST"])
@admin_required
def create_manual_signal(admin_id):
    data = request.get_json(silent=True) or {}
    try:
        symbol = normalize_symbol(data.get("symbol", ""))
        side = data.get("side", "").upper()
        entry_price = float(data.get("entry_price"))
        confidence = float(data.get("confidence", 1.0))
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid signal: {exc}"}), 400
    db = SessionLocal()
    try:
        signal = create_signal(
            user_id=admin_id, symbol=symbol, timeframe=INTERVAL, side=side,
            confidence=confidence, entry_price=entry_price, db=db,
        )
        log_admin_action(admin_id, "create_signal", "signal", signal.id)
        log.info("Admin %s created manual signal %s", admin_id, signal.id)
        from services.notifier import broadcast_signal
        broadcast_signal(
            signal,
            f"Manual signal #{signal.id}: {side} {symbol} @ {entry_price} (confidence {confidence:.0%})",
        )
        return jsonify({"message": f"Signal {signal.id} created", "signal": _serialize(signal)})
    finally:
        db.close()


@admin_bp.route("/admin/api/signals/<int:signal_id>", methods=["DELETE"])
@admin_required
def delete_signal(admin_id, signal_id):
    db = SessionLocal()
    try:
        signal = db.query(Signal).filter(Signal.id == signal_id).first()
        if not signal:
            return jsonify({"error": "Signal not found"}), 404
        db.delete(signal)
        db.commit()
        log_admin_action(admin_id, "delete_signal", "signal", signal_id)
        log.info("Admin %s deleted signal %s", admin_id, signal_id)
        return jsonify({"message": f"Signal {signal_id} deleted"})
    finally:
        db.close()


@admin_bp.route("/admin/api/trades")
@admin_required
def list_all_trades(admin_id):
    db = SessionLocal()
    try:
        trades = db.query(Trade).order_by(Trade.id.desc()).limit(100).all()
        return jsonify({"trades": [_serialize_trade(t) for t in trades]})
    finally:
        db.close()


@admin_bp.route("/admin/api/trades/<int:trade_id>/close", methods=["POST"])
@admin_required
def force_close_trade(admin_id, trade_id):
    try:
        trade = close_trade(trade_id, manual_close=True)
        if not trade:
            return jsonify({"error": "Trade not found"}), 404
        log_admin_action(admin_id, "force_close_trade", "trade", trade_id, {"pnl": trade.pnl})
        log.info("Admin %s force-closed trade %s (pnl %s)", admin_id, trade_id, trade.pnl)
        return jsonify({"message": f"Trade {trade_id} closed", "pnl": trade.pnl})
    except Exception as exc:
        log.exception("force close failed")
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------
# Models & data
# ---------------------------------------------------------------------
@admin_bp.route("/admin/api/models")
@admin_required
def list_models(admin_id):
    models = []
    db_files = set()
    db = SessionLocal()
    try:
        versions = db.query(ModelVersion).order_by(ModelVersion.id.desc()).limit(50).all()
        for v in versions:
            fname = os.path.basename(v.path)
            db_files.add(fname)
            models.append({
                "id": v.id,
                "file": fname,
                "symbol": v.symbol,
                "interval": v.interval,
                "active": v.is_active,
                "metrics": {
                    "samples": v.samples,
                    "val_accuracy": v.val_accuracy,
                    "trained_at": v.trained_at.isoformat() if v.trained_at else None,
                },
                "source": "db",
            })
    finally:
        db.close()
    for path in sorted(glob.glob(os.path.join(MODEL_DIR, "*_*.joblib"))):
        fname = os.path.basename(path)
        if fname in db_files:
            continue
        entry = {
            "file": os.path.basename(path),
            "size_kb": round(os.path.getsize(path) / 1024, 1),
            "modified": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
        }
        try:
            bundle = joblib.load(path)
            if isinstance(bundle, dict):
                entry["symbol"] = bundle.get("symbol")
                entry["interval"] = bundle.get("interval")
                entry["metrics"] = bundle.get("metrics")
        except Exception as exc:
            entry["error"] = f"unreadable: {exc}"
        models.append(entry)
    return jsonify({"models": models})


@admin_bp.route("/admin/api/models/retrain", methods=["POST"])
@admin_required
def retrain_model(admin_id):
    data = request.get_json(silent=True) or {}
    try:
        symbol = normalize_symbol(data.get("symbol", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    fetch = bool(data.get("fetch", True))
    try:
        df, source = get_data(symbol, INTERVAL, fetch=fetch)
        result = train_and_predict(symbol, df, INTERVAL)
        if result is None:
            return jsonify({"error": f"Not enough data to train {symbol}"}), 422
        log_admin_action(admin_id, "retrain_model", "symbol", symbol, result["metrics"])
        log.info("Admin %s retrained %s", admin_id, symbol)
        return jsonify({
            "message": f"{symbol} retrained on {result['metrics']['samples']} samples "
                       f"({source} data)",
            "metrics": result["metrics"],
        })
    except Exception as exc:
        log.exception("retrain failed")
        return jsonify({"error": str(exc)}), 500


@admin_bp.route("/admin/api/models/<name>", methods=["DELETE"])
@admin_required
def delete_model(admin_id, name):
    # Restrict to plain joblib filenames inside MODEL_DIR (no path tricks).
    if os.path.basename(name) != name or not name.endswith(".joblib"):
        return jsonify({"error": "Invalid model name"}), 400
    path = os.path.join(MODEL_DIR, name)
    if not os.path.exists(path):
        return jsonify({"error": "Model not found"}), 404
    os.remove(path)
    db = SessionLocal()
    try:
        db.query(ModelVersion).filter(ModelVersion.path.like(f"%{name}")).update(
            {ModelVersion.is_active: False}, synchronize_session=False
        )
        db.commit()
    finally:
        db.close()
    log_admin_action(admin_id, "delete_model", "model", name)
    log.info("Admin %s deleted model %s", admin_id, name)
    return jsonify({"message": f"{name} deleted"})


@admin_bp.route("/admin/api/data/refresh", methods=["POST"])
@admin_required
def refresh_data(admin_id):
    data = request.get_json(silent=True) or {}
    if data.get("all"):
        if _refresh_state["running"]:
            return jsonify({"error": "A refresh-all run is already in progress"}), 409

        def worker():
            from batch_fetch import refresh_all
            _refresh_state.update(running=True, started_at=datetime.now(timezone.utc).isoformat())
            try:
                refresh_all()
            finally:
                _refresh_state["running"] = False

        threading.Thread(target=worker, daemon=True, name="refresh-all").start()
        log_admin_action(admin_id, "refresh_all", "data", "all")
        log.info("Admin %s started refresh-all", admin_id)
        return jsonify({"message": "Refresh of all pairs started in the background"})

    try:
        symbol = normalize_symbol(data.get("symbol", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        df, source = get_data(symbol, INTERVAL, fetch=True)
        return jsonify({"message": f"{symbol}: {len(df)} candles ({source})"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@admin_bp.route("/admin/api/data/refresh/status")
@admin_required
def refresh_status(admin_id):
    return jsonify(_refresh_state)


@admin_bp.route("/admin/api/predict", methods=["POST"])
@admin_required
def admin_predict(admin_id):
    data = request.get_json(silent=True) or {}
    try:
        symbol = normalize_symbol(data.get("symbol", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    raw_interval = data.get("interval")
    if raw_interval is not None and raw_interval != "":
        try:
            interval = validate_interval(str(raw_interval))
        except ValueError as exc:
            return jsonify({"error": str(exc), "supported_intervals": supported_intervals()}), 400
    else:
        interval = INTERVAL
    fetch = bool(data.get("fetch", True))
    raw_strategy = data.get("strategy")
    if raw_strategy is None or raw_strategy == "":
        raw_strategy = data.get("strategy_mode")
    try:
        from engine.confluence import normalize_strategy_mode
        strategy = normalize_strategy_mode(raw_strategy)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        result = predict_symbol(
            symbol, interval=interval, fetch=fetch, strategy_mode=strategy
        )
        return jsonify(result)
    except Exception as exc:
        log.exception("admin predict failed")
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------
# Settings & config & logs
# ---------------------------------------------------------------------
@admin_bp.route("/admin/api/settings")
@admin_required
def get_settings(admin_id):
    from engine.confluence import SL_MAX_PCT_DEFAULT, TP_MAX_PCT_DEFAULT
    return jsonify({
        "effective": {
            "supported_pairs": settings.get_supported_pairs(),
            "min_final_confidence": settings.get_float("min_final_confidence", 0.55),
            "broadcast_signals": settings.get_broadcast_signals(),
            "predictions_enabled": settings.get("predictions_enabled", "true"),
            "disabled_pairs": settings.get("disabled_pairs", ""),
            "sl_max_pct": settings.get_float("sl_max_pct", SL_MAX_PCT_DEFAULT),
            "tp_max_pct": settings.get_float("tp_max_pct", TP_MAX_PCT_DEFAULT),
        },
        "overrides": settings.all_settings(),
    })


@admin_bp.route("/admin/api/settings", methods=["POST"])
@admin_required
def update_settings(admin_id):
    data = request.get_json(silent=True) or {}
    applied = {}

    if "supported_pairs" in data:
        raw = data["supported_pairs"]
        pairs = [p.strip().upper() for p in str(raw).split(",") if p.strip()]
        try:
            pairs = [normalize_symbol(p) for p in pairs]
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not pairs:
            return jsonify({"error": "At least one pair required"}), 400
        settings.set("supported_pairs", ",".join(pairs))
        applied["supported_pairs"] = pairs

    if "min_final_confidence" in data:
        try:
            value = float(data["min_final_confidence"])
        except (TypeError, ValueError):
            return jsonify({"error": "min_final_confidence must be a number"}), 400
        if not 0.30 <= value <= 0.95:
            return jsonify({"error": "min_final_confidence must be between 0.30 and 0.95"}), 400
        settings.set("min_final_confidence", str(value))
        applied["min_final_confidence"] = value

    if "broadcast_signals" in data:
        value = bool(data["broadcast_signals"])
        settings.set("broadcast_signals", "true" if value else "false")
        applied["broadcast_signals"] = value

    if "predictions_enabled" in data:
        value = bool(data["predictions_enabled"])
        settings.set("predictions_enabled", "true" if value else "false")
        applied["predictions_enabled"] = value

    if "disabled_pairs" in data:
        raw = data["disabled_pairs"]
        pairs = [p.strip().upper() for p in str(raw).split(",") if p.strip()]
        for p in pairs:
            try:
                normalize_symbol(p)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
        settings.set("disabled_pairs", ",".join(pairs))
        applied["disabled_pairs"] = pairs

    # Max SL/TP distance as a percent of price — keeps levels realistic.
    for key, low, high in (("sl_max_pct", 0.05, 2.0), ("tp_max_pct", 0.10, 5.0)):
        if key in data:
            try:
                value = float(data[key])
            except (TypeError, ValueError):
                return jsonify({"error": f"{key} must be a number"}), 400
            if not low <= value <= high:
                return jsonify({"error": f"{key} must be between {low} and {high} (percent)"}), 400
            settings.set(key, str(value))
            applied[key] = value

    if not applied:
        return jsonify({"error": "Nothing to update"}), 400
    log.info("Admin %s updated settings: %s", admin_id, applied)
    log_admin_action(admin_id, "update_settings", "settings", None, applied)
    return jsonify({"message": "Settings saved", "applied": applied})


@admin_bp.route("/admin/api/users/<int:user_id>/quota", methods=["POST"])
@admin_required
def set_user_quota(admin_id, user_id):
    amount = int((request.get_json(silent=True) or {}).get("signals_remaining", 0))
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        user.signals_remaining = max(0, amount)
        db.commit()
        db.refresh(user)
        log_admin_action(admin_id, "set_quota", "user", user_id, {"signals_remaining": user.signals_remaining})
        from services.notification_service import notify_quota_updated
        notify_quota_updated(user.id, signals_remaining=user.signals_remaining, reason="updated by admin")
        row = _serialize(user)
        row.pop("password_hash", None)
        return jsonify({
            "message": f"Quota set to {user.signals_remaining}",
            "user": row,
        })
    finally:
        db.close()


@admin_bp.route("/admin/api/training-records")
@admin_required
def list_training_records_route(admin_id):
    from services.training_service import list_training_records
    status = (request.args.get("status") or "").strip() or None
    limit = min(int(request.args.get("limit", 100)), 500)
    return jsonify({"records": list_training_records(status=status, limit=limit)})


@admin_bp.route("/admin/api/training-records/<int:record_id>/review", methods=["PATCH"])
@admin_required
def review_training_record_route(admin_id, record_id):
    from services.training_service import review_training_record
    data = request.get_json(silent=True) or {}
    status = (data.get("admin_status") or "").strip().upper()
    if status not in {"PENDING_REVIEW", "APPROVED", "REJECTED", "NEEDS_MORE_DATA"}:
        return jsonify({"error": "Invalid admin_status"}), 400
    row = review_training_record(
        record_id,
        admin_status=status,
        admin_notes=data.get("admin_notes"),
        label_quality_score=data.get("label_quality_score"),
    )
    if not row:
        return jsonify({"error": "Training record not found"}), 404
    log_admin_action(admin_id, "review_training_record", "training_record", record_id, {
        "admin_status": status,
        "label_quality_score": row.label_quality_score,
    })
    return jsonify({"message": "Training record updated", "record": {
        "id": row.id,
        "admin_status": row.admin_status,
        "conflict": row.conflict,
    }})


@admin_bp.route("/admin/api/training-records/export")
@admin_required
def export_training_records(admin_id):
    from services.training_service import export_approved_records
    limit = min(int(request.args.get("limit", 5000)), 10000)
    records = export_approved_records(limit=limit)
    log_admin_action(admin_id, "export_training_records", "training_record", None, {"count": len(records)})
    return jsonify({"records": records, "count": len(records)})


@admin_bp.route("/admin/api/analytics")
@admin_required
def admin_analytics(admin_id):
    import json as _json
    from db.models import MarketVerification, PredictionReview, TrainingRecord
    db = SessionLocal()
    try:
        reviews = db.query(PredictionReview).filter(PredictionReview.status == "evaluated").all()
        by_pair: dict[str, dict] = {}
        by_interval: dict[str, dict] = {}
        calibration: dict[str, dict] = {}
        no_trade_reasons: dict[str, int] = {}
        conflicts = db.query(TrainingRecord).filter(TrainingRecord.conflict.is_(True)).count()
        verify_failures = db.query(PredictionReview).filter(
            PredictionReview.status == "verification_failed"
        ).count()

        for r in reviews:
            pair = r.symbol
            iv = r.interval or "60min"
            by_pair.setdefault(pair, {"total": 0, "correct": 0})
            by_interval.setdefault(iv, {"total": 0, "correct": 0})
            by_pair[pair]["total"] += 1
            by_interval[iv]["total"] += 1
            if r.was_correct:
                by_pair[pair]["correct"] += 1
                by_interval[iv]["correct"] += 1

            bucket = "high" if (r.predicted_confidence or 0) >= 0.7 else (
                "medium" if (r.predicted_confidence or 0) >= 0.55 else "low"
            )
            calibration.setdefault(bucket, {"total": 0, "correct": 0})
            calibration[bucket]["total"] += 1
            if r.was_correct:
                calibration[bucket]["correct"] += 1

            if r.predicted_action in ("NO_TRADE", "WAIT_FOR_CONFIRMATION") and r.scores_json:
                try:
                    scores = _json.loads(r.scores_json)
                except Exception:
                    scores = {}
                if not scores and r.predicted_action == "NO_TRADE":
                    no_trade_reasons["no_signals"] = no_trade_reasons.get("no_signals", 0) + 1

        def _accuracy(d):
            return {
                k: {
                    "total": v["total"],
                    "correct": v["correct"],
                    "accuracy": round(v["correct"] / v["total"], 4) if v["total"] else None,
                }
                for k, v in d.items()
            }

        return jsonify({
            "accuracy_by_pair": _accuracy(by_pair),
            "accuracy_by_interval": _accuracy(by_interval),
            "calibration": _accuracy(calibration),
            "conflict_count": conflicts,
            "verification_failure_count": verify_failures,
            "no_trade_reasons": no_trade_reasons,
        })
    finally:
        db.close()


@admin_bp.route("/admin/api/reviews")
@admin_required
def list_prediction_reviews(admin_id):
    from services.prediction_review import list_reviews
    status = (request.args.get("status") or "").strip() or None
    return jsonify({"reviews": list_reviews(status=status)})


@admin_bp.route("/admin/api/reviews/<int:review_id>/retrain", methods=["POST"])
@admin_required
def retrain_from_review(admin_id, review_id):
    from services.prediction_review import get_review, set_review_status
    from engine.model_trainer import retrain_with_feedback

    review = get_review(review_id)
    if not review:
        return jsonify({"error": "Review not found"}), 404
    data = request.get_json(silent=True) or {}
    promote = bool(data.get("promote", True))
    try:
        df, source = get_data(review.symbol, review.interval or INTERVAL, fetch=True)
        result = retrain_with_feedback(review.symbol, df, review.interval or INTERVAL, promote=promote)
        if result is None:
            return jsonify({"error": "Not enough data to retrain"}), 422
        set_review_status(review_id, "retrain_done")
        log_admin_action(admin_id, "retrain_from_review", "review", review_id, {
            "symbol": review.symbol,
            "promote": promote,
            "metrics": result.get("metrics"),
        })
        return jsonify({
            "message": f"Retrained {review.symbol} from review #{review_id}",
            "promoted": result.get("promoted", False),
            "metrics": result.get("metrics"),
            "data_source": source,
        })
    except Exception as exc:
        log.exception("retrain from review failed")
        return jsonify({"error": str(exc)}), 500


@admin_bp.route("/admin/api/reviews/<int:review_id>/dismiss", methods=["POST"])
@admin_required
def dismiss_review(admin_id, review_id):
    from services.prediction_review import set_review_status
    if not set_review_status(review_id, "dismissed"):
        return jsonify({"error": "Review not found"}), 404
    log_admin_action(admin_id, "dismiss_review", "review", review_id)
    return jsonify({"message": f"Review {review_id} dismissed"})


@admin_bp.route("/admin/api/models/candidates")
@admin_required
def list_model_candidates(admin_id):
    from services.feedback_service import get_model_candidates
    symbol = (request.args.get("symbol") or "").strip().upper() or None
    return jsonify({"candidates": get_model_candidates(symbol=symbol, interval=INTERVAL)})


@admin_bp.route("/admin/api/models/versions/<int:version_id>/promote", methods=["POST"])
@admin_required
def promote_model_version_route(admin_id, version_id):
    from services.feedback_service import promote_model_version, get_pending_feedback, mark_samples_used

    row = promote_model_version(version_id)
    if not row:
        return jsonify({"error": "Model version not found"}), 404
    pending = get_pending_feedback(row.symbol, row.interval)
    if pending:
        mark_samples_used([s["id"] for s in pending])
    log_admin_action(admin_id, "promote_model", "model_version", version_id, {
        "symbol": row.symbol,
        "val_accuracy": row.val_accuracy,
    })
    return jsonify({
        "message": f"Promoted model v{version_id} for {row.symbol}",
        "symbol": row.symbol,
        "val_accuracy": row.val_accuracy,
    })


@admin_bp.route("/admin/api/backtest", methods=["POST"])
@admin_required
def admin_backtest(admin_id):
    from engine.backtest import run_backtest
    data = request.get_json(silent=True) or {}
    try:
        symbol = normalize_symbol(data.get("symbol", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        df, _ = get_data(symbol, INTERVAL, fetch=bool(data.get("fetch", False)))
        result = run_backtest(df, symbol, max_bars=int(data.get("max_bars", 800)))
        if not result.get("error"):
            _persist_backtest_result(symbol, result)
        log_admin_action(admin_id, "backtest", "symbol", symbol, result)
        result["saved_to_report"] = not bool(result.get("error"))
        return jsonify(result)
    except Exception as exc:
        log.exception("backtest failed")
        return jsonify({"error": str(exc)}), 500


@admin_bp.route("/admin/api/audit")
@admin_required
def list_audit_logs(admin_id):
    action = (request.args.get("action") or "").strip()
    limit = min(int(request.args.get("limit", 100)), 500)
    db = SessionLocal()
    try:
        query = db.query(AdminLog)
        if action:
            query = query.filter(AdminLog.action == action)
        rows = query.order_by(AdminLog.id.desc()).limit(limit).all()
        return jsonify({"logs": [_serialize(r) for r in rows]})
    finally:
        db.close()


@admin_bp.route("/admin/api/config")
@admin_required
def view_config(admin_id):
    return jsonify({
        "interval": INTERVAL,
        "fetch_cooldown_minutes": FETCH_COOLDOWN_MINUTES,
        "cors_origins": CORS_ORIGINS,
        "data_provider": DATA_PROVIDER,
        "active_provider": active_provider(),
        "oanda_env": OANDA_ENV,
        "oanda_key_set": bool(OANDA_API_KEY),
        "alpha_vantage_key_set": bool(ALPHA_VANTAGE_API_KEY),
        "telegram_bot_token_set": bool(TELEGRAM_BOT_TOKEN),
        "data_dir": DATA_DIR,
        "model_dir": MODEL_DIR,
    })


@admin_bp.route("/admin/api/logs")
@admin_required
def tail_logs(admin_id):
    lines = min(int(request.args.get("lines", 200)), 1000)
    if not os.path.exists(LOG_FILE):
        return jsonify({"lines": []})
    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
        content = f.readlines()
    return jsonify({"lines": [ln.rstrip("\n") for ln in content[-lines:]]})


@admin_bp.route("/admin/api/notifications")
@admin_required
def list_admin_notifications(admin_id):
    from services.notification_service import list_notifications, unread_count
    unread_only = request.args.get("unread") == "1"
    limit = min(int(request.args.get("limit", 30)), 100)
    return jsonify({
        "notifications": list_notifications(admin_id, unread_only=unread_only, limit=limit),
        "unread_count": unread_count(admin_id),
    })


@admin_bp.route("/admin/api/notifications/<int:notification_id>/read", methods=["PATCH", "POST"])
@admin_required
def mark_admin_notification_read(admin_id, notification_id):
    from services.notification_service import mark_read
    if not mark_read(notification_id, admin_id):
        return jsonify({"error": "Notification not found"}), 404
    return jsonify({"message": "Marked as read"})


@admin_bp.route("/admin/api/notifications/read-all", methods=["POST"])
@admin_required
def mark_all_admin_notifications_read(admin_id):
    from services.notification_service import mark_all_read, unread_count
    updated = mark_all_read(admin_id)
    return jsonify({"message": f"Marked {updated} as read", "unread_count": unread_count(admin_id)})
