"""archive support for strategies; one NEW idea per title per strategy

Revision ID: c9d3a1f0e2b7
Revises: b7e1d4a02c55
Create Date: 2026-10-06 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c9d3a1f0e2b7'
down_revision: Union[str, Sequence[str], None] = 'b7e1d4a02c55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('content_strategies', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    # Only NEW ideas: duplicates that already have runs are history and are left alone.
    op.execute(
        "CREATE UNIQUE INDEX uq_new_idea_title_per_strategy "
        "ON ideas (strategy_id, title) WHERE status = 'NEW'"
    )


def downgrade() -> None:
    op.drop_index('uq_new_idea_title_per_strategy', table_name='ideas')
    op.drop_column('content_strategies', 'archived_at')
