# services/trade_service.py
from db.session import SessionLocal
from db.models import Trade, Account
from datetime import datetime
from services.agent_loop import fetch_single_symbol

OUTCOME_WIN = 10
OUTCOME_LOSS = -5
OUTCOME_NEUTRAL = 0

# ✅ FIXED: accept entry_price explicitly
def pip_value_per_lot(symbol: str) -> float:
    pip_size = 0.01 if symbol.upper().endswith("JPY") else 0.0001
    return 100_000 * pip_size  # simplified pip value per lot

def open_trade(user_id: int, account_id: int, symbol: str, side: str, entry_price: float,
               stop_loss: float, take_profit: float | None, lot_size: float, confidence: float):
    db = SessionLocal()
    try:
        trade = Trade(
            user_id=user_id,
            account_id=account_id,
            symbol=symbol,
            side=side.upper(),
            status='OPEN',
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            lot_size=lot_size,
            confidence=confidence
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        return trade
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def close_trade(trade_id: int, manual_close: bool = False):
    """
    Close a trade based on latest market data or user manual action.
    Scenarios:
    1. TP hit -> WIN
    2. SL hit -> LOSS
    3. Manual close -> calculate based on current price
    """
    db = SessionLocal()
    try:
        trade = db.query(Trade).filter(Trade.id == trade_id).first()
        if not trade:
            return None

        # Fetch latest market price for the symbol
        latest_price = fetch_single_symbol(trade.symbol)
        if latest_price is None:
            latest_price = trade.entry_price  # fallback to entry price

        # Determine exit price based on scenario
        exit_price = None
        if not manual_close:
            # Check TP
            if trade.tp and (
                (trade.side.upper() == "BUY" and latest_price >= trade.tp) or
                (trade.side.upper() == "SELL" and latest_price <= trade.tp)
            ):
                exit_price = trade.tp
            # Check SL
            elif trade.sl and (
                (trade.side.upper() == "BUY" and latest_price <= trade.sl) or
                (trade.side.upper() == "SELL" and latest_price >= trade.sl)
            ):
                exit_price = trade.sl

        # Manual close or no TP/SL hit yet
        if exit_price is None:
            exit_price = latest_price

        # Calculate PnL
        pip_size = 0.01 if trade.symbol.upper().endswith("JPY") else 0.0001
        pip_val = pip_value_per_lot(trade.symbol)
        if trade.side.upper() == "BUY":
            pips = (exit_price - trade.entry_price) / pip_size
        else:
            pips = (trade.entry_price - exit_price) / pip_size
        pnl = pips * pip_val * trade.lot_size

        # Update trade
        trade.closed_at = datetime.utcnow()
        trade.status = "CLOSED"
        trade.pnl = round(pnl, 4)
        if pnl > 0:
            trade.outcome_score = OUTCOME_WIN
        elif pnl < 0:
            trade.outcome_score = OUTCOME_LOSS
        else:
            trade.outcome_score = OUTCOME_NEUTRAL

        # Update account balance
        acct = db.query(Account).filter(Account.id == trade.account_id).first()
        if acct:
            acct.balance = (acct.balance or 0) + pnl

        db.commit()
        db.refresh(trade)
        return trade

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def get_trades(user_id: int):
    """Return list of trades for a user (optionally filter by account)."""
    db = SessionLocal()
    try:
        trades = db.query(Trade).filter_by(user_id=user_id).all()
        return trades
    finally:
        db.close()

def get_trade_by_id(trade_id: int):
    db = SessionLocal()
    try:
        trade = db.query(Trade).filter(Trade.id == trade_id).first()
        return trade
    finally:
        db.close()