"""add vault lockout columns (brute-force protection for the settings password)

Revision ID: 82301c732b02
Revises: 0cf214bd69be
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '82301c732b02'
down_revision: Union[str, Sequence[str], None] = '0cf214bd69be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('vault_failed_attempts', sa.Integer(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('vault_locked_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'vault_locked_until')
    op.drop_column('users', 'vault_failed_attempts')
