# security.py
import os
import jwt
import datetime
from flask import request, jsonify
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

# Secret key for JWT
SECRET_KEY = os.getenv("SECRET_KEY", "default_secret_key")


def generate_token(user_id, expires_in=3600):
    """Generate JWT token for a user"""
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in),
        "iat": datetime.datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_token(token):
    """Verify and decode JWT token"""
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return decoded
    except jwt.ExpiredSignatureError:
        return None  # expired
    except jwt.InvalidTokenError:
        return None  # invalid


def token_required(f):
    """Decorator to protect routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            token = request.headers["Authorization"].split(" ")[1]  # Bearer <token>
        
        if not token:
            return jsonify({"error": "Token is missing!"}), 401

        decoded = verify_token(token)
        if not decoded:
            return jsonify({"error": "Invalid or expired token!"}), 401

        return f(decoded["user_id"], *args, **kwargs)
    return decorated
