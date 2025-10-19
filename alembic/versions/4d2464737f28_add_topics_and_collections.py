"""add_topics_and_collections

Revision ID: 4d2464737f28
Revises: 978715974dba
Create Date: 2025-10-19 01:20:52.462000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d2464737f28'
down_revision: Union[str, Sequence[str], None] = '978715974dba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create topics table
    op.create_table(
        'topics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['topics.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('idx_topics_parent_id', 'topics', ['parent_id'])

    # Create collections table
    op.create_table(
        'collections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('collection_type', sa.String(length=50), nullable=True),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('is_public', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_collections_user_id', 'collections', ['user_id'])
    op.create_index('idx_collections_type', 'collections', ['collection_type'])

    # Create job_topics junction table
    op.create_table(
        'job_topics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=False),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('ai_reasoning', sa.Text(), nullable=True),
        sa.Column('assigned_by', sa.String(length=255), nullable=True),
        sa.Column('user_reviewed', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'topic_id', name='uq_job_topic')
    )
    op.create_index('idx_job_topics_job_id', 'job_topics', ['job_id'])
    op.create_index('idx_job_topics_topic_id', 'job_topics', ['topic_id'])
    op.create_index('idx_job_topics_confidence', 'job_topics', ['ai_confidence'])
    op.create_index('idx_job_topics_reviewed', 'job_topics', ['user_reviewed'])

    # Create job_collections junction table
    op.create_table(
        'job_collections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('collection_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=True),
        sa.Column('assigned_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['collection_id'], ['collections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'collection_id', name='uq_job_collection')
    )
    op.create_index('idx_job_collections_job_id', 'job_collections', ['job_id'])
    op.create_index('idx_job_collections_collection_id', 'job_collections', ['collection_id'])
    op.create_index('idx_job_collections_position', 'job_collections', ['collection_id', 'position'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop tables in reverse order (to respect foreign key constraints)
    op.drop_table('job_collections')
    op.drop_table('job_topics')
    op.drop_table('collections')
    op.drop_table('topics')
