from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database.db import User, get_db
from app.models.schemas import RecurringCalendarResponse
from app.services.recurring_calendar import (
    DEFAULT_WINDOW_DAYS,
    _parse_date,
    get_upcoming_bills,
)

router = APIRouter()


@router.get("/recurring/calendar", response_model=RecurringCalendarResponse)
def get_recurring_calendar(
    start_date: Optional[str] = Query(
        None, description="Start date YYYY-MM-DD (default: today)"
    ),
    end_date: Optional[str] = Query(
        None,
        description=(
            "End date YYYY-MM-DD "
            f"(default: today + {DEFAULT_WINDOW_DAYS} days)"
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parsed_start = _parse_date(start_date) if start_date else date.today()
    parsed_end = (
        _parse_date(end_date)
        if end_date
        else date.today() + timedelta(days=DEFAULT_WINDOW_DAYS)
    )

    if start_date and parsed_start is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid start_date. Use YYYY-MM-DD.",
        )
    if end_date and parsed_end is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid end_date. Use YYYY-MM-DD.",
        )
    if parsed_start > parsed_end:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date.",
        )

    return get_upcoming_bills(db, current_user.id, parsed_start, parsed_end)
