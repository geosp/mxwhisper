"""add_segments_to_transcriptions

Revision ID: 3bc82393171b
Revises: fc1565c2b9ea
Create Date: 2025-10-19 23:32:01.418558

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3bc82393171b'
down_revision: Union[str, Sequence[str], None] = 'fc1565c2b9ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add segments column to transcriptions table
    op.add_column('transcriptions', sa.Column('segments', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove segments column from transcriptions table
    op.drop_column('transcriptions', 'segments')
