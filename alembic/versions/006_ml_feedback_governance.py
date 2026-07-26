"""ML feedback governance and immutable datasets.

Revision ID: 006_ml_feedback_governance
Revises: 005_notification_outbox
"""
from alembic import op
import sqlalchemy as sa

revision = "006_ml_feedback_governance"
down_revision = "005_notification_outbox"
branch_labels = None
depends_on = None


def upgrade():
    for name, kind in (
        ("risk_reward_planned", sa.Float()), ("risk_reward_achieved", sa.Float()),
        ("account_type", sa.String(32)), ("volatility", sa.Float()),
        ("spread", sa.Float()), ("execution_delay_ms", sa.Integer()),
        ("manual_notes", sa.Text()),
    ):
        op.add_column("prediction_reviews", sa.Column(name, kind, nullable=True))
    for name, kind in (
        ("screenshot_path", sa.String(512)), ("account_type", sa.String(32)),
        ("execution_delay_ms", sa.Integer()), ("manual_notes", sa.Text()),
        ("payload_hash", sa.String(64)),
    ):
        op.add_column("user_feedback", sa.Column(name, kind, nullable=True))
    op.create_index("ix_user_feedback_payload_hash", "user_feedback", ["payload_hash"])
    op.add_column("training_records", sa.Column("dataset_tier", sa.String(24), nullable=False, server_default="PENDING_REVIEW"))
    op.add_column("training_records", sa.Column("validation_score", sa.Float()))
    op.add_column("training_records", sa.Column("validation_reasons_json", sa.Text()))
    op.add_column("training_records", sa.Column("duplicate_of_id", sa.Integer(), sa.ForeignKey("training_records.id", ondelete="SET NULL")))
    op.add_column("training_records", sa.Column("suspicious", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("training_records", sa.Column("institutional_example", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_training_records_dataset_tier", "training_records", ["dataset_tier"])
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_tag", sa.String(64), nullable=False, unique=True),
        sa.Column("tier", sa.String(24), nullable=False),
        sa.Column("parent_version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="SET NULL")),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("promoted_at", sa.DateTime()),
    )
    op.create_table(
        "dataset_version_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("training_record_id", sa.Integer(), sa.ForeignKey("training_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("record_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("dataset_version_id", "training_record_id", name="uq_dataset_version_record"),
    )
    op.create_table(
        "shadow_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("active_model_version_id", sa.Integer(), sa.ForeignKey("model_versions.id", ondelete="SET NULL")),
        sa.Column("candidate_model_version_id", sa.Integer(), sa.ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="SET NULL")),
        sa.Column("active_metrics_json", sa.Text(), nullable=False),
        sa.Column("candidate_metrics_json", sa.Text(), nullable=False),
        sa.Column("statistically_better", sa.Boolean(), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("shadow_evaluations")
    op.drop_table("dataset_version_records")
    op.drop_table("dataset_versions")
    op.drop_index("ix_training_records_dataset_tier", table_name="training_records")
    for column in ("institutional_example", "suspicious", "duplicate_of_id", "validation_reasons_json", "validation_score", "dataset_tier"):
        op.drop_column("training_records", column)
    op.drop_index("ix_user_feedback_payload_hash", table_name="user_feedback")
    for column in ("payload_hash", "manual_notes", "execution_delay_ms", "account_type", "screenshot_path"):
        op.drop_column("user_feedback", column)
    for column in ("manual_notes", "execution_delay_ms", "spread", "volatility", "account_type", "risk_reward_achieved", "risk_reward_planned"):
        op.drop_column("prediction_reviews", column)
