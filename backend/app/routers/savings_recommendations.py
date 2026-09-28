from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.db import get_db, User
from app.services.savings_recommendations import generate_savings_recommendations
from app.services.ai_savings_explainer import generate_ai_explanations
from app.auth import get_current_user

router = APIRouter()


@router.get("/savings-recommendations")
def get_savings_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = generate_savings_recommendations(db, current_user.id)

    recs = result.get("recommendations", [])
    ai_layer = generate_ai_explanations(recs)

    result["ai_explanations"] = ai_layer.get("explanations", [])
    result["ai_summary"] = ai_layer.get("summary") or ai_layer.get("fallback_summary", "")
    if "error" in ai_layer:
        result["ai_error"] = ai_layer["error"]

    return result
