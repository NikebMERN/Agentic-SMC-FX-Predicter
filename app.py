# app.py
import json
import os

from flask import Flask, request, jsonify, Response, stream_with_context  # type: ignore
from flask_cors import CORS  # type: ignore
from flask_limiter import Limiter  # type: ignore
from flask_limiter.util import get_remote_address  # type: ignore

from engine.data import normalize_symbol, validate_interval, supported_intervals
from engine.pipeline import predict_symbol
from utils.config import IS_DEVELOPMENT, CORS_ORIGINS, INTERVAL
from utils.logger import get_logger
from utils.settings import get_supported_pairs
from utils import settings as runtime_settings
from utils.compliance import assert_safe_wording, DISCLAIMER
from utils.security import generate_token, token_required, approved_user_required, prediction_access_required, exchange_refresh_token, generate_refresh_token, revoke_refresh_tokens
from services.user_access import decrement_quota, increment_quota, DEFAULT_SIGNALS_QUOTA
from services.user_service import (
    change_password, login_user, register_user, request_password_reset,
    reset_password, validate_password,
)
from services.account_service import create_account, get_account_by_id, set_default_account, update_balance, delete_account
from services.trade_service import open_trade, get_trades, close_trade, get_trade_by_id
from services.signal_service import create_signal, get_signals
from db.models import Account, User
from db.session import SessionLocal, get_db

log = get_logger("api")

app = Flask(__name__)
CORS(app, origins=CORS_ORIGINS)
if CORS_ORIGINS == ["*"]:
    log.warning("CORS allows every origin — set CORS_ORIGINS in production.")

# Brute-force protection. In-memory storage is right for the single-process
# deployment; point it at Redis when scaling out.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per minute"],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
)

DATA_FOLDER = "data"


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


# ---------------- ADMIN PANEL ----------------
from admin_panel import admin_bp  # noqa: E402
from user_panel import user_bp  # noqa: E402
app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)
limiter.limit("10 per minute")(app.view_functions["admin.api_login"])
limiter.limit("5 per minute")(app.view_functions["admin.api_forgot"])
limiter.limit("5 per minute")(app.view_functions["admin.api_reset"])

# ---------------- UTILS ----------------
def serialize(obj):
    """Convert SQLAlchemy model instance into dict."""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def risk_lot_size(balance: float, risk_pct: float, entry: float, stop_loss: float, symbol: str) -> float:
    """Lot size so that hitting the SL loses balance * risk_pct."""
    pip_size = 0.01 if symbol.upper().endswith("JPY") else 0.0001
    pip_value_per_lot = 10.0  # simplified standard-lot pip value (USD)
    sl_pips = abs(entry - stop_loss) / pip_size
    if sl_pips <= 0:
        return 0.01
    lots = (balance * risk_pct) / (sl_pips * pip_value_per_lot)
    return max(0.01, round(lots, 2))


# ---------------- AUTH ROUTES ----------------
@app.route("/register", methods=["POST"])
@limiter.limit("10 per minute")
def register():
    data = request.get_json()
    username, email, password = data.get("username"), data.get("email"), data.get("password")
    if not username or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    policy_error = validate_password(password)
    if policy_error:
        return jsonify({"error": policy_error}), 400
    user = register_user(username=username, email=email, password=password)
    if not user:
        return jsonify({"error": "Username or email already exists"}), 400
    return jsonify({
        "message": "Registration complete — you have 5 free trial predictions (web + Telegram when linked).",
        "status": "active",
        "signals_remaining": DEFAULT_SIGNALS_QUOTA,
        "user_id": user.id,
    }), 201

@app.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    data = request.get_json()
    email, password = data.get("email"), data.get("password")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    result = login_user(email=email, password=password)
    if isinstance(result, tuple):
        payload, err = result
    else:
        payload, err = result, None
    if err == "account_suspended":
        return jsonify({"error": "Account suspended.", "status": "banned"}), 403
    if not payload:
        return jsonify({"error": "Invalid credentials"}), 401
    user = payload["user"]
    status = getattr(user, "status", "active")
    return jsonify({
        "message": "Login successful" if status == "active" else "Signed in — account pending admin approval.",
        "token": payload["token"],
        "refresh_token": payload.get("refresh_token"),
        "user_id": user.id,
        "username": user.username,
        "status": status,
        "signals_remaining": user.signals_remaining,
        "must_change_password": payload.get("must_change_password", False),
    })

