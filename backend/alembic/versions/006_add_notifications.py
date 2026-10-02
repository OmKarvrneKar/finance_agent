"""add notifications table

Revision ID: 006
Revises: 005
Create Date: 2026-10-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('type', sa.String(), nullable=False, index=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('message', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False, server_default='info'),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.false(), index=True),
        sa.Column('related_entity_type', sa.String(), nullable=True),
        sa.Column('related_entity_id', sa.Integer(), nullable=True),
        sa.Column('event_key', sa.String(), nullable=True, index=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
        sa.UniqueConstraint('user_id', 'event_key', name='uq_notifications_user_event_key'),
    )


def downgrade() -> None:
    op.drop_table('notifications')