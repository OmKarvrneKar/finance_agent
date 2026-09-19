from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database.db import get_db, AnomalyReview, User
from app.models import schemas
from app.services import anomalies
from app.auth import get_current_user

router = APIRouter()

@router.get("/anomalies", response_model=List[schemas.AnomalyResponse])
def get_anomalies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return anomalies.generate_anomaly_report(db, current_user.id)

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
