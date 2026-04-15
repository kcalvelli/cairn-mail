"""Add consecutive_empty_syncs column to accounts table

Revision ID: 007
Revises: 006
Create Date: 2026-04-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add consecutive_empty_syncs column with default 0
    op.add_column('accounts', sa.Column('consecutive_empty_syncs', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('accounts', 'consecutive_empty_syncs')
