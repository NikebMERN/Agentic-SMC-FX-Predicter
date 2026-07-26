"""notification delivery outbox

Revision ID: 005_notification_outbox
Revises: 004_ml_platform
"""
from alembic import op
import sqlalchemy as sa

revision = "005_notification_outbox"
down_revision = "004_ml_platform"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
        sa.UniqueConstraint("event_key", "channel", name="ux_notification_delivery_event_channel"),
    )
    op.create_index("ix_notification_delivery_pending", "notification_deliveries", ["status", "next_attempt_at"])
    op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])


def downgrade():
    op.drop_table("notification_deliveries")
