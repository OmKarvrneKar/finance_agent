from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.db import get_db, User
from app.database import crud
from app.services.health_score import calculate_health_score
from app.auth import get_current_user

router = APIRouter()

def _validate_account(db: Session, account_id: Optional[int], user_id: int) -> None:
    if account_id is not None:
        account = crud.get_account(db, account_id, user_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found.")

@router.get("/health")
def get_health_score(
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_account(db, account_id, current_user.id)
    return calculate_health_score(db, current_user.id, account_id=account_id)
