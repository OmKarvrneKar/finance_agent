import calendar
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.db import BudgetGoal, SavingsGoal, Transaction
from typing import List, Dict, Any, Optional
from app.services.forecasting import get_historical_average

def get_budget_status(db: Session, user_id: int, month: Optional[str] = None) -> List[Dict[str, Any]]:
    if not month:
        month = datetime.today().strftime("%Y-%m")
        
    year = int(month.split('-')[0])
    m = int(month.split('-')[1])
    
    start_date = date(year, m, 1)
    end_date = date(year, m, calendar.monthrange(year, m)[1])
    
    today = date.today()
    if today.year == year and today.month == m:
        days_passed = today.day
    elif today > end_date:
        days_passed = calendar.monthrange(year, m)[1]
    else:
        days_passed = 1 
        
    total_days = calendar.monthrange(year, m)[1]
    days_left = total_days - days_passed
    if days_left < 0:
        days_left = 0
        
    time_elapsed_pct = Decimal(str(days_passed)) / Decimal(str(total_days))
    
    budgets = db.query(BudgetGoal).filter(BudgetGoal.user_id == user_id).all()
    status_list = []
    
    for b in budgets:
        current_spend = db.query(func.sum(Transaction.amount)).filter(
            Transaction.user_id == user_id,
            func.lower(Transaction.category) == b.category.lower(),
            Transaction.transaction_type == 'debit',
            Transaction.date >= start_date,
            Transaction.date <= end_date
        ).scalar() or Decimal('0.00')
        
        percent_used = (current_spend / b.monthly_cap) * 100 if b.monthly_cap > 0 else Decimal('100.0')
        
        if current_spend > b.monthly_cap:
            status = "over"
            msg = f"You are over your {b.category} budget by ₹{current_spend - b.monthly_cap}."
        elif current_spend >= (b.monthly_cap * Decimal('0.8')):
            status = "approaching"
            msg = f"You are approaching your {b.category} budget ({percent_used}% used)."
        else:
            status = "on_track"
            msg = f"You are on track for your {b.category} budget."
            
        status_list.append({
            "category": b.category,
            "monthly_cap": b.monthly_cap,
            "current_spend": current_spend,
            "percent_used": percent_used,
            "days_left_in_month": days_left,
            "status": status,
            "message": msg
        })
        
    return status_list

def simulate_what_if(db: Session, user_id: int, category: str, percent_change: float, months: int = 12, goal_name: Optional[str] = None) -> Dict[str, Any]:
    hist = get_historical_average(category, db, user_id, num_past_months=3)
    if "error" in hist:
        return {"error": "insufficient data", "message": f"Not enough historical data to simulate {category}."}
        
    baseline_monthly = hist["historical_average"]
    
    new_monthly = baseline_monthly * (1 + (Decimal(str(percent_change)) / Decimal('100.0')))
    if new_monthly < 0:
        new_monthly = Decimal('0.00')
        
    monthly_delta = baseline_monthly - new_monthly
    
    projected_total = monthly_delta * Decimal(str(months))
    
    result = {
        "category": category,
        "percent_change": percent_change,
        "baseline_monthly_spend": baseline_monthly,
        "new_monthly_spend": new_monthly,
        "monthly_delta": monthly_delta,
        "projected_total_over_period": projected_total,
        "months_to_goal": None
    }
    
    if goal_name and monthly_delta > 0:
        goal = db.query(SavingsGoal).filter(
            SavingsGoal.user_id == user_id,
            func.lower(SavingsGoal.name) == goal_name.lower()
        ).first()
        if goal:
            months_to_goal = goal.target_amount / monthly_delta
            result["months_to_goal"] = months_to_goal
            
    return result
