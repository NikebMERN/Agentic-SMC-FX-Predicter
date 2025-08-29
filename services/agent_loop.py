# services/agent_loop.py
import os
import time
from datetime import datetime
from services.notifier import send_message
from services.trade_service import open_trade
from services.signal_service import create_signal
from services.risk import calculate_lot_size
from predict.predict_direction import predict_market_direction
from utils.config import DATA_FOLDER

DEFAULT_RISK_PCT = 0.01  # fallback if account not specified

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
    """Calculate TP and SL in pips based on last close price."""
    import pandas as pd # type: ignore

    df = pd.read_csv(csv_file_path)
    if df.empty or "Close" not in df.columns:
        return None, None

    last_close = df["Close"].iloc[-1]
    pip_size = 0.01 if "JPY" in csv_file_path.upper() else 0.0001
    tp_pips = sl_pips * risk_reward_ratio

    if action == "Buy":
        sl = last_close - (sl_pips * pip_size)
        tp = last_close + (tp_pips * pip_size)
    elif action == "Sell":
        sl = last_close + (sl_pips * pip_size)
        tp = last_close - (tp_pips * pip_size)
    else:
        return None, None

    return round(tp, 5), round(sl, 5)

# ---------------- AGENT LOOP ----------------
def agent_loop(user_id: int, account_id: int, chat_id: str, symbol: str = "NZDUSD", interval_sec: int = 3600):
    """
    Core agent loop:
    1. Fetch latest market data (CSV based on symbol).
    2. Run SMC predictor.
    3. Decide Buy/Sell/Skip.
    4. Calculate lot size based on account & risk.
    5. Open trade & save signal.
    6. Notify user via Telegram.
    """
    print(f"[AgentLoop] Started at {datetime.utcnow()} for user {user_id}, symbol {symbol}")

    while True:
        try:
            # Build CSV path dynamically
            file_name = f"{symbol}_60min.csv"  # assuming folder structure DATA_FOLDER/SYMBOL_60min.csv
            file_path = os.path.join(DATA_FOLDER, file_name)

            if not os.path.exists(file_path):
                print(f"[AgentLoop] CSV not found for {symbol}: {file_path}")
                time.sleep(interval_sec)
                continue

            # Run prediction
            predictions = predict_market_direction(file_path)

            for label, conf_scores in predictions:
                action = decide_action(conf_scores)
                confidence = max(conf_scores.values()) if conf_scores else 0

                # Calculate TP/SL
                tp, sl = calculate_tp_sl(file_path, action)

                # Save signal
                signal = create_signal(
                    user_id=user_id,
                    symbol=symbol,
                    timeframe="1h",
                    side=action,
                    confidence=confidence,
                    entry_price=0,  # could be last_close from CSV
                    stop_pips=10
                )

                # Calculate lot size
                lot_size = calculate_lot_size(account_id, action, risk_pct=DEFAULT_RISK_PCT)

                # Open trade if action is Buy/Sell
                if action != "Don't Enter":
                    open_trade(
                        user_id=user_id,
                        account_id=account_id,
                        symbol=symbol,
                        side=action,
                        entry_price=0,  # could be last_close
                        stop_loss=sl or 0,
                        take_profit=tp or 0,
                        lot_size=lot_size,
                        confidence=confidence
                    )

                # Notify via Telegram
                send_message(
                    chat_id,
                    f"[Signal] {action} {symbol} | Confidence: {confidence*100:.2f}% | Lot: {lot_size} | TP: {tp} | SL: {sl}"
                )

        except Exception as e:
            print(f"[AgentLoop] Error: {e}")

        # Wait for next interval
        time.sleep(interval_sec)
