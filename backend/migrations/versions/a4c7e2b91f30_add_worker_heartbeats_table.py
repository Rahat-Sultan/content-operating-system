"""add worker heartbeats table

Revision ID: a4c7e2b91f30
Revises: 928d1f2e9a3b
Create Date: 2026-10-06 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a4c7e2b91f30'
down_revision: Union[str, Sequence[str], None] = '928d1f2e9a3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'worker_heartbeats',
        sa.Column('worker_id', sa.Text(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('worker_id')
    )
    op.create_index('ix_worker_heartbeats_last_seen_at', 'worker_heartbeats', ['last_seen_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_worker_heartbeats_last_seen_at', table_name='worker_heartbeats')
    op.drop_table('worker_heartbeats')
