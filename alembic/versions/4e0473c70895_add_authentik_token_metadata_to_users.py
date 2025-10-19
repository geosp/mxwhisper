"""add_authentik_token_metadata_to_users

Revision ID: 4e0473c70895
Revises: m1n2o3p4q5r6
Create Date: 2025-10-18 18:05:33.115811

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e0473c70895'
down_revision: Union[str, Sequence[str], None] = 'm1n2o3p4q5r6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add Authentik token metadata columns to users table."""
    op.add_column('users', sa.Column('authentik_token_identifier', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('token_created_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('token_expires_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('token_description', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema - remove Authentik token metadata columns from users table."""
    op.drop_column('users', 'token_description')
    op.drop_column('users', 'token_expires_at')
    op.drop_column('users', 'token_created_at')
    op.drop_column('users', 'authentik_token_identifier')
