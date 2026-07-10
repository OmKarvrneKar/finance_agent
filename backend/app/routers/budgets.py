from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from app.database.db import get_db, BudgetGoal, SavingsGoal
from app.models import schemas
from app.services import budgets

router = APIRouter()

@router.post("/budgets", response_model=schemas.BudgetGoalResponse)
def create_or_update_budget(budget_in: schemas.BudgetGoalCreate, db: Session = Depends(get_db)):
    if budget_in.monthly_cap <= 0:
        raise HTTPException(status_code=400, detail="Monthly cap must be greater than 0.")
        
    budget = db.query(BudgetGoal).filter(func.lower(BudgetGoal.category) == budget_in.category.lower()).first()
    if budget:
        budget.monthly_cap = budget_in.monthly_cap
    else:
        budget = BudgetGoal(category=budget_in.category, monthly_cap=budget_in.monthly_cap)
        db.add(budget)
        
    db.commit()
    db.refresh(budget)
    return budget

@router.get("/budgets", response_model=List[schemas.BudgetStatusResponse])
def get_budgets(month: str = Query(None, description="YYYY-MM"), db: Session = Depends(get_db)):
    return budgets.get_budget_status(db, month)

@router.delete("/budgets/{category}")
def delete_budget(category: str, db: Session = Depends(get_db)):
    budget = db.query(BudgetGoal).filter(func.lower(BudgetGoal.category) == category.lower()).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found for this category.")
    
    db.delete(budget)
    db.commit()
    return {"message": "Budget goal removed."}

@router.post("/goals", response_model=schemas.SavingsGoalResponse)
def create_savings_goal(goal_in: schemas.SavingsGoalCreate, db: Session = Depends(get_db)):
    goal = SavingsGoal(name=goal_in.name, target_amount=goal_in.target_amount, target_date=goal_in.target_date)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal

@router.get("/goals", response_model=List[schemas.SavingsGoalResponse])
def get_savings_goals(db: Session = Depends(get_db)):
    return db.query(SavingsGoal).all()

@router.post("/simulate")
def simulate_budget_change(sim_in: schemas.SimulateRequest, db: Session = Depends(get_db)):
    res = budgets.simulate_what_if(db, sim_in.category, sim_in.percent_change, sim_in.months, sim_in.goal_name)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["message"])
    return res