@app.route("/refresh", methods=["POST"])
@limiter.limit("30 per minute")
def refresh_token_route():
    data = request.get_json(silent=True) or {}
    raw = data.get("refresh_token") or ""
    result = exchange_refresh_token(raw)
    if not result:
        return jsonify({"error": "Invalid or expired refresh token"}), 401
    return jsonify({
        "token": result["access_token"],
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "user_id": result["user_id"],
    })

@app.route("/logout", methods=["POST"])
@token_required
def logout(user_id):
    revoke_refresh_tokens(user_id)
    return jsonify({"message": "Logged out"})

@app.route("/forgot-password", methods=["POST"])
@limiter.limit("5 per minute")
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    result = request_password_reset(email)
    # Never reveal whether the account exists.
    response = {"message": "If that email is registered, a reset code has been sent."}

    if result["user_exists"] and not result["sent"]:
        if IS_DEVELOPMENT:
            # No SMTP locally — surface the code so the flow stays testable.
            response["dev_code"] = result["code"]
            response["message"] = "SMTP not configured (development mode) — use dev_code."
        else:
            log.error("Password reset email could not be sent — configure SMTP_* env vars.")
            return jsonify({"error": "Password reset email service is not configured. Contact the administrator."}), 503

    return jsonify(response)

@app.route("/reset-password", methods=["POST"])
@limiter.limit("5 per minute")
def reset_password_route():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    code = (data.get("code") or "").strip()
    new_password = data.get("new_password") or ""
    if not email or not code or not new_password:
        return jsonify({"error": "email, code and new_password are required"}), 400
    ok, message = reset_password(email, code, new_password)
    if not ok:
        return jsonify({"error": message}), 400
    return jsonify({"message": message})

@app.route("/change-password", methods=["POST"])
@token_required
def change_password_route(user_id):
    data = request.get_json(silent=True) or {}
    ok, message = change_password(
        user_id, data.get("current_password") or "", data.get("new_password") or ""
    )
    if not ok:
        return jsonify({"error": message}), 400
    return jsonify({"message": message})

# ---------------- ACCOUNT ROUTES ----------------
@app.route("/accounts/create", methods=["POST"])
@approved_user_required
def create_new_account(user_id):
    data = request.get_json()
    name = data.get("name")
    balance = data.get("balance", 0)
    risk_pct = data.get("risk_pct", 0.01)
    leverage = data.get("leverage", 100)

    account = create_account(user_id, name, balance, risk_pct, leverage)

    return jsonify({
        "message": "Account created",
        "account": {
            "id": account.id,
            "user_id": account.user_id,
            "name": account.name,
            "balance": account.balance,
            "risk_pct": account.base_risk_pct,
            "leverage": account.leverage
        }
    })

@app.route("/accounts/all", methods=["GET"])
@approved_user_required
def list_accounts(user_id):
    db = SessionLocal()
    try:
        accounts = db.query(Account).filter_by(user_id=user_id).all()
        return jsonify({"user_id": user_id, "accounts": [serialize(a) for a in accounts]})
    finally:
        db.close()

@app.route("/accounts/<int:account_id>", methods=["GET"])
@approved_user_required
def get_account(user_id, account_id):
    account = get_account_by_id(user_id, account_id)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(serialize(account))

@app.route("/accounts/set_default/<int:account_id>", methods=["PUT"])
@approved_user_required
def set_default(user_id, account_id):
    account = set_default_account(user_id, account_id)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    return jsonify({"message": f"Account {account_id} set as default"})

@app.route("/accounts/update_balance/<int:account_id>", methods=["PUT"])
@approved_user_required
def update_account_balance(user_id, account_id):
    data = request.get_json()
    new_balance = data.get("new_balance")
    if new_balance is None:
        return jsonify({"error": "New balance is required"}), 400
    account = update_balance(account_id, new_balance)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    return jsonify({"message": f"Account {account_id} balance updated"})

@app.route("/accounts/delete/<int:account_id>", methods=["DELETE"])
@approved_user_required
def delete_account_route(user_id, account_id):
    success = delete_account(account_id)
    if not success:
        return jsonify({"error": "Account not found or could not be deleted"}), 404
    return jsonify({"message": f"Account {account_id} deleted"})

# ---------------- TRADE ROUTES ----------------
@app.route("/trades", methods=["GET"])
@approved_user_required
def list_trades(user_id):
    trades = get_trades(user_id)
    return jsonify({"user_id": user_id, "trades": [serialize(t) for t in trades]})

