from pydantic import BaseModel
from datetime import date as date_type, datetime
from typing import List, Dict, Optional

class TransactionBase(BaseModel):
    date: date_type
    description: str
    amount: float
    transaction_type: str  # 'debit' or 'credit'
    category: str
    subcategory: Optional[str] = None
    is_recurring: bool = False
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
    total_spent: float
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
    monthly_cap: float

class BudgetGoalResponse(BaseModel):
    id: int
    category: str
    monthly_cap: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SavingsGoalCreate(BaseModel):
    name: str
    target_amount: float
    target_date: Optional[date_type] = None

class SavingsGoalResponse(BaseModel):
    id: int
    name: str
    target_amount: float
    target_date: Optional[date_type] = None
    created_at: datetime

    class Config:
        from_attributes = True

class BudgetStatusResponse(BaseModel):
    category: str
    monthly_cap: float
    current_spend: float
    percent_used: float
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
    amount: Optional[float] = None
    category: Optional[str] = None
    raw_text: Optional[str] = None
    image_path: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class ReceiptConfirmRequest(BaseModel):
    merchant: str
    date: date_type
    amount: float
    category: str

class AnomalyResponse(BaseModel):
    id: str
    type: str
    severity: str
    transaction_ids: List[int]
    message: str
    date: Optional[str] = None
    merchant: str
    amount: Optional[float] = None
    previous_amount: Optional[float] = None
    new_amount: Optional[float] = None
    percent_increase: Optional[float] = None
    dates: Optional[List[str]] = None
    gap_hours: Optional[int] = None
    user_avg_amount: Optional[float] = None
    user_std_dev: Optional[float] = None
