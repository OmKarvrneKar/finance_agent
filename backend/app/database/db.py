import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Date, DateTime, Numeric, ForeignKey, Text, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///finance.db")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    transaction_type = Column(String, nullable=False)  # 'debit' or 'credit'
    category = Column(String, nullable=False)
    subcategory = Column(String, nullable=True)
    is_recurring = Column(Boolean, default=False, nullable=False)
    is_user_confirmed_recurring = Column(Boolean, default=False, nullable=False)
    raw_text = Column(String, nullable=True)
    source = Column(String, default="bank_statement", nullable=False)
    receipt_image_path = Column(String, nullable=True)
    # Phase 4A: which account this transaction belongs to. Nullable so every
    # pre-existing transaction keeps working unchanged and is never guessed into
    # an account.
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Account(Base):
    """A user's own financial account (bank, card, cash, wallet, ...).

    Only the last four digits of a card/account number are ever stored, in
    ``last4``; a full account number has no column and is rejected on input.

    ``opening_balance`` is stored because it cannot be derived from
    transactions -- it predates them. The running balance deliberately is *not*
    stored: it is derived on read as ``opening_balance`` plus the signed sum of
    the account's transactions, so the two can never drift apart.
    """

    __tablename__ = "accounts"
    # SQLite does not enforce VARCHAR(length), so the "only four digits" rule is
    # enforced by these constraints as well as by request validation. Defence in
    # depth matters here because the rule is a privacy guarantee, not a
    # formatting preference.
    __table_args__ = (
        CheckConstraint(
            "last4 IS NULL OR length(last4) = 4",
            name="ck_accounts_last4_four_digits",
        ),
        CheckConstraint(
            "account_type IN ('bank', 'credit_card', 'cash', 'wallet', 'investment', 'other')",
            name="ck_accounts_account_type",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    # bank | credit_card | cash | wallet | investment | other
    account_type = Column(String, nullable=False, index=True)
    institution_name = Column(String, nullable=True)
    # Last four digits only. Never a full account/card number.
    last4 = Column(String(4), nullable=True)
    currency = Column(String, nullable=False, default="INR")
    # Balance before any tracked transaction. Nullable only in the sense that it
    # defaults to zero; stored so a balance cannot be derived from nothing.
    opening_balance = Column(Numeric(12, 2), nullable=False, default=0)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class BudgetGoal(Base):
    __tablename__ = "budget_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String, index=True, nullable=False)
    monthly_cap = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class SavingsGoal(Base):
    __tablename__ = "savings_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    target_amount = Column(Numeric(12, 2), nullable=False)
    current_amount = Column(Numeric(12, 2), nullable=False, default=0)
    target_date = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="active")  # active | completed | abandoned
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SavingsGoalContribution(Base):
    """Append-only ledger of money actually added to a savings goal.

    ``SavingsGoal.current_amount`` remains the aggregate source of truth for
    progress. This table exists purely to date contributions so a contribution
    *rate* can be measured instead of guessed. Rows are only written when a user
    really contributes; history is never back-filled or inferred.
    """

    __tablename__ = "savings_goal_contributions"

    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("savings_goals.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    contributed_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

class PendingReceipt(Base):
    __tablename__ = "pending_receipts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    merchant = Column(String, nullable=True)
    date = Column(Date, nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    category = Column(String, nullable=True)
    raw_text = Column(String, nullable=True)
    image_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class AnomalyReview(Base):
    __tablename__ = "anomaly_reviews"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    anomaly_signature = Column(String, index=True, nullable=False)
    status = Column(String, nullable=False)  # "dismissed" | "confirmed_issue"
    reviewed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class TransactionSplit(Base):
    __tablename__ = "transaction_splits"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    revoked_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Notification(Base):
    """User-scoped notification.

    type: budget_threshold | budget_exceeded | spending_velocity | anomaly
    severity: info | warning | critical

    event_key enables deterministic deduplication of the same event for the same
    user. NULL event_key values are treated as distinct by SQLite/Postgres, so
    notifications without a dedup key are never blocked by the unique constraint.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "event_key", name="uq_notifications_user_event_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    severity = Column(String, nullable=False, default="info")
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    related_entity_type = Column(String, nullable=True)
    related_entity_id = Column(Integer, nullable=True)
    event_key = Column(String, nullable=True, index=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
