"""Initial schema marker revision.

Tables are created via Base.metadata.create_all on startup; this revision
marks the baseline for future Alembic-managed changes.
"""
from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
