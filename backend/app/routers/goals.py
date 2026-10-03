from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, date

from app.database.db import get_db, User, SavingsGoal
from app.database import crud
from app.models.schemas import (
    SavingsGoalCreate, SavingsGoalUpdate, SavingsGoalContribution,
    SavingsGoalResponse, SavingsGoalsSummaryResponse,
    GoalProgressResponse, GoalsProgressListResponse,
)
from app.auth import get_current_user
from app.services import goal_progress

router = APIRouter()


def _compute_progress(goal: SavingsGoal, db: Session, user_id: int) -> dict:
    """Legacy `progress_percent` / `projected_completion` for a savings goal.

    Delegates to the goal progress service so the legacy endpoints and
    ``/api/goals/{id}/progress`` can never disagree. No projection maths lives
    in this module.
    """
    return goal_progress.get_legacy_progress(db, user_id, goal)


@router.post("/goals", response_model=SavingsGoalResponse)
def create_goal(
    goal_in: SavingsGoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if goal_in.target_amount <= 0:
        raise HTTPException(status_code=400, detail="Target amount must be positive.")
    if goal_in.target_date and goal_in.target_date < date.today():
        raise HTTPException(status_code=400, detail="Target date cannot be in the past.")
    goal = crud.create_savings_goal(
        db, user_id=current_user.id,
        name=goal_in.name, target_amount=goal_in.target_amount,
        target_date=goal_in.target_date, description=goal_in.description,
    )
    progress = _compute_progress(goal, db, current_user.id)
    return SavingsGoalResponse(
        id=goal.id, name=goal.name, description=goal.description,
        target_amount=goal.target_amount, current_amount=goal.current_amount,
        target_date=goal.target_date, status=goal.status,
        progress_percent=progress["progress_percent"],
        projected_completion=progress["projected_completion"],
        created_at=goal.created_at, updated_at=goal.updated_at,
    )


@router.get("/goals", response_model=list[SavingsGoalResponse])
def list_goals(
    status: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    goals = crud.get_savings_goals(db, current_user.id, status=status)
    # One contributions query for the whole page instead of one per goal.
    progress_by_goal = goal_progress.get_legacy_progress_bulk(db, current_user.id, goals)
    result = []
    for g in goals:
        progress = progress_by_goal[g.id]
        result.append(SavingsGoalResponse(
            id=g.id, name=g.name, description=g.description,
            target_amount=g.target_amount, current_amount=g.current_amount,
            target_date=g.target_date, status=g.status,
            progress_percent=progress["progress_percent"],
            projected_completion=progress["projected_completion"],
            created_at=g.created_at, updated_at=g.updated_at,
        ))
    return result


@router.get("/goals/summary", response_model=SavingsGoalsSummaryResponse)
def goals_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_savings_goals_summary(db, current_user.id)


@router.get("/goals/progress", response_model=GoalsProgressListResponse)
def goals_progress(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deterministic progress + projection for every goal owned by this user.

    Read-only: computing a projection never modifies stored goal values.
    """
    goals = goal_progress.get_all_goals_progress(db, current_user.id)
    return {"goals": goals, "total": len(goals)}


# Declared before "/goals/{goal_id}" so the literal path is not captured as an
# int goal_id.
@router.get("/goals/{goal_id}/progress", response_model=GoalProgressResponse)
def goal_progress_detail(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deterministic progress + projection for a single owned goal."""
    result = goal_progress.get_goal_progress(db, current_user.id, goal_id)
    if not result:
        raise HTTPException(status_code=404, detail="Goal not found.")
    return result


@router.get("/goals/{goal_id}", response_model=SavingsGoalResponse)
def get_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    goal = crud.get_savings_goal(db, goal_id, current_user.id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found.")
    progress = _compute_progress(goal, db, current_user.id)
    return SavingsGoalResponse(
        id=goal.id, name=goal.name, description=goal.description,
        target_amount=goal.target_amount, current_amount=goal.current_amount,
        target_date=goal.target_date, status=goal.status,
        progress_percent=progress["progress_percent"],
        projected_completion=progress["projected_completion"],
        created_at=goal.created_at, updated_at=goal.updated_at,
    )


@router.put("/goals/{goal_id}", response_model=SavingsGoalResponse)
def update_goal(
    goal_id: int,
    goal_in: SavingsGoalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updates = goal_in.model_dump(exclude_unset=True)
    if "target_amount" in updates and updates["target_amount"] is not None:
        if updates["target_amount"] <= 0:
            raise HTTPException(status_code=400, detail="Target amount must be positive.")
    if "target_date" in updates and updates["target_date"] is not None:
        if isinstance(updates["target_date"], str):
            try:
                updates["target_date"] = datetime.strptime(updates["target_date"], "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format.")
        if updates["target_date"] < date.today():
            raise HTTPException(status_code=400, detail="Target date cannot be in the past.")
    if "status" in updates and updates["status"] not in ("active", "completed", "abandoned"):
        raise HTTPException(status_code=400, detail="Status must be active, completed, or abandoned.")

    goal = crud.update_savings_goal(db, goal_id, current_user.id, updates)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found.")
    progress = _compute_progress(goal, db, current_user.id)
    return SavingsGoalResponse(
        id=goal.id, name=goal.name, description=goal.description,
        target_amount=goal.target_amount, current_amount=goal.current_amount,
        target_date=goal.target_date, status=goal.status,
        progress_percent=progress["progress_percent"],
        projected_completion=progress["projected_completion"],
        created_at=goal.created_at, updated_at=goal.updated_at,
    )


@router.delete("/goals/{goal_id}")
def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    success = crud.delete_savings_goal(db, goal_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Goal not found.")
    return {"message": "Goal deleted successfully."}


@router.post("/goals/{goal_id}/contribute", response_model=SavingsGoalResponse)
def contribute_to_goal(
    goal_id: int,
    contribution: SavingsGoalContribution,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if contribution.amount <= 0:
        raise HTTPException(status_code=400, detail="Contribution amount must be positive.")
    goal = crud.contribute_to_savings_goal(db, goal_id, current_user.id, contribution.amount)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found.")
    progress = _compute_progress(goal, db, current_user.id)
    return SavingsGoalResponse(
        id=goal.id, name=goal.name, description=goal.description,
        target_amount=goal.target_amount, current_amount=goal.current_amount,
        target_date=goal.target_date, status=goal.status,
        progress_percent=progress["progress_percent"],
        projected_completion=progress["projected_completion"],
        created_at=goal.created_at, updated_at=goal.updated_at,
    )
