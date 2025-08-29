# services/signal_service.py
from db.session import SessionLocal
from db.models import Signal
from datetime import datetime

def create_signal(user_id: int, symbol: str, timeframe: str, side: str,
                confidence: float, entry_price: float = 0, stop_pips: float = 10):
    db = SessionLocal()
    try:
        signal = Signal(
            user_id=user_id,
            symbol=symbol,
            timeframe=timeframe,
            side=side.upper(),
            confidence=confidence,
            entry_price=entry_price,
            stop_pips=stop_pips,
            created_at=datetime.utcnow()
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# ---------------- NEW FUNCTION ----------------
def get_signals(user_id: int, account_id: int | None = None):
    """Return list of signals for a user (optionally filter by account)."""
    db = SessionLocal()
    try:
        query = db.query(Signal).filter(Signal.user_id == user_id)
        if account_id is not None:
            query = query.filter(Signal.account_id == account_id)
        return query.all()
    finally:
        db.close()
