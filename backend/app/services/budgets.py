import calendar
from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.db import BudgetGoal, SavingsGoal, Transaction
from typing import List, Dict, Any, Optional
from app.services.forecasting import get_historical_average

def get_budget_status(db: Session, month: Optional[str] = None) -> List[Dict[str, Any]]:
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
        
    # Expected spend threshold at this point in the month
    time_elapsed_pct = days_passed / total_days
    
    budgets = db.query(BudgetGoal).all()
    status_list = []
    
    for b in budgets:
        current_spend = db.query(func.sum(Transaction.amount)).filter(
            func.lower(Transaction.category) == b.category.lower(),
            Transaction.transaction_type == 'debit',
            Transaction.date >= start_date,
            Transaction.date <= end_date
        ).scalar() or 0.0
        
        percent_used = (current_spend / b.monthly_cap) * 100 if b.monthly_cap > 0 else 100.0
        
        # "on_track (<80% of cap given time elapsed in month), approaching (80-100%), over (>100%)"
        expected_cap = b.monthly_cap * time_elapsed_pct
        
        if current_spend > b.monthly_cap:
            status = "over"
            msg = f"You are over your {b.category} budget by ₹{(current_spend - b.monthly_cap):.2f}."
        elif current_spend >= (b.monthly_cap * 0.8):
            status = "approaching"
            msg = f"You are approaching your {b.category} budget ({percent_used:.1f}% used)."
        else:
            status = "on_track"
            msg = f"You are on track for your {b.category} budget."
            
        status_list.append({
            "category": b.category,
            "monthly_cap": b.monthly_cap,
            "current_spend": current_spend,
            "percent_used": round(percent_used, 1),
            "days_left_in_month": days_left,
            "status": status,
            "message": msg
        })
        
    return status_list

def simulate_what_if(db: Session, category: str, percent_change: float, months: int = 12, goal_name: Optional[str] = None) -> Dict[str, Any]:
    hist = get_historical_average(category, db, num_past_months=3)
    if "error" in hist:
        return {"error": "insufficient data", "message": f"Not enough historical data to simulate {category}."}
        
    baseline_monthly = hist["historical_average"]
    
    new_monthly = baseline_monthly * (1 + (percent_change / 100.0))
    if new_monthly < 0:
        new_monthly = 0.0
        
    monthly_delta = baseline_monthly - new_monthly 
    
    projected_total = monthly_delta * months
    
    result = {
        "category": category,
        "percent_change": percent_change,
        "baseline_monthly_spend": round(baseline_monthly, 2),
        "new_monthly_spend": round(new_monthly, 2),
        "monthly_delta": round(monthly_delta, 2),
        "projected_total_over_period": round(projected_total, 2),
        "months_to_goal": None
    }
    
    if goal_name and monthly_delta > 0:
        goal = db.query(SavingsGoal).filter(func.lower(SavingsGoal.name) == goal_name.lower()).first()
        if goal:
            months_to_goal = goal.target_amount / monthly_delta
            result["months_to_goal"] = round(months_to_goal, 1)
            
    return result
