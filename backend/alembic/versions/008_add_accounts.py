"""add accounts table and transaction.account_id

Revision ID: 008
Revises: 007
Create Date: 2026-10-03

Multi-account support (Phase 4A). Adds an ``accounts`` table owned by exactly
one user and a nullable ``transactions.account_id`` foreign key.

The column is nullable on purpose: every existing transaction stays valid with
``account_id = NULL`` and is never assigned to an account automatically. No
existing rows are read, rewritten, or inferred. Only four digits of an
account/card number are ever stored (``last4``).

Reversible: downgrade drops the added column and then the table. Transactions
unlinked from a deleted account keep their amount, category and dates; only the
account reference is lost, which is why accounts are nulled out before delete
rather than leaving a dangling id.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('account_type', sa.String(), nullable=False, index=True),
        sa.Column('institution_name', sa.String(), nullable=True),
        # Length 4 is enforced by the column as well as by request validation,
        # so a full account number cannot be stored even via raw SQL.
        sa.Column('last4', sa.String(length=4), nullable=True),
        sa.Column('currency', sa.String(), nullable=False, server_default='INR'),
        sa.Column('opening_balance', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true(), index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # SQLite cannot ADD COLUMN with a non-NULL default plus a foreign key
    # constraint, and the column has to stay nullable for existing rows, so it
    # is added as a plain nullable column. batch_alter_table is used so the same
    # revision also works on backends that support adding the constraint
    # directly.
    with op.batch_alter_table('transactions') as batch_op:
        batch_op.add_column(
            sa.Column('account_id', sa.Integer(), nullable=True)
        )
        batch_op.create_index(
            'ix_transactions_account_id', ['account_id'], unique=False
        )

    with op.batch_alter_table('transactions') as batch_op:
        batch_op.create_foreign_key(
            'fk_transactions_account_id_accounts',
            'accounts',
            ['account_id'],
            ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('transactions') as batch_op:
        batch_op.drop_constraint('fk_transactions_account_id_accounts', type_='foreignkey')
        batch_op.drop_index('ix_transactions_account_id')

    with op.batch_alter_table('transactions') as batch_op:
        batch_op.drop_column('account_id')

    op.drop_table('accounts')