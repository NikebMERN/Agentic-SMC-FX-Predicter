# db/models.py
from __future__ import annotations
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from sqlalchemy import (  # type: ignore
    Column, Integer, String, Float, DateTime, Enum, ForeignKey, Boolean, Index,
    UniqueConstraint, Text,
)
from sqlalchemy.orm import relationship  # type: ignore
from db.session import Base

TradeStatus = Enum('OPEN', 'CLOSED', 'SKIPPED', name='trade_status')
SignalStatus = Enum('OPEN', 'CLOSED', name='signal_status')


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), default='user', nullable=False)
    status = Column(String(16), default='pending', nullable=False, index=True)
    is_active = Column(Boolean, default=False, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    signals_remaining = Column(Integer, default=5, nullable=False)
    risk_disclosure_accepted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    telegram = relationship("TelegramLink", back_populates="user", uselist=False)
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")


class PairThreshold(Base):
    __tablename__ = 'pair_thresholds'
    symbol = Column(String(16), primary_key=True)
    interval = Column(String(16), primary_key=True, default='*')
    thresholds_json = Column(Text, nullable=False, default='{}')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ThresholdVersion(Base):
    __tablename__ = 'threshold_versions'
    id = Column(Integer, primary_key=True)
    version_tag = Column(String(32), unique=True, nullable=False, index=True)
    config_json = Column(Text, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False, index=True)
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    notes = Column(Text, nullable=True)


class ThresholdOverride(Base):
    __tablename__ = 'threshold_overrides'
    symbol = Column(String(16), primary_key=True, default='*')
    interval = Column(String(16), primary_key=True, default='*')
    trading_style = Column(String(16), primary_key=True, default='*')
    patch_json = Column(Text, nullable=False, default='{}')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Setting(Base):
    __tablename__ = 'settings'
    key = Column(String(64), primary_key=True)
    value = Column(String(512), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PasswordReset(Base):
    __tablename__ = 'password_resets'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    code_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TelegramLink(Base):
    __tablename__ = 'telegram_links'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    chat_id = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="telegram")


class TelegramLinkCode(Base):
    __tablename__ = 'telegram_link_codes'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    code_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    balance = Column(Float, default=0.0)
    base_risk_pct = Column(Float, default=0.01)
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
    side = Column(String(8))
    confidence = Column(Float, default=0.0)
    entry_price = Column(Float)
    stop_pips = Column(Float)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    status = Column(SignalStatus, default='OPEN', index=True)
    outcome = Column(String(16), nullable=True)
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index('ix_signals_symbol_time', 'symbol', 'timeframe', 'created_at'),)


class Trade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)

    symbol = Column(String(16), index=True, nullable=False)
    side = Column(String(4), nullable=False)
    status = Column(TradeStatus, default='CLOSED', index=True)

    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=True)

    lot_size = Column(Float, nullable=False)
    confidence = Column(Float, default=0.0)

    opened_at = Column(DateTime, default=datetime.utcnow, index=True)
    closed_at = Column(DateTime, nullable=True)
    pnl = Column(Float, nullable=True)
    outcome_score = Column(Integer, nullable=True)

    account = relationship("Account", back_populates="trades")

    __table_args__ = (Index('ix_trades_user_symbol_time', 'user_id', 'symbol', 'opened_at'),)


