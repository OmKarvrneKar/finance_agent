from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.db import get_db, User
from app.database import crud
from app.services import forecasting
from datetime import datetime
from app.auth import get_current_user

router = APIRouter()


def _validate_account(db: Session, account_id: Optional[int], user_id: int) -> None:
    if account_id is not None:
        account = crud.get_account(db, account_id, user_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found.")


@router.get("/summary")
def get_forecast_summary(
    month: str = Query(None, description="YYYY-MM format"),
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not month:
        month = datetime.today().strftime("%Y-%m")
    _validate_account(db, account_id, current_user.id)

    forecast_data = forecasting.forecast_month_end_spend(
        None, month, db, current_user.id, account_id=account_id
    )
    hist_data = forecasting.get_historical_average(
        None, db, current_user.id, num_past_months=3, exclude_month=month, account_id=account_id
    )

    return {
        "month": month,
        "forecast": forecast_data,
        "historical": hist_data
    }

@router.get("/improved")
def get_improved_forecast(
    month: str = Query(None, description="YYYY-MM format"),
    category: str = Query(None, description="Filter by category"),
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not month:
        month = datetime.today().strftime("%Y-%m")
    _validate_account(db, account_id, current_user.id)
    return forecasting.get_improved_forecast(
        category, month, db, current_user.id, account_id=account_id
    )

@router.get("/alerts")
def get_forecast_alerts(
    month: str = Query(None, description="YYYY-MM format"),
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not month:
        month = datetime.today().strftime("%Y-%m")
    _validate_account(db, account_id, current_user.id)
    return forecasting.generate_overspend_alerts(
        db, current_user.id, month, account_id=account_id
    )

@router.get("/category/{category_name}")
def get_category_forecast(
    category_name: str,
    month: str = Query(None, description="YYYY-MM format"),
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not month:
        month = datetime.today().strftime("%Y-%m")
    _validate_account(db, account_id, current_user.id)

    forecast_data = forecasting.forecast_month_end_spend(
        category_name, month, db, current_user.id, account_id=account_id
    )
    hist_data = forecasting.get_historical_average(
        category_name, db, current_user.id, num_past_months=3, exclude_month=month,
        account_id=account_id
    )

    return {
        "category": category_name,
        "month": month,
        "forecast": forecast_data,
        "historical": hist_data
    }
