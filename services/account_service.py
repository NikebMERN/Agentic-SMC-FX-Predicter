# services/account_service.py
from db.session import SessionLocal
from db.models import Account

def create_account(user_id: int, name: str, balance: float = 0.0, base_risk_pct: float = 0.01, leverage: int = 100):
    db: Session = SessionLocal()
    try:
        # Ensure unique account name for this user
        original_name = name
        i = 1
        while db.query(Account).filter_by(user_id=user_id, name=name).first():
            i += 1
            name = f"{original_name} {i}"

        acct = Account(
            user_id=user_id,
            name=name,
            balance=balance,
            base_risk_pct=base_risk_pct,
            leverage=leverage
        )
        db.add(acct)
        db.commit()
        db.refresh(acct)
        return acct
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def get_account_by_id(user_id: int, account_id: int):
    """Return a single account for a user by account_id."""
    db = SessionLocal()
    try:
        return db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).first()
    finally:
        db.close()

def get_accounts(user_id: int):
    """Return all accounts for a given user."""
    db = SessionLocal()
    try:
        return db.query(Account).filter(Account.user_id == user_id).all()
    finally:
        db.close()

def set_default_account(user_id: int, account_id: int):
    db = SessionLocal()
    try:
        # unset others
        db.query(Account).filter(Account.user_id == user_id).update({Account.is_default: False})
        # set chosen
        acct = db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).first()
        if not acct:
            return None
        acct.is_default = True
        db.commit()
        return acct
    finally:
        db.close()

def update_balance(account_id: int, new_balance: float):
    db = SessionLocal()
    try:
        acct = db.query(Account).filter(Account.id == account_id).first()
        if not acct:
            return None
        acct.balance = new_balance
        db.commit()
        return acct
    finally:
        db.close()

def delete_account(account_id: int):
    db = SessionLocal()
    try:
        acct = db.query(Account).filter(Account.id == account_id).first()
        if not acct:
            return False
        db.delete(acct)
        db.commit()
        return True
    finally:
        db.close()