class FeedbackSample(Base):
    __tablename__ = 'feedback_samples'
    id = Column(Integer, primary_key=True)
    symbol = Column(String(16), index=True, nullable=False)
    interval = Column(String(16), default='60min')
    features_json = Column(Text, nullable=False)
    label = Column(String(8), nullable=False)
    signal_id = Column(Integer, ForeignKey('signals.id', ondelete='SET NULL'), nullable=True)
    trade_id = Column(Integer, ForeignKey('trades.id', ondelete='SET NULL'), nullable=True)
    used_in_training = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ModelVersion(Base):
    __tablename__ = 'model_versions'
    id = Column(Integer, primary_key=True)
    symbol = Column(String(16), index=True, nullable=False)
    interval = Column(String(16), default='60min')
    trading_style = Column(String(16), default='intraday', nullable=False)
    model_type = Column(String(16), default='RANDOM_FOREST', nullable=False)
    path = Column(String(512), nullable=False)
    calibrator_path = Column(String(512), nullable=True)
    feature_schema_version = Column(String(16), default='v1')
    threshold_version_id = Column(Integer, ForeignKey('threshold_versions.id', ondelete='SET NULL'), nullable=True)
    rule_engine_version = Column(String(32), default='v1')
    training_data_start = Column(DateTime, nullable=True)
    training_data_end = Column(DateTime, nullable=True)
    training_record_count = Column(Integer, default=0)
    walk_forward_score = Column(Float, nullable=True)
    precision = Column(Float, nullable=True)
    recall = Column(Float, nullable=True)
    f1 = Column(Float, nullable=True)
    brier_score = Column(Float, nullable=True)
    log_loss = Column(Float, nullable=True)
    win_rate = Column(Float, nullable=True)
    accepted_signal_count = Column(Integer, default=0)
    rejected_signal_count = Column(Integer, default=0)
    status = Column(String(16), default='CANDIDATE', nullable=False, index=True)
    promoted_from_version_id = Column(Integer, ForeignKey('model_versions.id', ondelete='SET NULL'), nullable=True)
    promoted_at = Column(DateTime, nullable=True)
    val_accuracy = Column(Float, default=0.0)
    samples = Column(Integer, default=0)
    is_active = Column(Boolean, default=False, nullable=False, index=True)
    metrics_json = Column(Text, nullable=True)
    trained_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index('ix_model_versions_pair', 'symbol', 'interval', 'trading_style', 'status'),)


