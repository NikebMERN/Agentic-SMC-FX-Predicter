
from utils.orm_config import get_env
from db.session import engine, SessionLocal
from db.models import Base, User
from utils.security import hash_password

def create_tables():
    Base.metadata.create_all(bind=engine)

def seed_admin():
    email = get_env('ADMIN_EMAIL')
    password = get_env('ADMIN_PASSWORD')
    username = get_env('ADMIN_USERNAME') or 'admin'
    if not email or not password:
        return

    db = SessionLocal()
    try:
        exists = db.query(User).filter(User.email == email).first()
        if not exists:
            user = User(
                username=username,
                email=email,
                password_hash=hash_password(password)
            )
            db.add(user)
            db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    create_tables()
    seed_admin()
    print("Tables created. Admin seeded (if provided).")
