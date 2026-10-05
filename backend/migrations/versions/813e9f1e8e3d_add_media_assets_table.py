"""add media assets table

Revision ID: 813e9f1e8e3d
Revises: f7690ad02cfe
Create Date: 2026-10-05 12:02:40.049344

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '813e9f1e8e3d'
down_revision: Union[str, Sequence[str], None] = 'f7690ad02cfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    media_asset_type = postgresql.ENUM('IMAGE', name='media_asset_type', create_type=False)
    media_asset_type.create(op.get_bind(), checkfirst=True)

    media_asset_status = postgresql.ENUM('PENDING', 'READY', 'FAILED', name='media_asset_status', create_type=False)
    media_asset_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'media_assets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('content_version_id', sa.UUID(), nullable=False),
        sa.Column('type', postgresql.ENUM('IMAGE', name='media_asset_type', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('PENDING', 'READY', 'FAILED', name='media_asset_status', create_type=False), nullable=False),
        sa.Column('storage_url', sa.Text(), nullable=False),
        sa.Column('mime_type', sa.Text(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('alt_text', sa.Text(), nullable=True),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('provider_asset_id', sa.Text(), nullable=True),
        sa.Column('asset_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['content_version_id'], ['content_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_media_assets_content_version_id', 'media_assets', ['content_version_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_media_assets_content_version_id', table_name='media_assets')
    op.drop_table('media_assets')
    sa.Enum(name='media_asset_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='media_asset_type').drop(op.get_bind(), checkfirst=True)
