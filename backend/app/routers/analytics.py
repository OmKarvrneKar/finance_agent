from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from decimal import Decimal
import logging

from app.database.db import get_db, User
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_analytics_summary(db, current_user.id, start_date, end_date)


@router.get("/merchants")
def get_merchant_analytics_endpoint(
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    limit: int = Query(20, ge=1, le=100, description="Max merchants to return"),
    search: Optional[str] = Query(None, description="Search merchant name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_merchant_analytics(
        db, current_user.id, start_date, end_date, limit, search
    )


@router.get("/spending-velocity", response_model=SpendingVelocityResponse)
def get_spending_velocity_endpoint(
    window_days: int = Query(
        DEFAULT_WINDOW_DAYS,
        ge=1,
        le=MAX_WINDOW_DAYS,
        description="Current window length in days (1-90)",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_spending_velocity(db, current_user.id, window_days=window_days)
