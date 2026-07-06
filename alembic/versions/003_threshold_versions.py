"""Add threshold_versions, threshold_overrides, prediction_reviews.threshold_version_id."""
from alembic import op
import sqlalchemy as sa

revision = "003_threshold_versions"
down_revision = "002_pair_thresholds"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "threshold_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_tag", sa.String(32), nullable=False, unique=True),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_threshold_versions_is_active", "threshold_versions", ["is_active"])

    op.create_table(
        "threshold_overrides",
        sa.Column("symbol", sa.String(16), primary_key=True, server_default="*"),
        sa.Column("interval", sa.String(16), primary_key=True, server_default="*"),
        sa.Column("trading_style", sa.String(16), primary_key=True, server_default="*"),
        sa.Column("patch_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    with op.batch_alter_table("prediction_reviews") as batch_op:
        batch_op.add_column(
            sa.Column(
                "threshold_version_id",
                sa.Integer(),
                sa.ForeignKey("threshold_versions.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_prediction_reviews_threshold_version_id", ["threshold_version_id"])


def downgrade():
    with op.batch_alter_table("prediction_reviews") as batch_op:
        batch_op.drop_index("ix_prediction_reviews_threshold_version_id")
        batch_op.drop_column("threshold_version_id")
    op.drop_table("threshold_overrides")
    op.drop_index("ix_threshold_versions_is_active", "threshold_versions")
    op.drop_table("threshold_versions")
