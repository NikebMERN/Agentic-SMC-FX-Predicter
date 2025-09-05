# app.py
from flask import Flask, request, jsonify, Response # type: ignore
from flask_cors import CORS # type: ignore
import os
import pandas as pd # type: ignore
from predict.predict_direction import predict_market_direction
from utils.security import generate_token, token_required
from services.user_service import register_user, login_user
from services.account_service import create_account, get_account_by_id, set_default_account, update_balance, delete_account
from services.trade_service import open_trade, get_trades, close_trade, get_trade_by_id
from services.signal_service import create_signal, get_signals
from services.agent_loop import fetch_single_symbol
from db.models import Account
from db.session import SessionLocal, get_db
# import threading

app = Flask(__name__)
CORS(app)

DATA_FOLDER = "data"

# ---------------- UTILS ----------------
def decide_action(confidence_scores):
    """Determine trading action based on model's confidence scores."""
    if not confidence_scores:
        return "Don't Enter"
    top_label, _ = max(confidence_scores.items(), key=lambda x: x[1])
    label = top_label.lower()
    if label in ["strong uptrend", "buy"]:
        return "Buy"
    elif label in ["strong downtrend", "sell"]:
        return "Sell"
    else:
        return "Don't Enter"

def calculate_tp_sl(csv_file_path, action, sl_pips=10, risk_reward_ratio=2):
    """Calculate TP and SL prices based on last close price in CSV."""
    df = pd.read_csv(csv_file_path)
    if df.empty or "Close" not in df.columns:
        raise ValueError("CSV file is empty or missing 'Close' column.")

    last_close = float(df["Close"].iloc[-1])

    # Extract symbol from filename: e.g., "EURUSD_5min.csv" -> "EURUSD"
    import os
    filename = os.path.basename(csv_file_path)
    symbol = filename.split("_")[0].upper()

    pip_size = 0.01 if symbol.endswith("JPY") else 0.0001
    tp_pips = sl_pips * risk_reward_ratio

    if action.lower() == "buy":
        sl = last_close - (sl_pips * pip_size)
        tp = last_close + (tp_pips * pip_size)
    elif action.lower() == "sell":
        sl = last_close + (sl_pips * pip_size)
        tp = last_close - (tp_pips * pip_size)
    else:
        raise ValueError("Action must be 'Buy' or 'Sell'.")

    return round(tp, 5), round(sl, 5)
# def run_agent_in_thread(user_id: int, account_id: int, chat_id: str, symbol: str):
#     """Run agent loop in a separate thread with symbol selection."""
#     thread = threading.Thread(target=agent_loop, args=(user_id, account_id, chat_id, symbol), daemon=True)
#     thread.start()
#     return thread

def serialize(obj):
    """Convert SQLAlchemy model instance into dict."""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

# ---------------- AUTH ROUTES ----------------
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username, email, password = data.get("username"), data.get("email"), data.get("password")
    if not username or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    user = register_user(username=username, email=email, password=password)
    if not user:
        return jsonify({"error": "Username or email already exists"}), 400
    token = generate_token(user.id)
    return jsonify({"message": "User registered", "token": token, "user_id": user.id})

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email, password = data.get("email"), data.get("password")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    result = login_user(email=email, password=password)
    if not result:
        return jsonify({"error": "Invalid credentials"}), 401
    return jsonify({"message": "Login successful", "token": result["token"], "user_id": result["user"].id})

# ---------------- ACCOUNT ROUTES ----------------
@app.route("/accounts/create", methods=["POST"])
@token_required
def create_new_account(user_id):
    data = request.get_json()
    name = data.get("name")
    balance = data.get("balance", 0)
    risk_pct = data.get("risk_pct", 0.01)
    leverage = data.get("leverage", 100)

    account = create_account(user_id, name, balance, risk_pct, leverage)

    # If account is a SQLAlchemy object, jsonify only fields
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
@token_required
def list_accounts(user_id):
    db = SessionLocal()
    try:
        accounts = db.query(Account).filter_by(user_id=user_id).all()
        return jsonify({"user_id": user_id, "accounts": [serialize(a) for a in accounts]})
    finally:
        db.close()

@app.route("/accounts/<int:account_id>", methods=["GET"])
@token_required
def get_account(user_id, account_id):
    account = get_account_by_id(user_id, account_id)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(serialize(account))

@app.route("/accounts/set_default/<int:account_id>", methods=["PUT"])
@token_required
def set_default(user_id, account_id):
    account = set_default_account(user_id, account_id)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    return jsonify({"message": f"Account {account_id} set as default"})

@app.route("/accounts/update_balance/<int:account_id>", methods=["PUT"])
@token_required
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
@token_required
def delete_account_route(user_id, account_id):
    success = delete_account(account_id)
    if not success:
        return jsonify({"error": "Account not found or could not be deleted"}), 404
    return jsonify({"message": f"Account {account_id} deleted"})

# ---------------- TRADE ROUTES ----------------
@app.route("/trades", methods=["GET"])
@token_required
def list_trades(user_id):
    trades = get_trades(user_id)
    return jsonify({"user_id": user_id, "trades": [serialize(t) for t in trades]})

