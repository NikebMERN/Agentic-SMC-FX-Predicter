# app.py
from flask import Flask, request, jsonify # type: ignore
from flask_cors import CORS # type: ignore
import os
import pandas as pd # type: ignore
from predict.predict_direction import predict_market_direction
from utils.security import generate_token, token_required
from services.user_service import register_user, login_user
from services.account_service import create_account, get_account_by_id, set_default_account, update_balance, delete_account
from services.trade_service import open_trade, get_trades, close_trade, pip_value_per_lot
from services.signal_service import create_signal, get_signals
from services.agent_loop import agent_loop
from db.models import Account, Trade, Signal
from db.session import SessionLocal, get_db
import threading

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
def run_agent_in_thread(user_id: int, account_id: int, chat_id: str, symbol: str):
    """Run agent loop in a separate thread with symbol selection."""
    thread = threading.Thread(target=agent_loop, args=(user_id, account_id, chat_id, symbol), daemon=True)
    thread.start()
    return thread

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
    db = SessionLocal()
    try:
        trades = db.query(Trade).filter_by(user_id=user_id).all()
        return jsonify({"user_id": user_id, "trades": [serialize(t) for t in trades]})
    finally:
        db.close()

# ---------------- SIGNAL ROUTES ----------------
@app.route("/signals", methods=["GET"])
@token_required
def list_signals(user_id):
    db = SessionLocal()
    try:
        signals = db.query(Signal).filter_by(user_id=user_id).all()
        return jsonify({"user_id": user_id, "signals": [serialize(s) for s in signals]})
    finally:
        db.close()

# ---------------- AGENT LOOP ----------------
def run_agent_in_thread(user_id, account_id, chat_id, symbol):
    # Example placeholder for your threaded agent logic
    Thread(target=lambda: print(f"Running agent for {user_id}, {account_id}, {symbol}")).start() # type: ignore

@app.route("/agent/start", methods=["POST"])
@token_required
def start_agent(user_id):
    data = request.get_json()
    account_id, chat_id, symbol = data.get("account_id"), data.get("chat_id"), data.get("symbol")
    db = SessionLocal()
    try:
        account = db.query(Account).filter_by(user_id=user_id, id=account_id).first()
        if not account:
            return jsonify({"error": "Account not found"}), 404
        run_agent_in_thread(user_id, account_id, chat_id, symbol)
        return jsonify({"message": f"Agent loop started for account {account_id}, symbol {symbol}"})
    finally:
        db.close()

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
def predict(user_id, account_id):
    data = request.get_json()
    filename = data.get("filename")

    if not filename:
        return jsonify({"error": "Filename is required."}), 400

    filepath = os.path.join(DATA_FOLDER, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": f"File '{filename}' not found."}), 404

    # Extract symbol from filename: "EURUSD_5min.csv" -> "EURUSD"
    symbol = filename.split("_")[0].upper()

    results = predict_market_direction(filepath)
    response = []

    db = next(get_db())
    try:
        # Fetch account using helper
        acct = get_account_by_id(user_id, account_id)
        if not acct:
            return jsonify({"error": "Account not found or unauthorized."}), 404

        balance = acct.balance or 1000  # fallback
        risk_pct = acct.base_risk_pct or 0.01  # default 1%

        # Standard pip value per 1 lot in USD for major pairs
        standard_pip_value = 10  

        for label, confidence_scores in results:
            action = decide_action(confidence_scores).capitalize()
            if action not in ("Buy", "Sell"):
                continue  # skip invalid predictions

            # Calculate TP/SL
            tp, sl = calculate_tp_sl(filepath, action)
            if tp is None or sl is None:
                continue

            # Lot size calculation (simplified)
            lot_size = round((balance * risk_pct) / standard_pip_value, 2)
            lot_size = max(0.01, lot_size)  # minimum lot size

            # Entry price = last close from CSV
            entry_price = pd.read_csv(filepath)["Close"].iloc[-1]

            # Create signal
            signal = create_signal(
                user_id=user_id,
                # account_id=account_id,
                symbol=symbol,
                timeframe="1H",
                side=action,
                confidence=max(confidence_scores.values()),
                entry_price=entry_price,
                db=db
            )

            # Create trade
            trade = open_trade(
                user_id=user_id,
                account_id=account_id,
                symbol=symbol,
                side=action,
                entry_price=entry_price,
                stop_loss=sl,
                take_profit=tp,
                lot_size=lot_size,
                confidence=max(confidence_scores.values()),
                # db=db
            )

            response.append({
                "prediction": label,
                "confidence": {k: round(v*100, 2) for k, v in confidence_scores.items()},
                "action": action,
                "take_profit": tp,
                "stop_loss": sl,
                "lot_size": lot_size,
                "signal_id": signal.id,
                "trade_id": trade.id
            })

        return jsonify({
            "user_id": user_id,
            "account_id": account_id,
            "results": response
        })

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
