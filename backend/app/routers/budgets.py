from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
from decimal import Decimal
from app.database import crud
from app.database.db import get_db, BudgetGoal, SavingsGoal, User
from app.models import schemas
from app.services import budgets
from app.services import notification_producers
from app.auth import get_current_user

router = APIRouter()


def _validate_account(db: Session, account_id: Optional[int], user_id: int) -> None:
    if account_id is not None:
        account = crud.get_account(db, account_id, user_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found.")

@router.post("/budgets", response_model=schemas.BudgetGoalResponse)
def create_or_update_budget(
    budget_in: schemas.BudgetGoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if budget_in.monthly_cap <= 0:
        raise HTTPException(status_code=400, detail="Monthly cap must be greater than 0.")
        
    budget = db.query(BudgetGoal).filter(
        BudgetGoal.user_id == current_user.id,
        func.lower(BudgetGoal.category) == budget_in.category.lower()
    ).first()
    if budget:
        budget.monthly_cap = budget_in.monthly_cap
    else:
        budget = BudgetGoal(
            user_id=current_user.id,
            category=budget_in.category,
            monthly_cap=budget_in.monthly_cap
        )
        db.add(budget)
        
    db.commit()
    db.refresh(budget)
    notification_producers.sync_after_budget_change(db, current_user.id)
    return budget

@router.get("/budgets", response_model=List[schemas.BudgetStatusResponse])
def get_budgets(
    month: str = Query(None, description="YYYY-MM"),
    account_id: Optional[int] = Query(
        None,
        description=(
            "Filter budget spending to a single account. Budget caps stay "
            "user-level; only the current-spend calculation is scoped to this "
            "account (NULL-account transactions excluded). Omit for all accounts."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_account(db, account_id, current_user.id)
    return budgets.get_budget_status(db, current_user.id, month, account_id=account_id)

@router.delete("/budgets/{category}")
def delete_budget(
    category: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    budget = db.query(BudgetGoal).filter(
        BudgetGoal.user_id == current_user.id,
        func.lower(BudgetGoal.category) == category.lower()
    ).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found for this category.")
    
    db.delete(budget)
    db.commit()
    return {"message": "Budget goal removed."}

@router.post("/simulate")
def simulate_budget_change(
    sim_in: schemas.SimulateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = budgets.simulate_what_if(
        db, current_user.id, sim_in.category, sim_in.percent_change, sim_in.months, sim_in.goal_name
    )
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["message"])
    return res
