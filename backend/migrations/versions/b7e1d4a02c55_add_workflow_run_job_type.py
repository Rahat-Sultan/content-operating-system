"""add WORKFLOW_RUN to job_type enum

Revision ID: b7e1d4a02c55
Revises: a4c7e2b91f30
Create Date: 2026-10-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e1d4a02c55'
down_revision: Union[str, Sequence[str], None] = 'a4c7e2b91f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'WORKFLOW_RUN'")


def downgrade() -> None:
    """
    PostgreSQL cannot drop an enum value. Downgrade leaves 'WORKFLOW_RUN' in
    place; rows using it must be removed by hand before any code that does not
    know the value runs.
    """
    pass
