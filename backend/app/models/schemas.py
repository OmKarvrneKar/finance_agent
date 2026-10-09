from pydantic import BaseModel, EmailStr, field_validator
from datetime import date as date_type, datetime
from decimal import Decimal
from typing import List, Dict, Optional, Any
import re

# Phase 4A account types. Kept as a plain tuple so the CRUD layer, the schemas
# and the tests all read the same single definition.
ACCOUNT_TYPES = ("bank", "credit_card", "cash", "wallet", "investment", "other")

# The application reports in Indian Rupees, so that is the default currency.
DEFAULT_CURRENCY = "INR"

# Auth schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# Transaction schemas
class AccountBase(BaseModel):
    name: str
    account_type: str
    institution_name: Optional[str] = None
    # Exactly four digits, or omitted. A full account/card number is rejected
    # here rather than silently truncated.
    last4: Optional[str] = None
    currency: str = DEFAULT_CURRENCY
    opening_balance: Decimal = Decimal("0")

    @field_validator("account_type")
    @classmethod
    def validate_account_type(cls, v):
        normalised = (v or "").strip().lower()
        if normalised not in ACCOUNT_TYPES:
            raise ValueError(
                f"account_type must be one of: {', '.join(ACCOUNT_TYPES)}"
            )
        return normalised

    @field_validator("last4")
    @classmethod
    def validate_last4(cls, v):
        if v is None:
            return None
        candidate = str(v).strip()
        if not re.fullmatch(r"\d{4}", candidate):
            # This is the guard that keeps full account numbers out of the
            # database: anything that is not exactly four digits is refused.
            raise ValueError("last4 must be exactly 4 digits")
        return candidate

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v):
        candidate = (v or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", candidate):
            raise ValueError("currency must be a 3-letter ISO code, e.g. INR")
        return candidate

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        candidate = (v or "").strip()
        if not candidate:
            raise ValueError("name must not be empty")
        return candidate


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    """Partial update. Only the fields actually sent are changed.

    Duplicate names are allowed: a user may legitimately hold several accounts
    at the same bank, so no uniqueness restriction is imposed.
    """

    model_config = {"extra": "forbid"}

    name: Optional[str] = None
    account_type: Optional[str] = None
    institution_name: Optional[str] = None
    last4: Optional[str] = None
    currency: Optional[str] = None
    opening_balance: Optional[Decimal] = None
    is_active: Optional[bool] = None

    @field_validator("account_type")
    @classmethod
    def validate_account_type(cls, v):
        if v is None:
            return None
        normalised = v.strip().lower()
        if normalised not in ACCOUNT_TYPES:
            raise ValueError(
                f"account_type must be one of: {', '.join(ACCOUNT_TYPES)}"
            )
        return normalised

    @field_validator("last4")
    @classmethod
    def validate_last4(cls, v):
        if v is None:
            return None
        candidate = str(v).strip()
        if not re.fullmatch(r"\d{4}", candidate):
            raise ValueError("last4 must be exactly 4 digits")
        return candidate

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v):
        if v is None:
            return None
        candidate = v.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", candidate):
            raise ValueError("currency must be a 3-letter ISO code, e.g. INR")
        return candidate

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if v is None:
            return None
        candidate = v.strip()
        if not candidate:
            raise ValueError("name must not be empty")
        return candidate


class AccountResponse(BaseModel):
    """An account plus its derived balance.

    ``current_balance`` is computed from ``opening_balance`` and the account's
    transactions at read time; it is not a stored column.

    ``balance_nature`` tells the client how to read the sign:
      * ``available`` - positive means money available (bank, cash, wallet, ...).
      * ``owed``      - positive means money owed on the card.
    """

    id: int
    user_id: int
    name: str
    account_type: str
    institution_name: Optional[str] = None
    last4: Optional[str] = None
    currency: str
    opening_balance: Decimal
    current_balance: Decimal
    balance_nature: str
    transaction_count: int = 0
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransactionAccountAssign(BaseModel):
    """Attach (or detach, with ``account_id: null``) a transaction's account."""

    account_id: Optional[int] = None


class TransactionBase(BaseModel):
    date: date_type
    description: str
    amount: Decimal
    transaction_type: str  # 'debit' or 'credit'
    category: str
    subcategory: Optional[str] = None
    is_recurring: bool = False
    is_user_confirmed_recurring: bool = False
    raw_text: Optional[str] = None
    # Phase 4A: optional account link. Existing callers that never send this get
    # NULL, which is exactly the pre-Phase-4A behaviour.
    account_id: Optional[int] = None

class TransactionUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    category: Optional[str] = None
    subcategory: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    transaction_type: Optional[str] = None
    date: Optional[date_type] = None
    is_recurring: Optional[bool] = None

    @field_validator("transaction_type")
    @classmethod
    def validate_transaction_type(cls, v):
        if v is not None and v not in ("debit", "credit"):
            raise ValueError("transaction_type must be 'debit' or 'credit'")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        if v is not None and v <= 0:
            raise ValueError("amount must be positive")
        return v

class TransactionCreate(TransactionBase):
    model_config = {"extra": "forbid"}

    @field_validator("transaction_type")
    @classmethod
    def validate_transaction_type(cls, v: str) -> str:
        if v not in ("debit", "credit"):
            raise ValueError("transaction_type must be 'debit' or 'credit'")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if not v.is_finite() or v <= 0:
            raise ValueError("amount must be positive")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Category cannot be empty")
        return v.strip()

class TransactionResponse(TransactionBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class UploadSummaryResponse(BaseModel):
    total_transactions: int
    total_spent: Decimal
    category_breakdown: Dict[str, int]
    new_transactions: int
    duplicate_transactions: int
    total_in_file: int

class PaginatedTransactionsResponse(BaseModel):
    transactions: List[TransactionResponse]
    total: int
    page: int
    limit: int
    pages: int

class BudgetGoalCreate(BaseModel):
    category: str
    monthly_cap: Decimal

class BudgetGoalResponse(BaseModel):
    id: int
    category: str
    monthly_cap: Decimal
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SavingsGoalCreate(BaseModel):
    name: str
    target_amount: Decimal
    target_date: Optional[date_type] = None
    description: Optional[str] = None

class SavingsGoalUpdate(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[Decimal] = None
    target_date: Optional[date_type] = None
    description: Optional[str] = None
    status: Optional[str] = None

class SavingsGoalContribution(BaseModel):
    amount: Decimal

class SavingsGoalResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    target_amount: Decimal
    current_amount: Decimal
    target_date: Optional[date_type] = None
    status: str
    progress_percent: float = 0
    projected_completion: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SavingsGoalsSummaryResponse(BaseModel):
    total_goals: int
    active_goals: int
    completed_goals: int
    total_target: Decimal
    total_saved: Decimal
    overall_progress: float

class GoalProgressResponse(BaseModel):
    """Deterministic progress + projection for one savings goal.

    Money fields are Decimal and serialize as strings. ``monthly_contribution_rate``
    and the projection fields stay null when the underlying history cannot
    support them, which is signalled by ``projection_status``.
    """

    goal_id: int
    goal_name: str
    target_amount: Decimal
    current_amount: Decimal
    remaining_amount: Decimal
    progress_percent: float
    target_date: Optional[str] = None
    monthly_contribution_rate: Optional[Decimal] = None
    average_monthly_contribution: Optional[Decimal] = None
    contribution_count: int = 0
    projected_completion_date: Optional[str] = None
    projected_months_remaining: Optional[int] = None
    projection_status: str

class GoalsProgressListResponse(BaseModel):
    goals: List[GoalProgressResponse]
    total: int

class BudgetStatusResponse(BaseModel):
    budget_id: Optional[int] = None
    category: str
    monthly_cap: Decimal
    current_spend: Decimal
    percent_used: Decimal
    days_left_in_month: int
    status: str
    message: str

class SimulateRequest(BaseModel):
    category: str
    percent_change: float
    months: int = 12
    goal_name: Optional[str] = None

class PendingReceiptResponse(BaseModel):
    id: int
    merchant: Optional[str] = None
    date: Optional[date_type] = None
    amount: Optional[Decimal] = None
    category: Optional[str] = None
    raw_text: Optional[str] = None
    image_path: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class ReceiptConfirmRequest(BaseModel):
    merchant: str
    date: date_type
    amount: Decimal
    category: str

class AnomalyResponse(BaseModel):
    id: str
    type: str
    severity: str
    transaction_ids: List[int]
    message: str
    date: Optional[str] = None
    merchant: str
    amount: Optional[Decimal] = None
    previous_amount: Optional[Decimal] = None
    new_amount: Optional[Decimal] = None
    percent_increase: Optional[float] = None
    dates: Optional[List[str]] = None
    gap_hours: Optional[int] = None
    user_avg_amount: Optional[Decimal] = None
    user_std_dev: Optional[Decimal] = None

class SubscriptionResponse(BaseModel):
    description: str
    category: str
    occurrences: int
    average_amount: Decimal
    frequency: str
    estimated_monthly_cost: Decimal
    estimated_annual_cost: Decimal
    last_seen: str
    is_user_confirmed: bool = False


# Savings Recommendation schemas

class SavingsRecommendationBase(BaseModel):
    type: str
    title: str
    description: str
    estimated_monthly_savings: Decimal
    estimated_annual_savings: Decimal
    confidence: str
    supporting_data: Dict[str, Any]


class HighSpendingCategoryRecommendation(SavingsRecommendationBase):
    type: str = "high_spending_category"
    category: str
    current_monthly_avg: Decimal
    peer_monthly_avg: Optional[Decimal] = None
    months_analyzed: int


class HighFrequencyMerchantRecommendation(SavingsRecommendationBase):
    type: str = "high_frequency_merchant"
    merchant: str
    category: str
    visit_count: int
    monthly_frequency: Decimal
    average_per_visit: Decimal
    months_analyzed: int


class SpendingIncreaseRecommendation(SavingsRecommendationBase):
    type: str = "spending_increase"
    category: Optional[str] = None
    merchant: Optional[str] = None
    previous_monthly_avg: Decimal
    current_monthly_avg: Decimal
    percent_increase: float
    months_analyzed: int


class SavingsRecommendationsResponse(BaseModel):
    recommendations: List[SavingsRecommendationBase]
    total_estimated_monthly_savings: Decimal
    total_estimated_annual_savings: Decimal
    categories_analyzed: int
    merchants_analyzed: int
    months_of_data: int
    generated_at: datetime


# Merchant Analytics schemas

class MerchantAnalyticsItem(BaseModel):
    merchant: str
    total_spent: Decimal
    transaction_count: int
    average_amount: Decimal
    largest_transaction: Decimal
    spending_percent: Decimal
    first_seen: str
    last_seen: str
    category: Optional[str] = None


class MerchantAnalyticsResponse(BaseModel):
    merchants: List[MerchantAnalyticsItem]
    total_merchants: int
    total_expenses: Decimal
    date_range: Optional[Dict[str, Optional[str]]] = None


# Transaction Split schemas

class TransactionSplitCreate(BaseModel):
    category: str
    amount: Decimal
    description: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Split amount must be positive")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Category cannot be empty")
        return v.strip()


class TransactionSplitUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    category: Optional[str] = None
    amount: Optional[Decimal] = None
    description: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Split amount must be positive")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError("Category cannot be empty")
        return v.strip() if v else v


class TransactionSplitResponse(BaseModel):
    id: int
    transaction_id: int
    user_id: int
    category: str
    amount: Decimal
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransactionWithSplitsResponse(BaseModel):
    id: int
    user_id: int
    date: date_type
    description: str
    amount: Decimal
    transaction_type: str
    category: str
    subcategory: Optional[str] = None
    is_recurring: bool
    source: str
    created_at: datetime
    splits: List[TransactionSplitResponse] = []
    split_total: Decimal = Decimal('0')
    is_split: bool = False

    class Config:
        from_attributes = True


# Recurring Bill Calendar schemas

class RecurringCalendarBill(BaseModel):
    description: str
    category: Optional[str] = None
    expected_amount: Decimal
    expected_date: Optional[str] = None
    date_status: str  # projected | uncertain | missing
    frequency: str
    is_user_confirmed: bool = False
    occurrences: int
    last_seen: str


class RecurringCalendarResponse(BaseModel):
    bills: List[RecurringCalendarBill]
    start_date: str
    end_date: str
    total_expected_amount: Decimal
    count: int


# Spending Velocity schemas

class SpendingVelocityResponse(BaseModel):
    current_window_spend: Decimal
    baseline_window_spend: Decimal
    velocity_ratio: Optional[float] = None
    percentage_change: Optional[float] = None
    window_days: int
    baseline_method: str
    alert_level: str
    start_date: str
    end_date: str
    baseline_windows_used: int = 0
    history_start_date: Optional[str] = None


# Notification schemas

NOTIFICATION_TYPES = {"budget_threshold", "budget_exceeded", "spending_velocity", "anomaly"}
NOTIFICATION_SEVERITIES = {"info", "warning", "critical"}


class NotificationCreate(BaseModel):
    type: str
    title: str
    message: str
    severity: str = "info"
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None
    event_key: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in NOTIFICATION_TYPES:
            raise ValueError(
                f"Invalid notification type '{v}'. Must be one of: {sorted(NOTIFICATION_TYPES)}"
            )
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        if v not in NOTIFICATION_SEVERITIES:
            raise ValueError(
                f"Invalid notification severity '{v}'. Must be one of: {sorted(NOTIFICATION_SEVERITIES)}"
            )
        return v

    @field_validator("title", "message")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field must not be empty.")
        return v.strip()


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    type: str
    title: str
    message: str
    severity: str
    is_read: bool
    created_at: datetime
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    total: int
    page: int
    limit: int
    pages: int
    unread_count: int
