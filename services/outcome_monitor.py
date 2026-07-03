# services/outcome_monitor.py
"""Background job: auto-close open trades/signals when SL/TP is hit."""
import threading
import time

from db.models import Signal, Trade
from db.session import SessionLocal
from engine.data import get_latest_price
from services.prediction_review import evaluate_due_reviews
from services.feedback_reminder import send_due_feedback_reminders
from services.trade_service import OUTCOME_LOSS, OUTCOME_NEUTRAL, OUTCOME_WIN, close_trade
from utils.config import INTERVAL
from utils.logger import get_logger

log = get_logger("services.outcome_monitor")

INTERVAL_SEC = int(__import__("os").getenv("OUTCOME_MONITOR_INTERVAL_SEC", "60"))
_running = False
_thread: threading.Thread | None = None


def _check_signal(signal: Signal, price: float) -> bool:
    """Close signal if SL/TP hit. Returns True if closed."""
    if signal.status != "OPEN" or signal.side not in ("BUY", "SELL"):
        return False
    sl = signal.stop_loss
    tp = signal.take_profit
    hit = False
    outcome = None
    if signal.side == "BUY":
        if tp and price >= tp:
            hit, outcome = True, "win"
        elif sl and price <= sl:
            hit, outcome = True, "loss"
    else:
        if tp and price <= tp:
            hit, outcome = True, "win"
        elif sl and price >= sl:
            hit, outcome = True, "loss"
    if not hit:
        return False
    db = SessionLocal()
    try:
        row = db.query(Signal).filter(Signal.id == signal.id, Signal.status == "OPEN").first()
        if not row:
            return False
        from datetime import datetime
        row.status = "CLOSED"
        row.outcome = outcome
        row.closed_at = datetime.utcnow()
        db.commit()
        log.info("Signal %s closed (%s) at price %.5f", row.id, outcome, price)
        return True
    finally:
        db.close()


def run_cycle():
    db = SessionLocal()
    try:
        open_trades = db.query(Trade).filter(Trade.status == "OPEN").all()
        open_signals = db.query(Signal).filter(Signal.status == "OPEN").all()
    finally:
        db.close()

    symbols = {t.symbol for t in open_trades} | {s.symbol for s in open_signals}
    prices = {}
    for sym in symbols:
        try:
            prices[sym] = get_latest_price(sym)
        except Exception as exc:
            log.warning("Price fetch failed for %s: %s", sym, exc)

    for trade in open_trades:
        price = prices.get(trade.symbol)
        if price is None:
            continue
        tp_hit = trade.take_profit and (
            (trade.side == "BUY" and price >= trade.take_profit)
            or (trade.side == "SELL" and price <= trade.take_profit)
        )
        sl_hit = trade.stop_loss and (
            (trade.side == "BUY" and price <= trade.stop_loss)
            or (trade.side == "SELL" and price >= trade.stop_loss)
        )
        if tp_hit or sl_hit:
            closed = close_trade(trade.id, manual_close=False)
            if closed:
                log.info("Trade %s auto-closed (SL/TP)", trade.id)

    for signal in open_signals:
        price = prices.get(signal.symbol)
        if price is not None:
            _check_signal(signal, price)

    reminders = send_due_feedback_reminders()
    if reminders:
        log.info("Sent %d feedback reminder(s)", reminders)

    evaluated = evaluate_due_reviews()
    if evaluated:
        log.info("Evaluated %d prediction review(s) (2h market check)", evaluated)


def _loop():
    global _running
    while _running:
        try:
            run_cycle()
        except Exception:
            log.exception("Outcome monitor cycle failed")
        time.sleep(INTERVAL_SEC)


def start_outcome_monitor():
    global _running, _thread
    if _running:
        return
    _running = True
    _thread = threading.Thread(target=_loop, daemon=True, name="outcome-monitor")
    _thread.start()
    log.info("Outcome monitor started (interval %ss)", INTERVAL_SEC)
