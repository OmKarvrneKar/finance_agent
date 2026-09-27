from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.db import get_db, User
from app.services.health_score import calculate_health_score
from app.auth import get_current_user

router = APIRouter()

@router.get("/health")
def get_health_score(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return calculate_health_score(db, current_user.id)
