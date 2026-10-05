"""add scheduled jobs table

Revision ID: 928d1f2e9a3b
Revises: 813e9f1e8e3d
Create Date: 2026-10-05 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '928d1f2e9a3b'
down_revision: Union[str, Sequence[str], None] = '813e9f1e8e3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    job_type = postgresql.ENUM('DISCOVERY', 'ANALYTICS_SYNC', name='job_type', create_type=False)
    job_type.create(op.get_bind(), checkfirst=True)

    job_status = postgresql.ENUM('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', name='job_status', create_type=False)
    job_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'scheduled_jobs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('job_type', postgresql.ENUM('DISCOVERY', 'ANALYTICS_SYNC', name='job_type', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', name='job_status', create_type=False), nullable=False),
        sa.Column('strategy_id', sa.UUID(), nullable=True),
        sa.Column('publication_id', sa.UUID(), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('claimed_by', sa.Text(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['strategy_id'], ['content_strategies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['publication_id'], ['publications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_scheduled_jobs_status_scheduled_at', 'scheduled_jobs', ['status', 'scheduled_at'])
    op.create_index('ix_scheduled_jobs_strategy_id', 'scheduled_jobs', ['strategy_id'])
    op.create_index('ix_scheduled_jobs_publication_id', 'scheduled_jobs', ['publication_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_scheduled_jobs_publication_id', table_name='scheduled_jobs')
    op.drop_index('ix_scheduled_jobs_strategy_id', table_name='scheduled_jobs')
    op.drop_index('ix_scheduled_jobs_status_scheduled_at', table_name='scheduled_jobs')
    op.drop_table('scheduled_jobs')
    sa.Enum(name='job_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='job_type').drop(op.get_bind(), checkfirst=True)
