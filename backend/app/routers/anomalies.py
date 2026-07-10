from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database.db import get_db, AnomalyReview
from app.models import schemas
from app.services import anomalies

router = APIRouter()

@router.get("/anomalies", response_model=List[schemas.AnomalyResponse])
def get_anomalies(db: Session = Depends(get_db)):
    return anomalies.generate_anomaly_report(db)

@router.post("/anomalies/{anomaly_id}/dismiss")
def dismiss_anomaly(anomaly_id: str, db: Session = Depends(get_db)):
    # Check if already reviewed
    existing = db.query(AnomalyReview).filter(AnomalyReview.anomaly_signature == anomaly_id).first()
    if existing:
        existing.status = "dismissed"
    else:
        rev = AnomalyReview(anomaly_signature=anomaly_id, status="dismissed")
        db.add(rev)
    db.commit()
    return {"message": "Anomaly dismissed."}

@router.post("/anomalies/{anomaly_id}/confirm")
def confirm_anomaly(anomaly_id: str, db: Session = Depends(get_db)):
    existing = db.query(AnomalyReview).filter(AnomalyReview.anomaly_signature == anomaly_id).first()
    if existing:
        existing.status = "confirmed_issue"
    else:
        rev = AnomalyReview(anomaly_signature=anomaly_id, status="confirmed_issue")
        db.add(rev)
    db.commit()
    return {"message": "Anomaly confirmed as an issue."}
