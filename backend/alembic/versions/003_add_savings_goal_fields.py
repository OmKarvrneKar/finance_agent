"""add current_amount, description, status, updated_at to savings_goals

Revision ID: 003
Revises: 002
Create Date: 2026-09-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'savings_goals',
        sa.Column('description', sa.String(), nullable=True)
    )
    op.add_column(
        'savings_goals',
        sa.Column('current_amount', sa.Numeric(12, 2), nullable=False, server_default='0')
    )
    op.add_column(
        'savings_goals',
        sa.Column('status', sa.String(), nullable=False, server_default='active')
    )
    op.add_column(
        'savings_goals',
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
    )


def downgrade() -> None:
    op.drop_column('savings_goals', 'updated_at')
    op.drop_column('savings_goals', 'status')
    op.drop_column('savings_goals', 'current_amount')
    op.drop_column('savings_goals', 'description')
