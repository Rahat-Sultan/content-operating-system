"""add indexes for hot-path foreign-key lookups found in the performance pass

Revision ID: 914f44a041fe
Revises: 82301c732b02
Create Date: 2026-10-09 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '914f44a041fe'
down_revision: Union[str, Sequence[str], None] = '82301c732b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # "Snapshots for this post" and "latest snapshot per post" filtered on publication_id
    # with no general index (only a partial unique one for the single initial snapshot).
    op.create_index('ix_analytics_publication_id_collected_at', 'analytics', ['publication_id', 'collected_at'])
    # The run page's "does this version have a publication?" lookup, unindexed.
    op.create_index('ix_publications_content_version_id', 'publications', ['content_version_id'])
    # Stop-and-delete, duplicate checks and run history filter on idea_id across every
    # status; the existing index only covers the active-status subset.
    op.create_index('ix_workflow_runs_idea_id', 'workflow_runs', ['idea_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_workflow_runs_idea_id', table_name='workflow_runs')
    op.drop_index('ix_publications_content_version_id', table_name='publications')
    op.drop_index('ix_analytics_publication_id_collected_at', table_name='analytics')
