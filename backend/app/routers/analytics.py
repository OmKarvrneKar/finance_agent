from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from decimal import Decimal
import logging

from app.database.db import get_db, User
from app.database.crud import get_analytics_summary
from app.auth import get_current_user
from app.services.merchant_analytics import get_merchant_analytics

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
