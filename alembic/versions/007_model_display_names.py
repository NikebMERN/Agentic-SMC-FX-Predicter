"""Editable semantic display names for model versions."""
from alembic import op
import sqlalchemy as sa

revision = "007_model_display_names"
down_revision = "006_ml_feedback_governance"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("model_versions", sa.Column("display_name", sa.String(64), nullable=True))
    op.create_index("ix_model_versions_display_name", "model_versions", ["display_name"])


def downgrade():
    op.drop_index("ix_model_versions_display_name", table_name="model_versions")
    op.drop_column("model_versions", "display_name")
