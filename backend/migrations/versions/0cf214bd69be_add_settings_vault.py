"""add settings vault (second password gating API keys and Platforms)

Revision ID: 0cf214bd69be
Revises: 1b6712ad6a31
Create Date: 2026-10-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0cf214bd69be'
down_revision: Union[str, Sequence[str], None] = '1b6712ad6a31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('vault_password_hash', sa.Text(), nullable=True))
    op.create_table(
        'vault_unlocks',
        sa.Column('session_token_hash', sa.Text(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['session_token_hash'], ['user_sessions.token_hash'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('session_token_hash'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('vault_unlocks')
    op.drop_column('users', 'vault_password_hash')