@app.route("/close-trade/<int:trade_id>", methods=["POST"])
@approved_user_required
def close_trade_route(user_id, trade_id):
    """
    Close a trade by ID. Determines if TP/SL was hit automatically or user closed manually.
    Expects optional JSON body: { "manual_close": true } to force manual close
    """
    from services.trade_service import get_trade_by_id
    existing = get_trade_by_id(trade_id)
    if not existing:
        return jsonify({"error": "Trade not found"}), 404
    if existing.user_id != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    manual_close = data.get("manual_close", False)

    try:
        trade = close_trade(trade_id, manual_close=manual_close)
        if not trade:
            return jsonify({"error": "Trade not found"}), 404

        scenario = "Manual Close"
        if not manual_close:
            if trade.pnl and trade.pnl > 0:
                scenario = "Take Profit Hit"
            elif trade.pnl and trade.pnl < 0:
                scenario = "Stop Loss Hit"
            else:
                scenario = "Flat Close"

        # pnl = price_change * 100000 * lots, so invert to approximate exit price
        price_change = (trade.pnl or 0) / (100_000 * trade.lot_size) if trade.lot_size else 0
        if trade.side.upper() == "SELL":
            price_change = -price_change
        response = {
            "trade_id": trade.id,
            "symbol": trade.symbol,
            "side": trade.side,
            "entry_price": trade.entry_price,
            "exit_price": round(trade.entry_price + price_change, 5),
            "lot_size": trade.lot_size,
            "pnl": trade.pnl,
            "outcome_score": trade.outcome_score,
            "scenario": scenario,
            "closed_at": trade.closed_at.isoformat() if trade.closed_at else None
        }

        return jsonify(response), 200

    except Exception as e:
        log.exception("close_trade failed")
        return jsonify({"error": str(e)}), 500


# ---------------- SIGNAL ROUTES ----------------
@app.route("/signals", methods=["GET"])
@approved_user_required
def list_signals(user_id):
    db = SessionLocal()
    signals = get_signals(user_id, db)
    return jsonify({"user_id": user_id, "signals": [serialize(s) for s in signals]})

# ---------------- PREDICTION ROUTES ----------------
@app.route("/healthz", methods=["GET"])
def healthz():
    db_ok = True
    try:
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
    except Exception:
        db_ok = False
    from engine.model_trainer import MODEL_DIR
    from utils.config import TELEGRAM_BOT_TOKEN
    payload = {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "data_dir_writable": os.access(DATA_FOLDER, os.W_OK),
        "models_dir": os.path.isdir(MODEL_DIR),
        "bot_configured": bool(TELEGRAM_BOT_TOKEN),
    }
    return jsonify(payload), 200 if db_ok else 503


@app.route("/telegram/link-code", methods=["POST"])
@token_required
def telegram_link_code(user_id):
    from services.telegram_link import create_link_code
    code = create_link_code(user_id)
    return jsonify({"message": "Use /link CODE in Telegram within 15 minutes.", "code": code})


def _check_kill_switch(symbol: str) -> tuple[bool, str]:
    enabled = runtime_settings.get("predictions_enabled", "true")
    if str(enabled).strip().lower() in {"0", "false", "no", "off"}:
        return False, "Predictions are temporarily disabled by the administrator."
    disabled_raw = runtime_settings.get("disabled_pairs", "") or ""
    disabled = {p.strip().upper() for p in disabled_raw.split(",") if p.strip()}
    sym = symbol.upper()
    if sym in disabled:
        return False, f"Predictions are disabled for {sym}."
    return True, ""


def _user_has_disclosure(user_id: int) -> bool:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        return bool(user and getattr(user, "risk_disclosure_accepted_at", None))
    finally:
        db.close()


def _parse_horizon(data: dict) -> str:
    raw = (data.get("horizon") or "intraday").strip().lower()
    if raw not in {"scalping", "intraday", "swing"}:
        return "intraday"
    return raw


def _check_and_decrement_quota(user_id: int) -> tuple[bool, str]:
    return decrement_quota(user_id)


@app.route("/me/accept-disclosure", methods=["POST"])
@approved_user_required
def accept_disclosure(user_id):
    from datetime import datetime
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        user.risk_disclosure_accepted_at = datetime.utcnow()
        db.commit()
        return jsonify({
            "message": "Risk disclosure accepted.",
            "disclaimer": DISCLAIMER,
            "risk_disclosure_accepted_at": user.risk_disclosure_accepted_at.isoformat(),
        })
    finally:
        db.close()


@app.route("/me", methods=["GET"])
@token_required
def me(user_id):
    from services.user_access import get_user
    user = get_user(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "status": getattr(user, "status", "active"),
        "signals_remaining": user.signals_remaining,
        "role": user.role,
        "risk_disclosure_accepted": bool(getattr(user, "risk_disclosure_accepted_at", None)),
        "disclaimer": DISCLAIMER,
    })


