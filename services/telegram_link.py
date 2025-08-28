# services/telegram_link.py

from db.session import SessionLocal
from db.models import User

def link_telegram(username: str, telegram_id: str):
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            return {"error": "User not found"}
        
        user.telegram_id = telegram_id
        session.commit()
        return {"success": f"Telegram linked for {username}"}
    except Exception as e:
        session.rollback()
        return {"error": str(e)}
    finally:
        session.close()


def unlink_telegram(username: str):
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            return {"error": "User not found"}
        
        user.telegram_id = None
        session.commit()
        return {"success": f"Telegram unlinked for {username}"}
    except Exception as e:
        session.rollback()
        return {"error": str(e)}
    finally:
        session.close()
