"""Add pair_thresholds table."""
from alembic import op
import sqlalchemy as sa

revision = "002_pair_thresholds"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pair_thresholds",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("interval", sa.String(16), primary_key=True, server_default="*"),
        sa.Column("thresholds_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("pair_thresholds")
