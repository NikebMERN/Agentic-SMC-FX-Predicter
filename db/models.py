# db/models.py

from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from db.session import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    telegram_id = Column(String(50), unique=True, nullable=True)

    accounts = relationship("Account", back_populates="owner")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    balance = Column(Float, default=0.0)
    leverage = Column(Integer, default=100)

    owner = relationship("User", back_populates="accounts")
    trades = relationship("Trade", back_populates="account")


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    symbol = Column(String(20))
    entry_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    risk = Column(Float)  # percentage risked
    lot_size = Column(Float)
    created_at = Column(DateTime, default=func.now())

    account = relationship("Account", back_populates="trades")
