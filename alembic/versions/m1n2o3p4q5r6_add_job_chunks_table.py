"""Add job_chunks table for semantic chunking

Revision ID: m1n2o3p4q5r6
Revises: k1l2m3n4o5p6
Create Date: 2025-10-17 11:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'm1n2o3p4q5r6'
down_revision: Union[str, Sequence[str], None] = 'k1l2m3n4o5p6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add job_chunks table for semantic chunking."""
    # Create job_chunks table
    op.create_table(
        'job_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('topic_summary', sa.Text(), nullable=True),
        sa.Column('keywords', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('start_time', sa.Float(), nullable=True),
        sa.Column('end_time', sa.Float(), nullable=True),
        sa.Column('start_char_pos', sa.Integer(), nullable=True),
        sa.Column('end_char_pos', sa.Integer(), nullable=True),
        sa.Column('embedding', Vector(384), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'chunk_index', name='uq_job_chunk_index')
    )

    # Create indexes for fast search and lookups
    op.create_index('job_chunks_job_id_idx', 'job_chunks', ['job_id'])

    # Create HNSW index for vector similarity search on chunks
    op.execute(
        'CREATE INDEX job_chunks_embedding_idx ON job_chunks USING hnsw (embedding vector_cosine_ops)'
    )


def downgrade() -> None:
    """Downgrade schema - remove job_chunks table."""
    # Drop indexes
    op.execute('DROP INDEX IF EXISTS job_chunks_embedding_idx')
    op.drop_index('job_chunks_job_id_idx', table_name='job_chunks')

    # Drop table
    op.drop_table('job_chunks')
