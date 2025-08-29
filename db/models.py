# db/models.py
from __future__ import annotations
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Enum, ForeignKey, Boolean, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from db.session import Base 
# from session import Base # Use this code when you create the tables

TradeStatus = Enum('OPEN', 'CLOSED', 'SKIPPED', name='trade_status')

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    telegram = relationship("TelegramLink", back_populates="user", uselist=False)
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")

class TelegramLink(Base):
    __tablename__ = 'telegram_links'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    chat_id = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="telegram")

class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    balance = Column(Float, default=0.0)
    base_risk_pct = Column(Float, default=0.01)  # e.g., 0.01 == 1%
    leverage = Column(Integer, default=100)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="accounts")
    trades = relationship("Trade", back_populates="account", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint('user_id', 'name', name='uq_user_account_name'),)

class Signal(Base):
    __tablename__ = 'signals'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    symbol = Column(String(16), index=True, nullable=False)
    timeframe = Column(String(8), default='1h')
    side = Column(String(8))  # BUY/SELL/SKIP
    confidence = Column(Float, default=0.0)
    entry_price = Column(Float)
    stop_pips = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index('ix_signals_symbol_time', 'symbol', 'timeframe', 'created_at'),)

class Trade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)

    symbol = Column(String(16), index=True, nullable=False)
    side = Column(String(4), nullable=False)  # 'BUY' or 'SELL'
    status = Column(TradeStatus, default='CLOSED', index=True)

    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=True)

    lot_size = Column(Float, nullable=False)
    confidence = Column(Float, default=0.0)

    opened_at = Column(DateTime, default=datetime.utcnow, index=True)
    closed_at = Column(DateTime, nullable=True)
    pnl = Column(Float, nullable=True)  # in account currency (assume USD)
    outcome_score = Column(Integer, nullable=True)  # +10, -5, 0

    account = relationship("Account", back_populates="trades")

    __table_args__ = (Index('ix_trades_user_symbol_time', 'user_id', 'symbol', 'opened_at'),)

class EquitySnapshot(Base):
    __tablename__ = 'equity_snapshots'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    balance = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