class TrainingRun(Base):
    __tablename__ = 'training_runs'
    id = Column(Integer, primary_key=True)
    run_type = Column(String(16), default='NIGHTLY', nullable=False)
    status = Column(String(16), default='QUEUED', nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    pairs_processed = Column(Integer, default=0)
    models_created = Column(Integer, default=0)
    models_promoted = Column(Integer, default=0)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class BacktestRun(Base):
    __tablename__ = 'backtest_runs'
    id = Column(Integer, primary_key=True)
    model_version_id = Column(Integer, ForeignKey('model_versions.id', ondelete='CASCADE'), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)
    interval = Column(String(16), default='60min')
    trading_style = Column(String(16), default='intraday')
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    walk_forward_windows = Column(Integer, default=0)
    total_signals = Column(Integer, default=0)
    accepted_signals = Column(Integer, default=0)
    rejected_signals = Column(Integer, default=0)
    win_rate = Column(Float, nullable=True)
    precision = Column(Float, nullable=True)
    recall = Column(Float, nullable=True)
    f1 = Column(Float, nullable=True)
    brier_score = Column(Float, nullable=True)
    log_loss = Column(Float, nullable=True)
    max_adverse_excursion_avg = Column(Float, nullable=True)
    confidence_calibration_json = Column(Text, nullable=True)
    passed_promotion_gate = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class SignalOutcome(Base):
    __tablename__ = 'signal_outcomes'
    id = Column(Integer, primary_key=True)
    prediction_id = Column(Integer, ForeignKey('prediction_reviews.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    rule_direction = Column(String(16), nullable=False)
    tp_price = Column(Float, nullable=True)
    sl_price = Column(Float, nullable=True)
    entry_price = Column(Float, nullable=False)
    outcome = Column(String(24), nullable=False, index=True)
    max_favorable_excursion = Column(Float, nullable=True)
    max_adverse_excursion = Column(Float, nullable=True)
    meta_label = Column(Integer, nullable=True)
    verified_at = Column(DateTime, default=datetime.utcnow)

    prediction = relationship("PredictionReview", back_populates="signal_outcome")


class AlertRule(Base):
    __tablename__ = 'alert_rules'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    channel = Column(String(16), default='TELEGRAM', nullable=False)
    telegram_chat_id = Column(String(64), nullable=True)
    pairs_json = Column(Text, nullable=False, default='[]')
    min_confidence = Column(Float, default=0.6)
    allowed_directions_json = Column(Text, nullable=False, default='["BUY_BIAS","SELL_BIAS"]')
    timeframes_json = Column(Text, nullable=False, default='["60min"]')
    trading_style = Column(String(16), default='intraday')
    quiet_hours_json = Column(Text, nullable=True)
    max_alerts_per_day = Column(Integer, default=10)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlertEvent(Base):
    __tablename__ = 'alert_events'
    id = Column(Integer, primary_key=True)
    alert_rule_id = Column(Integer, ForeignKey('alert_rules.id', ondelete='CASCADE'), nullable=False, index=True)
    prediction_id = Column(Integer, ForeignKey('prediction_reviews.id', ondelete='SET NULL'), nullable=True, index=True)
    sent_at = Column(DateTime, default=datetime.utcnow, index=True)
    status = Column(String(16), default='SENT', nullable=False)
    error_message = Column(Text, nullable=True)


class ExportJob(Base):
    __tablename__ = 'export_jobs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    export_type = Column(String(8), default='CSV', nullable=False)
    scope = Column(String(32), default='predictions')
    status = Column(String(16), default='QUEUED', nullable=False, index=True)
    file_path = Column(String(512), nullable=True)
    file_url = Column(String(512), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)


class PairPerformance(Base):
    __tablename__ = 'pair_performance'
    id = Column(Integer, primary_key=True)
    symbol = Column(String(16), nullable=False, index=True)
    interval = Column(String(16), default='60min')
    trading_style = Column(String(16), default='intraday')
    model_version_id = Column(Integer, ForeignKey('model_versions.id', ondelete='SET NULL'), nullable=True)
    total_signals = Column(Integer, default=0)
    accepted_signals = Column(Integer, default=0)
    rejected_signals = Column(Integer, default=0)
    win_rate = Column(Float, nullable=True)
    precision = Column(Float, nullable=True)
    avg_confidence = Column(Float, nullable=True)
    brier_score = Column(Float, nullable=True)
    status_recommendation = Column(String(16), default='ACTIVE')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint('symbol', 'interval', 'trading_style', name='uq_pair_perf'),)


class PredictionReview(Base):
    """Prediction vs actual outcome after horizon window — admin can trigger retrain from these."""
    __tablename__ = 'prediction_reviews'
    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey('signals.id', ondelete='SET NULL'), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    symbol = Column(String(16), index=True, nullable=False)
    interval = Column(String(16), default='60min')
    horizon = Column(String(16), default='intraday')
    predicted_action = Column(String(32), nullable=False)
    direction = Column(String(16), nullable=True)
    predicted_confidence = Column(Float, default=0.0)
    entry_price = Column(Float, nullable=False)
    invalidation_price = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    scores_json = Column(Text, nullable=True)
    signals_json = Column(Text, nullable=True)
    snapshot_path = Column(String(512), nullable=True)
    model_version = Column(String(64), nullable=True)
    model_version_id = Column(Integer, ForeignKey('model_versions.id', ondelete='SET NULL'), nullable=True, index=True)
    threshold_version_id = Column(Integer, ForeignKey('threshold_versions.id', ondelete='SET NULL'), nullable=True, index=True)
    rule_engine_version = Column(String(32), default='v1')
    feature_schema_version = Column(String(16), default='v1')
    meta_ml_probability = Column(Float, nullable=True)
    confidence_before_ml = Column(Float, nullable=True)
    final_confidence = Column(Float, nullable=True)
    trading_style = Column(String(16), default='intraday')
    strategy_mode = Column(String(16), default='both')
    retry_count = Column(Integer, default=0, nullable=False)
    predicted_at = Column(DateTime, default=datetime.utcnow)
    feedback_due_at = Column(DateTime, nullable=True, index=True)
    feedback_reminder_sent = Column(Boolean, default=False, nullable=False)
    evaluate_at = Column(DateTime, nullable=False, index=True)
    actual_price = Column(Float, nullable=True)
    actual_direction = Column(String(16), nullable=True)
    was_correct = Column(Boolean, nullable=True)
    features_json = Column(Text, nullable=True)
    status = Column(String(24), default='pending', nullable=False, index=True)
    evaluated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    detected_signals = relationship("DetectedSignal", back_populates="prediction", cascade="all, delete-orphan")
    user_feedback = relationship("UserFeedback", back_populates="prediction", uselist=False, cascade="all, delete-orphan")
    market_verification = relationship("MarketVerification", back_populates="prediction", uselist=False, cascade="all, delete-orphan")
    training_record = relationship("TrainingRecord", back_populates="prediction", uselist=False, cascade="all, delete-orphan")
    signal_outcome = relationship("SignalOutcome", back_populates="prediction", uselist=False, cascade="all, delete-orphan")


class DetectedSignal(Base):
    __tablename__ = 'detected_signals'
    id = Column(Integer, primary_key=True)
    prediction_id = Column(Integer, ForeignKey('prediction_reviews.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    framework = Column(String(8), nullable=False)
    direction = Column(String(16), nullable=True)
    timeframe = Column(String(16), nullable=True)
    strength = Column(Integer, default=0)
    confidence = Column(Float, default=0.0)
    price_low = Column(Float, nullable=True)
    price_high = Column(Float, nullable=True)
    candle_start = Column(Integer, nullable=True)
    candle_end = Column(Integer, nullable=True)
    validation_reason = Column(Text, nullable=True)
    invalidation_reason = Column(Text, nullable=True)
    status = Column(String(16), default='active')
    created_at = Column(DateTime, default=datetime.utcnow)

    prediction = relationship("PredictionReview", back_populates="detected_signals")


class UserFeedback(Base):
    __tablename__ = 'user_feedback'
    id = Column(Integer, primary_key=True)
    prediction_id = Column(Integer, ForeignKey('prediction_reviews.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    trade_entry = Column(String(16), nullable=True)
    feedback = Column(String(16), nullable=True)
    comment = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    prediction = relationship("PredictionReview", back_populates="user_feedback")

    __table_args__ = (UniqueConstraint('prediction_id', 'user_id', name='uq_feedback_prediction_user'),)


class MarketVerification(Base):
    __tablename__ = 'market_verifications'
    id = Column(Integer, primary_key=True)
    prediction_id = Column(Integer, ForeignKey('prediction_reviews.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    start_price = Column(Float, nullable=False)
    end_price = Column(Float, nullable=True)
    max_favorable_excursion = Column(Float, nullable=True)
    max_adverse_excursion = Column(Float, nullable=True)
    actual_direction = Column(String(16), nullable=True)
    outcome = Column(String(24), nullable=True)
    invalidation_hit = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    method = Column(String(32), default='candle_mfe_mae')

    prediction = relationship("PredictionReview", back_populates="market_verification")


class TrainingRecord(Base):
    __tablename__ = 'training_records'
    id = Column(Integer, primary_key=True)
    prediction_id = Column(Integer, ForeignKey('prediction_reviews.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    user_feedback_id = Column(Integer, ForeignKey('user_feedback.id', ondelete='SET NULL'), nullable=True)
    market_verification_id = Column(Integer, ForeignKey('market_verifications.id', ondelete='SET NULL'), nullable=True)
    features_json = Column(Text, nullable=True)
    label_from_market = Column(String(16), nullable=True)
    label_from_user = Column(String(16), nullable=True)
    final_label = Column(String(16), nullable=True)
    conflict = Column(Boolean, default=False, nullable=False)
    label_quality_score = Column(Float, nullable=True)
    admin_status = Column(String(24), default='PENDING_REVIEW', nullable=False, index=True)
    admin_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    prediction = relationship("PredictionReview", back_populates="training_record")


class Notification(Base):
    __tablename__ = 'notifications'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String(32), nullable=False, index=True)
    title = Column(String(160), nullable=False)
    body = Column(Text, nullable=False)
    link = Column(String(256), nullable=True)
    meta_json = Column(Text, nullable=True)
    read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('ix_notifications_user_read_created', 'user_id', 'read', 'created_at'),
    )


class ConfirmationWatch(Base):
    """Track WAIT_FOR_CONFIRMATION setups until they confirm into a tradeable bias."""
    __tablename__ = 'confirmation_watches'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    source_review_id = Column(Integer, ForeignKey('prediction_reviews.id', ondelete='CASCADE'), nullable=False, index=True)
    confirmed_review_id = Column(Integer, ForeignKey('prediction_reviews.id', ondelete='SET NULL'), nullable=True, index=True)
    symbol = Column(String(16), nullable=False, index=True)
    interval = Column(String(16), default='60min')
    horizon = Column(String(16), default='intraday')
    strategy_mode = Column(String(16), default='both')
    trading_style = Column(String(16), default='intraday')
    params_json = Column(Text, nullable=True)
    status = Column(String(16), default='watching', nullable=False, index=True)
    wait_reason = Column(Text, nullable=True)
    confirmed_action = Column(String(32), nullable=True)
    confirmation_reason = Column(Text, nullable=True)
    confirmed_snapshot_json = Column(Text, nullable=True)
    notified_at = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_confirmation_watches_user_status', 'user_id', 'status'),
    )


class AdminLog(Base):
    __tablename__ = 'admin_logs'
    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    target_type = Column(String(32), nullable=True)
    target_id = Column(String(64), nullable=True)
    detail_json = Column(Text, nullable=True)
    ip = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class EquitySnapshot(Base):
    __tablename__ = 'equity_snapshots'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    balance = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
