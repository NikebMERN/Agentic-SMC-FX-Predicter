# utils/security.py
import jwt # type: ignore
import datetime
from werkzeug.security import generate_password_hash, check_password_hash # type: ignore
import os
from dotenv import load_dotenv # type: ignore

# Load environment variables from .env
load_dotenv()

# Secret key for JWT
SECRET_KEY = os.getenv("SECRET_KEY", "weak_secret_key")

# Hash a password
def hash_password(password: str) -> str:
    return generate_password_hash(password)

# Verify a password
def check_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)

# Generate JWT token
def generate_token(user_id: int):
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # token expiry
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return token

# Token verification decorator (Flask)
from functools import wraps
from flask import request, jsonify # type: ignore

def token_required(f):
    @wraps(f)  # ← this preserves the original function metadata
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
