"""add_token_revocation_fields

Revision ID: 978715974dba
Revises: dbe1c2f7c955
Create Date: 2025-10-18 21:28:45.415906

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '978715974dba'
down_revision: Union[str, Sequence[str], None] = 'dbe1c2f7c955'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add current_token_jti column
    op.add_column('users', sa.Column('current_token_jti', sa.String(255), nullable=True))
    
    # Add token_revocation_counter column
    op.add_column('users', sa.Column('token_revocation_counter', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove token_revocation_counter column
    op.drop_column('users', 'token_revocation_counter')
    
    # Remove current_token_jti column
    op.drop_column('users', 'current_token_jti')
