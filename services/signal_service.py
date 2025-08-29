# services/signal_service.py
from db.models import Signal
from datetime import datetime
from services.account_service import get_account_by_id

# ---------------- CREATE SIGNAL ----------------
def create_signal(
    user_id: int,
    # account_id: int,
    symbol: str,
    timeframe: str,
    side: str,
    confidence: float,
    entry_price: float,
    stop_pips: float = 10,
    db=None
):
    """
    Create a signal linked to an account.
    
    Args:
        user_id (int): ID of the user.
        account_id (int): ID of the account.
        symbol (str): Trading pair (e.g., 'EURUSD').
        timeframe (str): Timeframe (e.g., '1H').
        side (str): Trade direction ('BUY' or 'SELL').
        confidence (float): Model confidence score.
        entry_price (float): Market entry price.
        stop_pips (float, optional): Stop loss in pips. Default is 10.
        db: SQLAlchemy session.
    """

    signal = Signal(
        user_id=user_id,
        # account_id=account_id,
        symbol=symbol.upper(),
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


# ---------------- GET SIGNALS ----------------
def get_signals(user_id: int, account_id: int | None = None, db=None):
    """
    Return list of signals for a user (optionally filter by account).
    
    Args:
        user_id (int): ID of the user.
        account_id (int, optional): Filter by account ID.
        db: SQLAlchemy session.
    
    Returns:
        list[Signal]: List of signals.
    """
    query = db.query(Signal).filter(Signal.user_id == user_id)
    if account_id:
        query = query.filter(Signal.account_id == account_id)
    return query.all()
