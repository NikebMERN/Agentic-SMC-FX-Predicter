# services/user_service.py
from db.session import SessionLocal
from db.models import User
from utils.security import hash_password, check_password, generate_token
from sqlalchemy.exc import IntegrityError
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def register_user(username: str, email: str, password: str):
    db = SessionLocal()
    try:
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password)
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        return None  # username/email already exists
    finally:
        db.close()

def login_user(email: str, password: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return None
        if not check_password(password, user.password_hash):
            return None
        # generate JWT token
        token = generate_token(user.id)
        return {"user": user, "token": token}
    finally:
        db.close()

def get_user_by_id(user_id: int):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()
