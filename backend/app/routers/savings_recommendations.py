from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import crud
from app.database.db import get_db, User
from app.services.savings_recommendations import generate_savings_recommendations
from app.services.ai_savings_explainer import generate_ai_explanations
from app.auth import get_current_user

router = APIRouter()


def _validate_account(db: Session, account_id: Optional[int], user_id: int) -> None:
    if account_id is not None:
        account = crud.get_account(db, account_id, user_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found.")


@router.get("/savings-recommendations")
def get_savings_recommendations(
    account_id: Optional[int] = Query(
        None,
        description=(
            "Filter recommendations to a single account. Both the monthly "
            "spending and merchant-level queries used to derive "
            "recommendations are scoped to this account; NULL-account "
            "transactions are excluded. Omit for all accounts."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_account(db, account_id, current_user.id)
    result = generate_savings_recommendations(db, current_user.id, account_id=account_id)

    recs = result.get("recommendations", [])
    ai_layer = generate_ai_explanations(recs)

    result["ai_explanations"] = ai_layer.get("explanations", [])
    result["ai_summary"] = ai_layer.get("summary") or ai_layer.get("fallback_summary", "")
    if "error" in ai_layer:
        result["ai_error"] = ai_layer["error"]

    return result
