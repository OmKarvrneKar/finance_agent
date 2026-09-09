from pydantic import BaseModel, EmailStr, field_validator
from datetime import date as date_type, datetime
from decimal import Decimal
from typing import List, Dict, Optional
import re

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

class TransactionCreate(TransactionBase):
    pass

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

class BudgetStatusResponse(BaseModel):
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