@app.route("/close-trade/<int:trade_id>", methods=["POST"])
# @token_required
def close_trade_route(trade_id):
    """
    Close a trade by ID. Determines if TP/SL was hit automatically or user closed manually.
    Expects optional JSON body: { "manual_close": true } to force manual close
    """
    data = request.get_json(silent=True) or {}
    manual_close = data.get("manual_close", False)

    try:
        trade = close_trade(trade_id, manual_close=manual_close)
        if not trade:
            return jsonify({"error": "Trade not found"}), 404

        # Determine scenario for response
        scenario = "Manual Close" if manual_close else "TP/SL Hit"
        if not manual_close:
            if trade.side.upper() == "BUY":
                if trade.pnl > 0 and trade.closed_at:
                    scenario = "Take Profit Hit"
                elif trade.pnl < 0 and trade.closed_at:
                    scenario = "Stop Loss Hit"
            else:
                if trade.pnl > 0 and trade.closed_at:
                    scenario = "Take Profit Hit"
                elif trade.pnl < 0 and trade.closed_at:
                    scenario = "Stop Loss Hit"

        response = {
            "trade_id": trade.id,
            "symbol": trade.symbol,
            "side": trade.side,
            "entry_price": trade.entry_price,
            "exit_price": trade.entry_price + trade.pnl / (trade.lot_size * (0.01 if trade.symbol.upper().endswith("JPY") else 0.0001)),  # approximate exit price
            "lot_size": trade.lot_size,
            "pnl": trade.pnl,
            "outcome_score": trade.outcome_score,
            "scenario": scenario,
            "closed_at": trade.closed_at.isoformat()
        }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- SIGNAL ROUTES ----------------
@app.route("/signals", methods=["GET"])
@token_required
def list_signals(user_id):
    db = SessionLocal()
    signals = get_signals(user_id, db)
    return jsonify({"user_id": user_id, "signals": [serialize(s) for s in signals]})

# ---------------- AGENT LOOP ----------------
# def run_agent_in_thread(user_id, account_id, chat_id, symbol):
#     # Example placeholder for your threaded agent logic
#     Thread(target=lambda: print(f"Running agent for {user_id}, {account_id}, {symbol}")).start() # type: ignore

# @app.route("/agent/start", methods=["POST"])
# @token_required
# def start_agent(user_id):
#     data = request.get_json()
#     account_id, chat_id, symbol = data.get("account_id"), data.get("chat_id"), data.get("symbol")
#     db = SessionLocal()
#     try:
#         account = db.query(Account).filter_by(user_id=user_id, id=account_id).first()
#         if not account:
#             return jsonify({"error": "Account not found"}), 404
#         run_agent_in_thread(user_id, account_id, chat_id, symbol)
#         return jsonify({"message": f"Agent loop started for account {account_id}, symbol {symbol}"})
#     finally:
#         db.close()

# ---------------- PREDICTION ROUTES ----------------
@app.route("/")
def index():
    return jsonify({
        "message": "Welcome to the SMC Forex Predictor API.",
        "endpoints": {
            "GET /data": "List available data files",
            "POST /predict": "Send filename to get market prediction (choose different currencies)"
        }
    })

@app.route("/data", methods=["GET"])
@token_required
def list_data_files(user_id):
    try:
        files = [f for f in os.listdir(DATA_FOLDER) if f.endswith(".csv")]
        return jsonify({"available_files": files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/predict/<int:account_id>", methods=["POST"])
@token_required
def predict_stream(user_id, account_id):
    def event_stream():
        data = request.get_json()
        filename = data.get("filename")
        if not filename:
            yield "data: [ERROR] Filename is required.\n\n"
            return

        symbol = filename.split("_")[0].upper()
        yield f"data: [PREDICT] Starting prediction for {symbol}\n\n"

        # Step 1: Fetch latest data and retrain model
        yield f"data: [FETCH] Fetching latest data and retraining model for {symbol}...\n\n"
        fetch_single_symbol(symbol)
        yield f"data: [FETCH] Completed fetching and model retraining.\n\n"

        filepath = os.path.join(DATA_FOLDER, filename)
        if not os.path.exists(filepath):
            yield f"data: [ERROR] File '{filename}' not found after fetching.\n\n"
            return

        results = predict_market_direction(filepath)

        db = next(get_db())
        try:
            acct = get_account_by_id(user_id, account_id)
            if not acct:
                yield f"data: [ERROR] Account not found or unauthorized.\n\n"
                return

            balance = acct.balance or 1000
            risk_pct = acct.base_risk_pct or 0.01
            standard_pip_value = 10

            for label, confidence_scores in results:
                action = decide_action(confidence_scores).capitalize()
                if action not in ("Buy", "Sell"):
                    continue

                lot_size = round((balance * risk_pct) / standard_pip_value, 2)
                lot_size = max(0.01, lot_size)
                entry_price = pd.read_csv(filepath)["Close"].iloc[-1]

                signal = create_signal(
                    user_id=user_id,
                    account_id=account_id,
                    symbol=symbol,
                    timeframe="1H",
                    side=action,
                    confidence=max(confidence_scores.values()),
                    entry_price=entry_price,
                    db=db
                )
                yield f"data: [SIGNAL] Created signal {signal.id} for action {action}\n\n"

                trade = open_trade(
                    user_id=user_id,
                    account_id=account_id,
                    symbol=symbol,
                    side=action,
                    entry_price=entry_price,
                    stop_loss=None,
                    take_profit=None,
                    lot_size=lot_size,
                    confidence=max(confidence_scores.values()),
                    db=db
                )
                yield f"data: [TRADE] Opened trade {trade.id} for action {action}\n\n"

            yield f"data: [PREDICT] Prediction process completed.\n\n"

        except Exception as e:
            db.rollback()
            yield f"data: [ERROR] Exception occurred: {e}\n\n"
        finally:
            db.close()

    return Response(event_stream(), mimetype="text/event-stream")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