@app.route("/my/reviews/<int:review_id>/feedback", methods=["POST"])
@approved_user_required
def submit_review_feedback(user_id, review_id):
    data = request.get_json(silent=True) or {}
    from services.user_feedback_service import submit_feedback
    ok, msg, row = submit_feedback(
        user_id,
        review_id,
        data.get("feedback", ""),
        data.get("comment"),
    )
    if not ok:
        code = 404 if "not found" in msg.lower() else 409 if "already" in msg.lower() else 400
        return jsonify({"error": msg}), code
    return jsonify({
        "message": msg,
        "feedback": row.feedback,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
    })


@app.route("/my/reviews", methods=["GET"])
@token_required
def my_reviews(user_id):
    from services.prediction_review import list_reviews
    status = request.args.get("status")
    limit = min(int(request.args.get("limit", 100)), 200)
    return jsonify({"reviews": list_reviews(status=status, user_id=user_id, limit=limit)})


@app.route("/my/history", methods=["GET"])
@token_required
def my_history(user_id):
    from services.prediction_history import get_user_history
    hours = min(int(request.args.get("hours", 24)), 168)
    limit = min(int(request.args.get("limit", 100)), 200)
    return jsonify(get_user_history(user_id, hours=hours, limit=limit))


@app.route("/my/reviews/<int:review_id>/candles", methods=["GET"])
@token_required
def my_review_candles(user_id, review_id):
    from services.prediction_history import get_review_candles
    bars = min(int(request.args.get("bars", 48)), 120)
    data = get_review_candles(user_id, review_id, bars=bars)
    if not data:
        return jsonify({"error": "Review not found"}), 404
    return jsonify(data)


@app.route("/")
def index():
    return jsonify({
        "message": "SmartFlow AI API is running.",
        "web_app": "http://127.0.0.1:5173/",
        "admin_panel": f"http://127.0.0.1:{os.getenv('API_PORT', '5000')}/admin/",
        "health": "/healthz",
        "endpoints": {
            "GET /pairs": "List supported currency pairs",
            "GET /data": "List available data files",
            "POST /analyze": "{symbol} -> full SMC/ICT + ML prediction (no trade opened)",
            "POST /predict/<account_id>": "{symbol} -> SSE stream: fetch latest data, retrain, predict, open trade",
        },
    })

@app.route("/pairs", methods=["GET"])
def list_pairs():
    return jsonify({"pairs": get_supported_pairs(), "interval": INTERVAL})

