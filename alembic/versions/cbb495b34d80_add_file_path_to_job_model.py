"""Add file_path to Job model

Revision ID: cbb495b34d80
Revises: 8c215621414a
Create Date: 2025-10-14 21:31:17.280287

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'cbb495b34d80'
down_revision: Union[str, Sequence[str], None] = '8c215621414a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('jobs', sa.Column('file_path', sa.String(length=500), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('jobs', 'file_path')
