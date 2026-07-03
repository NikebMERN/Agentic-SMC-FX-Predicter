# utils/security.py
import jwt # type: ignore
import datetime
import secrets
from werkzeug.security import generate_password_hash, check_password_hash # type: ignore
import os
from dotenv import load_dotenv # type: ignore

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
_WEAK_SECRET_KEYS = {
    "",
    "change_me_to_a_long_random_string",
    "change_me",
    "secret",
    "dev",
    "test",
}
if not SECRET_KEY or SECRET_KEY.strip().lower() in _WEAK_SECRET_KEYS:
    raise RuntimeError(
        "SECRET_KEY is missing or uses a known placeholder. Add a long random "
        "string to your .env (e.g. python -c \"import secrets; print(secrets.token_hex(32))\")."
    )

ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))


def is_weak_password(password: str) -> bool:
    weak = {"12345678", "password", "admin", "admin123", "1234567890"}
    return len(password or "") < 10 or (password or "").lower() in weak


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def check_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


def generate_token(user_id: int):
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def generate_refresh_token(user_id: int) -> str:
    """Create and persist a refresh token; returns the raw token."""
    from db.models import RefreshToken
    from db.session import SessionLocal

    raw = secrets.token_urlsafe(48)
    db = SessionLocal()
    try:
        db.add(RefreshToken(
            user_id=user_id,
            token_hash=hash_password(raw),
            expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=REFRESH_TOKEN_DAYS),
        ))
        db.commit()
    finally:
        db.close()
    return raw


def revoke_refresh_tokens(user_id: int):
    from db.models import RefreshToken
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        db.query(RefreshToken).filter(RefreshToken.user_id == user_id).update(
            {RefreshToken.revoked: True}, synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def exchange_refresh_token(raw_token: str) -> dict | None:
    from db.models import RefreshToken, User
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        rows = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > datetime.datetime.utcnow(),
            )
            .all()
        )
        match = None
        for row in rows:
            if check_password(raw_token, row.token_hash):
                match = row
                break
        if not match:
            return None
        user = db.query(User).filter(User.id == match.user_id).first()
        if not user or not user.is_active or getattr(user, "status", "active") != "active":
            return None
        return {
            "access_token": generate_token(user.id),
            "refresh_token": generate_refresh_token(user.id),
            "user_id": user.id,
        }
    finally:
        db.close()

from functools import wraps
from flask import request, jsonify # type: ignore


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("user_id")
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(user_id, *args, **kwargs)

    return decorated


def approved_user_required(f):
    """Require valid JWT and admin-approved account (quota not checked)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("user_id")
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        from db.models import User
        from db.session import SessionLocal

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
        finally:
            db.close()

        if not user:
            return jsonify({"error": "User not found"}), 404
        status = getattr(user, "status", "active" if user.is_active else "pending")
        if status == "pending":
            return jsonify({
                "error": "Account pending admin approval.",
                "status": "pending",
            }), 403
        if status == "banned" or not user.is_active:
            return jsonify({"error": "Account suspended.", "status": "banned"}), 403

        return f(user_id, *args, **kwargs)

    return decorated


def prediction_access_required(f):
    """Require approved user with remaining signal quota."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("user_id")
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        from services.user_access import get_user, can_use_predictions

        user = get_user(user_id)
        ok, msg = can_use_predictions(user)
        if not ok:
            status = getattr(user, "status", None) if user else None
            code = 429 if user and status == "active" and user.signals_remaining <= 0 else 403
            return jsonify({"error": msg, "status": status}), code

        return f(user_id, *args, **kwargs)

    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("user_id")
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        from db.session import SessionLocal
        from db.models import User
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user or getattr(user, "role", "user") != "admin":
                return jsonify({"error": "Admin access required"}), 403
            if not getattr(user, "is_active", True):
                return jsonify({"error": "Account disabled"}), 403
        finally:
            db.close()

        return f(user_id, *args, **kwargs)

    return decorated
