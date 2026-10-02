"""add savings goal contributions table

Revision ID: 007
Revises: 006
Create Date: 2026-10-03

Records when money was actually added to a savings goal so a contribution rate
can be measured from real history. No rows are back-filled: existing goals keep
whatever history they genuinely have, and goal-progress analytics report
insufficient_data when there is none.
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
    op.create_table(
        'savings_goal_contributions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('goal_id', sa.Integer(), sa.ForeignKey('savings_goals.id'), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('contributed_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table('savings_goal_contributions')