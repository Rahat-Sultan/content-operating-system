"""owner for user-owned data; the existing data belongs to the first (admin) account

Existing rows are assigned to the admin account created here. That account has no
password until you set one: run `python -m app.accounts.set_password <email>` once.

Revision ID: a8c3e1f5d2b9
Revises: f7a2c9d4e1b6
Create Date: 2026-10-06 16:30:00.000000
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a8c3e1f5d2b9'
down_revision: Union[str, Sequence[str], None] = 'f7a2c9d4e1b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN_EMAIL = "rahatsultan654@gmail.com"
OWNED_TABLES = ["content_strategies", "sources", "ideas", "workflow_runs", "publications", "scheduled_jobs"]


def upgrade() -> None:
    conn = op.get_bind()
    admin_id = str(uuid.uuid4())
    conn.execute(sa.text(
        "INSERT INTO users (id, email, display_name, password_hash, auth_provider, is_admin) "
        "VALUES (:id, :email, 'Admin', NULL, 'local', true) ON CONFLICT (email) DO NOTHING"
    ), {"id": admin_id, "email": ADMIN_EMAIL})
    admin_id = conn.execute(sa.text("SELECT id FROM users WHERE email = :e"), {"e": ADMIN_EMAIL}).scalar_one()

    for table in OWNED_TABLES:
        op.add_column(table, sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True))
        conn.execute(sa.text(f"UPDATE {table} SET owner_id = :id WHERE owner_id IS NULL"), {"id": admin_id})
        op.alter_column(table, 'owner_id', nullable=False)
        op.create_foreign_key(f"fk_{table}_owner", table, "users", ["owner_id"], ["id"], ondelete="CASCADE")
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])

    # Per-user platform settings and API keys: the key is now (owner, name).
    op.add_column('platform_settings', sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('secret_values', sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True))
    conn.execute(sa.text("UPDATE secret_values SET owner_id = :id"), {"id": admin_id})
    conn.execute(sa.text("UPDATE platform_settings SET owner_id = :id"), {"id": admin_id})
    op.drop_constraint('platform_settings_pkey', 'platform_settings', type_='primary')
    op.drop_constraint('secret_values_pkey', 'secret_values', type_='primary')
    op.alter_column('platform_settings', 'owner_id', nullable=False)
    op.alter_column('secret_values', 'owner_id', nullable=False)
    op.create_primary_key('platform_settings_pkey', 'platform_settings', ['owner_id', 'key'])
    op.create_primary_key('secret_values_pkey', 'secret_values', ['owner_id', 'name'])
    op.create_foreign_key("fk_platform_settings_owner", "platform_settings", "users", ["owner_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_secret_values_owner", "secret_values", "users", ["owner_id"], ["id"], ondelete="CASCADE")

    # The old installation-wide Settings password and sessions are replaced by accounts.
    op.drop_table('settings_sessions')
    op.drop_table('settings_auth')

    # Same-named ideas per user: the one-NEW-per-title index now includes the owner.
    op.drop_index('uq_new_idea_title_per_strategy', table_name='ideas')
    op.execute("CREATE UNIQUE INDEX uq_new_idea_title_per_strategy ON ideas (strategy_id, title) WHERE status = 'NEW'")


def downgrade() -> None:
    raise NotImplementedError("Restore from a backup. This migration reassigns ownership of existing data.")
