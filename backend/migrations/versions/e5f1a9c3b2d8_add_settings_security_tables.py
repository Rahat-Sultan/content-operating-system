"""settings password, sessions and encrypted API key storage

Revision ID: e5f1a9c3b2d8
Revises: d4b2c8e1a7f3
Create Date: 2026-10-06 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f1a9c3b2d8'
down_revision: Union[str, Sequence[str], None] = 'd4b2c8e1a7f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'settings_auth',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('failed_attempts', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'settings_sessions',
        sa.Column('token_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('token_hash'),
    )
    op.create_table(
        'secret_values',
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('ciphertext', sa.Text(), nullable=False),
        sa.Column('last4', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('name'),
    )


def downgrade() -> None:
    op.drop_table('secret_values')
    op.drop_table('settings_sessions')
    op.drop_table('settings_auth')
