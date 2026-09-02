from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.db import get_db, User
from app.services.savings_recommendations import generate_savings_recommendations
from app.auth import get_current_user

router = APIRouter()


@router.get("/savings-recommendations")
def get_savings_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return generate_savings_recommendations(db, current_user.id)
