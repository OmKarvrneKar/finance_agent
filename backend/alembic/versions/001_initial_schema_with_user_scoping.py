"""initial schema with user scoping

Revision ID: 001
Revises: 
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_id', 'users', ['id'], unique=False)

    # transactions table
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('transaction_type', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('subcategory', sa.String(), nullable=True),
        sa.Column('is_recurring', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('raw_text', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=False, server_default='bank_statement'),
        sa.Column('receipt_image_path', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_transactions_id', 'transactions', ['id'], unique=False)
    op.create_index('ix_transactions_user_id', 'transactions', ['user_id'], unique=False)

    # budget_goals table
    op.create_table(
        'budget_goals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('monthly_cap', sa.Numeric(12, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_budget_goals_id', 'budget_goals', ['id'], unique=False)
    op.create_index('ix_budget_goals_category', 'budget_goals', ['category'], unique=False)
    op.create_index('ix_budget_goals_user_id', 'budget_goals', ['user_id'], unique=False)

    # savings_goals table
    op.create_table(
        'savings_goals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('target_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_savings_goals_id', 'savings_goals', ['id'], unique=False)
    op.create_index('ix_savings_goals_name', 'savings_goals', ['name'], unique=False)
    op.create_index('ix_savings_goals_user_id', 'savings_goals', ['user_id'], unique=False)

    # pending_receipts table
    op.create_table(
        'pending_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('merchant', sa.String(), nullable=True),
        sa.Column('date', sa.Date(), nullable=True),
        sa.Column('amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('raw_text', sa.String(), nullable=True),
        sa.Column('image_path', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pending_receipts_id', 'pending_receipts', ['id'], unique=False)
    op.create_index('ix_pending_receipts_user_id', 'pending_receipts', ['user_id'], unique=False)

    # anomaly_reviews table
    op.create_table(
        'anomaly_reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('anomaly_signature', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_anomaly_reviews_id', 'anomaly_reviews', ['id'], unique=False)
    op.create_index('ix_anomaly_reviews_anomaly_signature', 'anomaly_reviews', ['anomaly_signature'], unique=False)
    op.create_index('ix_anomaly_reviews_user_id', 'anomaly_reviews', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('anomaly_reviews')
    op.drop_table('pending_receipts')
    op.drop_table('savings_goals')
    op.drop_table('budget_goals')
    op.drop_table('transactions')
    op.drop_table('users')
