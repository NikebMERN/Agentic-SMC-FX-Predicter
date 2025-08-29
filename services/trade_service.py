# services/trade_service.py
from db.session import SessionLocal
from db.models import Trade, Account
from datetime import datetime

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

def close_trade(trade_id: int, exit_price: float):
    db = SessionLocal()
    try:
        trade = db.query(Trade).filter(Trade.id == trade_id).first()
        if not trade:
            return None
        pip_size = 0.01 if trade.symbol.upper().endswith("JPY") else 0.0001
        pip_val = pip_value_per_lot(trade.symbol, entry_price=trade.entry_price)  # ✅ FIXED
        if trade.side.upper() == "BUY":
            pips = (exit_price - trade.entry_price) / pip_size
        else:
            pips = (trade.entry_price - exit_price) / pip_size
        pnl = pips * pip_val * trade.lot_size
        trade.closed_at = datetime.utcnow()
        trade.status = 'CLOSED'
        trade.pnl = round(pnl, 4)
        if pnl > 0:
            trade.outcome_score = OUTCOME_WIN
        elif pnl < 0:
            trade.outcome_score = OUTCOME_LOSS
        else:
            trade.outcome_score = OUTCOME_NEUTRAL
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

def get_trades(user_id: int, account_id: int | None = None):
    """Return list of trades for a user (optionally filter by account)."""
    db = SessionLocal()
    try:
        query = db.query(Trade).filter(Trade.user_id == user_id)
        if account_id is not None:
            query = query.filter(Trade.account_id == account_id)
        return query.all()
    finally:
        db.close()
