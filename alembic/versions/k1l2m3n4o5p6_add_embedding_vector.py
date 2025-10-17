"""Add embedding vector column and pgvector extension

Revision ID: k1l2m3n4o5p6
Revises: d036d6780f9b
Create Date: 2025-10-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, Sequence[str], None] = 'd036d6780f9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Add embedding column (384 dimensions for all-MiniLM-L6-v2 model)
    op.add_column('jobs', sa.Column('embedding', Vector(384), nullable=True))

    # Create an index for faster similarity search
    # Using HNSW (Hierarchical Navigable Small World) index for fast approximate nearest neighbor search
    op.execute(
        'CREATE INDEX IF NOT EXISTS jobs_embedding_idx ON jobs USING hnsw (embedding vector_cosine_ops)'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the index
    op.execute('DROP INDEX IF EXISTS jobs_embedding_idx')

    # Drop the embedding column
    op.drop_column('jobs', 'embedding')

    # Note: We don't drop the pgvector extension in downgrade
    # as it might be used by other tables
