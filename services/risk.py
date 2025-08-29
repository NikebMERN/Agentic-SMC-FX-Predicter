# services/risk.py
from db.session import SessionLocal
from db.models import Account

def calculate_lot_size(account_id: int, action: str, risk_pct: float = 0.01):
    """
    Simple lot calculation:
    lot_size = (account_balance * risk_pct) / standard_pip_value
    """
    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account or not account.balance:
            balance = 1000  # fallback if account missing
        else:
            balance = account.balance

        # standard pip value per 1 lot in USD for major pairs
        pip_value = 10  # you can adjust per symbol if needed

        lot_size = (balance * risk_pct) / pip_value
        return round(lot_size, 2)
    finally:
        db.close()
