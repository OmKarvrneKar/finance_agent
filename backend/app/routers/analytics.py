from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from decimal import Decimal
import logging

from app.database.db import get_db, User
from app.database import crud
from app.database.crud import get_analytics_summary
from app.auth import get_current_user
from app.services.merchant_analytics import get_merchant_analytics
from app.services.spending_velocity import (
    DEFAULT_WINDOW_DAYS,
    MAX_WINDOW_DAYS,
    get_spending_velocity,
)
from app.models.schemas import SpendingVelocityResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/summary")
def get_dashboard_summary(
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if account_id is not None:
        account = crud.get_account(db, account_id, current_user.id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found.")
    return get_analytics_summary(db, current_user.id, start_date, end_date, account_id)


@router.get("/merchants")
def get_merchant_analytics_endpoint(
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    limit: int = Query(20, ge=1, le=100, description="Max merchants to return"),
    search: Optional[str] = Query(None, description="Search merchant name"),
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if account_id is not None:
        account = crud.get_account(db, account_id, current_user.id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found.")
    return get_merchant_analytics(
        db, current_user.id, start_date, end_date, limit, search, account_id
    )


@router.get("/spending-velocity", response_model=SpendingVelocityResponse)
def get_spending_velocity_endpoint(
    window_days: int = Query(
        DEFAULT_WINDOW_DAYS,
        ge=1,
        le=MAX_WINDOW_DAYS,
        description="Current window length in days (1-90)",
    ),
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if account_id is not None:
        account = crud.get_account(db, account_id, current_user.id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found.")
    return get_spending_velocity(
        db, current_user.id, window_days=window_days, account_id=account_id
    )