@app.route("/data", methods=["GET"])
@approved_user_required
def list_data_files(user_id):
    try:
        files = [f for f in os.listdir(DATA_FOLDER) if f.endswith(".csv")]
        return jsonify({"available_files": files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _extract_symbol(data: dict) -> str:
    """Accept {'symbol': 'EURUSD'} or the legacy {'filename': 'EURUSD_60min.csv'}."""
    raw = data.get("symbol") or (data.get("filename") or "").split("_")[0]
    return normalize_symbol(raw)


def _parse_interval(data: dict) -> str:
    raw = data.get("interval")
    if raw is None or raw == "":
        return INTERVAL
    return validate_interval(str(raw))


def _parse_strategy(data: dict) -> str:
    from engine.confluence import normalize_strategy_mode
    raw = data.get("strategy")
    if raw is None or raw == "":
        raw = data.get("strategy_mode")
    try:
        return normalize_strategy_mode(raw)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


@app.route("/analyze", methods=["POST"])
@prediction_access_required
def analyze(user_id):
    """Full pipeline (fetch latest CSV -> train -> predict) without touching accounts."""
    if not _user_has_disclosure(user_id):
        return jsonify({
            "error": "You must accept the risk disclosure before running predictions.",
            "code": "disclosure_required",
            "disclaimer": DISCLAIMER,
        }), 403

    data = request.get_json(silent=True) or {}
    try:
        symbol = _extract_symbol(data)
        interval = _parse_interval(data)
        strategy = _parse_strategy(data)
        horizon = _parse_horizon(data)
    except ValueError as exc:
        return jsonify({"error": str(exc), "supported_intervals": supported_intervals()}), 400

    ks_ok, ks_msg = _check_kill_switch(symbol)
    if not ks_ok:
        return jsonify({"error": ks_msg, "code": "predictions_disabled"}), 403

    ok, quota_msg = _check_and_decrement_quota(user_id)
    if not ok:
        return jsonify({"error": quota_msg}), 429
    fetch = bool(data.get("fetch", True))
    try:
        result = predict_symbol(
            symbol, interval=interval, fetch=fetch, strategy_mode=strategy
        )
        decision = result.get("decision", {})
        from services.prediction_record import record_prediction_from_result
        review = record_prediction_from_result(
            user_id=user_id,
            result=result,
            horizon=horizon,
            source="web",
        )
        result["review_id"] = review.id if review else None
        result["quota"] = quota_msg
        return jsonify(result)
    except Exception as exc:
        increment_quota(user_id)
        log.exception("analyze failed for %s", symbol)
        return jsonify({"error": str(exc)}), 500


@app.route("/predict/<int:account_id>", methods=["POST"])
@prediction_access_required
def predict_stream(user_id, account_id):
    """SSE stream: pull latest CSV for the pair, retrain its model on it,
    aggregate valid SMC+ICT signals, then record the signal and open a
    risk-sized trade on the account."""
    if not _user_has_disclosure(user_id):
        return jsonify({
            "error": "You must accept the risk disclosure before running predictions.",
            "code": "disclosure_required",
            "disclaimer": DISCLAIMER,
        }), 403

    data = request.get_json(silent=True) or {}
    try:
        symbol = _extract_symbol(data)
        interval = _parse_interval(data)
        strategy = _parse_strategy(data)
        horizon = _parse_horizon(data)
    except ValueError as exc:
        return jsonify({"error": str(exc), "supported_intervals": supported_intervals()}), 400

    ks_ok, ks_msg = _check_kill_switch(symbol)
    if not ks_ok:
        return jsonify({"error": ks_msg, "code": "predictions_disabled"}), 403

    account = get_account_by_id(user_id, account_id)
    if not account:
        return jsonify({"error": "Account not found or unauthorized"}), 404

    balance = account.balance or 1000
    risk_pct = account.base_risk_pct or 0.01

    ok, err = _check_and_decrement_quota(user_id)
    if not ok:
        return jsonify({"error": err}), 429

    def event_stream():
        updates: list[str] = []

        def on_progress(stage, message):
            updates.append(f"data: [{stage.upper()}] {message}\n\n")

        try:
            yield f"data: [PREDICT] Starting prediction for {symbol} ({strategy})\n\n"
            result = predict_symbol(
                symbol, interval=interval, strategy_mode=strategy, on_progress=on_progress
            )
            for u in updates:
                yield u

            decision = result["decision"]
            yield f"data: [RESULT] {json.dumps(result, default=str)}\n\n"

            from engine.confluence import is_trade_action, trade_side_from_action
            trade_side = trade_side_from_action(decision["action"])
            if not is_trade_action(decision["action"]):
                yield f"data: [PREDICT] {symbol}: {decision['action']} — no position opened.\n\n"
                from services.prediction_record import record_prediction_from_result
                record_prediction_from_result(
                    user_id=user_id,
                    result=result,
                    horizon=horizon,
                    source="web",
                )
                return

            db = next(get_db())
            try:
                signal = create_signal(
                    user_id=user_id,
                    symbol=symbol,
                    timeframe=result["interval"],
                    side=trade_side,
                    confidence=decision["confidence"],
                    entry_price=decision["entry"],
                    stop_loss=decision.get("stop_loss"),
                    take_profit=decision.get("take_profit"),
                    db=db,
                )
                from services.prediction_record import record_prediction_from_result
                record_prediction_from_result(
                    user_id=user_id,
                    result=result,
                    horizon=horizon,
                    signal_id=signal.id,
                    source="web",
                )
                from utils.compliance import assert_safe_wording
                msg = assert_safe_wording(
                    f"SmartFlow signal #{signal.id}: {trade_side} {symbol} @ {decision['entry']} "
                    f"(SL {decision.get('stop_loss')}, TP {decision.get('take_profit')})"
                )
                from services.notifier import broadcast_signal
                broadcast_signal(signal, msg)
            finally:
                db.close()

            lot_size = risk_lot_size(balance, risk_pct, decision["entry"], decision["stop_loss"], symbol)
            trade = open_trade(
                user_id=user_id,
                account_id=account_id,
                symbol=symbol,
                side=trade_side,
                entry_price=decision["entry"],
                stop_loss=decision["stop_loss"],
                take_profit=decision["take_profit"],
                lot_size=lot_size,
                confidence=decision["confidence"],
            )
            yield (
                f"data: [TRADE] Opened trade {trade.id}: {decision['action']} {lot_size} lots, "
                f"SL {decision['stop_loss']}, TP {decision['take_profit']} (RR {decision['risk_reward']})\n\n"
            )
            yield f"data: [PREDICT] Prediction process completed.\n\n"

        except Exception as e:
            increment_quota(user_id)
            log.exception("predict stream failed for %s", symbol)
            yield f"data: [ERROR] Exception occurred: {e}\n\n"

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
