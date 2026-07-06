"""ML platform: expanded model_versions, training runs, alerts, exports."""
from alembic import op
import sqlalchemy as sa

revision = "004_ml_platform"
down_revision = "003_threshold_versions"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("model_versions") as batch:
        batch.add_column(sa.Column("trading_style", sa.String(16), server_default="intraday", nullable=False))
        batch.add_column(sa.Column("model_type", sa.String(16), server_default="RANDOM_FOREST", nullable=False))
        batch.add_column(sa.Column("calibrator_path", sa.String(512), nullable=True))
        batch.add_column(sa.Column("feature_schema_version", sa.String(16), server_default="v1"))
        batch.add_column(sa.Column("threshold_version_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("rule_engine_version", sa.String(32), server_default="v1"))
        batch.add_column(sa.Column("training_data_start", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("training_data_end", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("training_record_count", sa.Integer(), server_default="0"))
        batch.add_column(sa.Column("walk_forward_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("precision", sa.Float(), nullable=True))
        batch.add_column(sa.Column("recall", sa.Float(), nullable=True))
        batch.add_column(sa.Column("f1", sa.Float(), nullable=True))
        batch.add_column(sa.Column("brier_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("log_loss", sa.Float(), nullable=True))
        batch.add_column(sa.Column("win_rate", sa.Float(), nullable=True))
        batch.add_column(sa.Column("accepted_signal_count", sa.Integer(), server_default="0"))
        batch.add_column(sa.Column("rejected_signal_count", sa.Integer(), server_default="0"))
        batch.add_column(sa.Column("status", sa.String(16), server_default="CANDIDATE", nullable=False))
        batch.add_column(sa.Column("promoted_from_version_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("promoted_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))

    op.execute("UPDATE model_versions SET status='ACTIVE' WHERE is_active=1")
    op.execute("UPDATE model_versions SET status='ARCHIVED' WHERE is_active=0 AND status='CANDIDATE'")

    with op.batch_alter_table("prediction_reviews") as batch:
        batch.add_column(sa.Column("model_version_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("rule_engine_version", sa.String(32), server_default="v1"))
        batch.add_column(sa.Column("feature_schema_version", sa.String(16), server_default="v1"))
        batch.add_column(sa.Column("meta_ml_probability", sa.Float(), nullable=True))
        batch.add_column(sa.Column("confidence_before_ml", sa.Float(), nullable=True))
        batch.add_column(sa.Column("final_confidence", sa.Float(), nullable=True))
        batch.add_column(sa.Column("trading_style", sa.String(16), server_default="intraday"))

    op.create_table(
        "training_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("pairs_processed", sa.Integer(), server_default="0"),
        sa.Column("models_created", sa.Integer(), server_default="0"),
        sa.Column("models_promoted", sa.Integer(), server_default="0"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("interval", sa.String(16)),
        sa.Column("trading_style", sa.String(16)),
        sa.Column("start_date", sa.DateTime(), nullable=True),
        sa.Column("end_date", sa.DateTime(), nullable=True),
        sa.Column("walk_forward_windows", sa.Integer(), server_default="0"),
        sa.Column("total_signals", sa.Integer(), server_default="0"),
        sa.Column("accepted_signals", sa.Integer(), server_default="0"),
        sa.Column("rejected_signals", sa.Integer(), server_default="0"),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("precision", sa.Float(), nullable=True),
        sa.Column("recall", sa.Float(), nullable=True),
        sa.Column("f1", sa.Float(), nullable=True),
        sa.Column("brier_score", sa.Float(), nullable=True),
        sa.Column("log_loss", sa.Float(), nullable=True),
        sa.Column("max_adverse_excursion_avg", sa.Float(), nullable=True),
        sa.Column("confidence_calibration_json", sa.Text(), nullable=True),
        sa.Column("passed_promotion_gate", sa.Boolean(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "signal_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("prediction_reviews.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("rule_direction", sa.String(16), nullable=False),
        sa.Column("tp_price", sa.Float(), nullable=True),
        sa.Column("sl_price", sa.Float(), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("max_favorable_excursion", sa.Float(), nullable=True),
        sa.Column("max_adverse_excursion", sa.Float(), nullable=True),
        sa.Column("meta_label", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("telegram_chat_id", sa.String(64), nullable=True),
        sa.Column("pairs_json", sa.Text(), nullable=False),
        sa.Column("min_confidence", sa.Float(), server_default="0.6"),
        sa.Column("allowed_directions_json", sa.Text(), nullable=False),
        sa.Column("timeframes_json", sa.Text(), nullable=False),
        sa.Column("trading_style", sa.String(16), server_default="intraday"),
        sa.Column("quiet_hours_json", sa.Text(), nullable=True),
        sa.Column("max_alerts_per_day", sa.Integer(), server_default="10"),
        sa.Column("is_active", sa.Boolean(), server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_rule_id", sa.Integer(), sa.ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("prediction_reviews.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("export_type", sa.String(8), nullable=False),
        sa.Column("scope", sa.String(32), server_default="predictions"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column("file_url", sa.String(512), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "pair_performance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("interval", sa.String(16)),
        sa.Column("trading_style", sa.String(16)),
        sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("total_signals", sa.Integer(), server_default="0"),
        sa.Column("accepted_signals", sa.Integer(), server_default="0"),
        sa.Column("rejected_signals", sa.Integer(), server_default="0"),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("precision", sa.Float(), nullable=True),
        sa.Column("avg_confidence", sa.Float(), nullable=True),
        sa.Column("brier_score", sa.Float(), nullable=True),
        sa.Column("status_recommendation", sa.String(16), server_default="ACTIVE"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("symbol", "interval", "trading_style", name="uq_pair_perf"),
    )


def downgrade():
    op.drop_table("pair_performance")
    op.drop_table("export_jobs")
    op.drop_table("alert_events")
    op.drop_table("alert_rules")
    op.drop_table("signal_outcomes")
    op.drop_table("backtest_runs")
    op.drop_table("training_runs")
    with op.batch_alter_table("prediction_reviews") as batch:
        for col in ("trading_style", "final_confidence", "confidence_before_ml", "meta_ml_probability",
                    "feature_schema_version", "rule_engine_version", "model_version_id"):
            batch.drop_column(col)
    with op.batch_alter_table("model_versions") as batch:
        for col in ("created_at", "promoted_at", "promoted_from_version_id", "status", "rejected_signal_count",
                    "accepted_signal_count", "win_rate", "log_loss", "brier_score", "f1", "recall", "precision",
                    "walk_forward_score", "training_record_count", "training_data_end", "training_data_start",
                    "rule_engine_version", "threshold_version_id", "feature_schema_version", "calibrator_path",
                    "model_type", "trading_style"):
            batch.drop_column(col)
