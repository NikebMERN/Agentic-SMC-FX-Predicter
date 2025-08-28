
from flask import Flask, request, jsonify
from db.session import SessionLocal
from db.models import User
from utils.security import hash_password, verify_password

app = Flask(__name__)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/register")
def register():
    data = request.get_json(force=True)
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    if not all([username, email, password]):
        return jsonify({"error": "username, email, password required"}), 400

    db = SessionLocal()
    try:
        if db.query(User).filter((User.email == email) | (User.username == username)).first():
            return jsonify({"error": "user exists"}), 409
        user = User(username=username, email=email, password_hash=hash_password(password))
        db.add(user)
        db.commit()
        return jsonify({"ok": True, "user_id": user.id})
    finally:
        db.close()

@app.post("/login")
def login():
    data = request.get_json(force=True)
    email = data.get("email")
    password = data.get("password")
    if not all([email, password]):
        return jsonify({"error": "email, password required"}), 400

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or not verify_password(password, user.password_hash):
            return jsonify({"error": "invalid credentials"}), 401
        # TODO: issue JWT/session
        return jsonify({"ok": True, "user_id": user.id, "username": user.username})
    finally:
        db.close()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
