from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database.db import get_db, AnomalyReview, User
from app.database import crud
from app.models import schemas
from app.services import anomalies
from app.auth import get_current_user

router = APIRouter()

def _validate_account(db: Session, account_id: Optional[int], user_id: int) -> None:
    if account_id is not None:
        account = crud.get_account(db, account_id, user_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found.")

@router.get("/anomalies", response_model=List[schemas.AnomalyResponse])
def get_anomalies(
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_account(db, account_id, current_user.id)
    return anomalies.generate_anomaly_report(db, current_user.id, account_id=account_id)

@router.post("/anomalies/{anomaly_id}/dismiss")
def dismiss_anomaly(
    anomaly_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.query(AnomalyReview).filter(
        AnomalyReview.user_id == current_user.id,
        AnomalyReview.anomaly_signature == anomaly_id
    ).first()
    if existing:
        existing.status = "dismissed"
    else:
        rev = AnomalyReview(
            user_id=current_user.id,
            anomaly_signature=anomaly_id,
            status="dismissed"
        )
        db.add(rev)
    db.commit()
    return {"message": "Anomaly dismissed."}

@router.post("/anomalies/{anomaly_id}/confirm")
def confirm_anomaly(
    anomaly_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.query(AnomalyReview).filter(
        AnomalyReview.user_id == current_user.id,
        AnomalyReview.anomaly_signature == anomaly_id
    ).first()
    if existing:
        existing.status = "confirmed_issue"
    else:
        rev = AnomalyReview(
            user_id=current_user.id,
            anomaly_signature=anomaly_id,
            status="confirmed_issue"
        )
        db.add(rev)
    db.commit()
    return {"message": "Anomaly confirmed as an issue."}
