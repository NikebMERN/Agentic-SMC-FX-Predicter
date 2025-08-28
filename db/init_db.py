# db/init_db.py

from db.session import Base, engine
from db import models

def init_db():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Done.")

if __name__ == "__main__":
    init_db()
