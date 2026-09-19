import calendar
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.db import Transaction

def parse_month(month_str: str) -> tuple[int, int]:
    try:
        dt = datetime.strptime(month_str, "%Y-%m")
        return dt.year, dt.month
    except ValueError:
        raise ValueError("Month must be in YYYY-MM format")

def get_daily_run_rate(category: Optional[str], month: str, db: Session, user_id: int) -> Dict[str, Any]:
    year, m = parse_month(month)
    start_date = date(year, m, 1)
    end_date = date(year, m, calendar.monthrange(year, m)[1])
    
    query = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == 'debit',
        Transaction.date >= start_date,
        Transaction.date <= end_date
    )
    
    if category:
        query = query.filter(func.lower(Transaction.category) == category.lower())
        
    txs = query.all()
    if len(txs) < 3:
        return {"error": "insufficient data", "message": f"Need at least 3 transactions to calculate run rate for {category or 'overall'}."}
        
    total_spend = sum(t.amount for t in txs)
    latest_date = max(t.date for t in txs)
    
    days_passed = (latest_date - start_date).days + 1
    run_rate = total_spend / Decimal(str(days_passed)) if days_passed > 0 else total_spend
    
    return {
        "daily_run_rate": run_rate,
        "total_spend_so_far": total_spend,
        "days_passed": days_passed,
        "latest_transaction_date": latest_date.isoformat()
    }

def forecast_month_end_spend(category: Optional[str], month: str, db: Session, user_id: int) -> Dict[str, Any]:
    run_rate_data = get_daily_run_rate(category, month, db, user_id)
    if "error" in run_rate_data:
        return run_rate_data
        
    year, m = parse_month(month)
    total_days_in_month = calendar.monthrange(year, m)[1]
    
    run_rate = run_rate_data["daily_run_rate"]
    spend_so_far = run_rate_data["total_spend_so_far"]
    days_passed = run_rate_data["days_passed"]
    
    days_remaining = total_days_in_month - days_passed
    if days_remaining < 0:
        days_remaining = 0
        
    forecasted_total = spend_so_far + (run_rate * Decimal(str(days_remaining)))
    
    return {
        "forecasted_total": forecasted_total,
        "daily_run_rate": run_rate,
        "spend_so_far": spend_so_far,
        "days_remaining": days_remaining,
        "total_days": total_days_in_month
    }

def get_historical_average(category: Optional[str], db: Session, user_id: int, num_past_months: int = 3, exclude_month: Optional[str] = None) -> Dict[str, Any]:
    query = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == 'debit'
    )
    
    if category:
        query = query.filter(func.lower(Transaction.category) == category.lower())
        
    if exclude_month:
        year, m = parse_month(exclude_month)
        cutoff_date = date(year, m, 1)
        query = query.filter(Transaction.date < cutoff_date)
        
    txs = query.all()
    if not txs:
        return {"error": "no historical data", "message": "No transactions found in prior months."}
        
    monthly_totals = {}
    for t in txs:
        month_key = t.date.strftime("%Y-%m")
        monthly_totals[month_key] = monthly_totals.get(month_key, Decimal('0.00')) + t.amount
        
    if not monthly_totals:
        return {"error": "no historical data", "message": "No transactions found in prior months."}
        
    sorted_months = sorted(monthly_totals.keys(), reverse=True)
    recent_months = sorted_months[:num_past_months]
    
    avg_spend = sum(monthly_totals[m] for m in recent_months) / len(recent_months)
    
    return {
        "historical_average": avg_spend,
        "months_used": len(recent_months),
        "recent_months": recent_months
    }

def generate_overspend_alerts(db: Session, user_id: int, month: Optional[str] = None) -> List[Dict[str, Any]]:
    if not month:
        month = datetime.today().strftime("%Y-%m")
        
    categories = db.query(Transaction.category).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == 'debit'
    ).distinct().all()
    category_names = [c[0] for c in categories if c[0]]
    
    alerts = []
    
    for cat in category_names:
        forecast_data = forecast_month_end_spend(cat, month, db, user_id)
        if "error" in forecast_data:
            continue
            
        hist_data = get_historical_average(cat, db, user_id, num_past_months=3, exclude_month=month)
        if "error" in hist_data:
            continue
            
        forecast_total = forecast_data["forecasted_total"]
        hist_avg = hist_data["historical_average"]
        
        if hist_avg > 0:
            percent_over = ((forecast_total - hist_avg) / hist_avg) * 100
        else:
            percent_over = Decimal('100') if forecast_total > 0 else Decimal('0')
            
        if percent_over > 15:
            severity = "critical" if percent_over > 30 else "warning"
            alerts.append({
                "category": cat,
                "current_spend": forecast_data["spend_so_far"],
                "forecasted_spend": forecast_total,
                "historical_average": hist_avg,
                "percent_over": percent_over,
                "severity": severity,
                "message": f"Forecasted to overspend by {percent_over}% in {cat} compared to historical average."
            })
            
    # Overall alert
    forecast_data = forecast_month_end_spend(None, month, db, user_id)
    if "error" not in forecast_data:
        hist_data = get_historical_average(None, db, user_id, num_past_months=3, exclude_month=month)
        if "error" not in hist_data:
            forecast_total = forecast_data["forecasted_total"]
            hist_avg = hist_data["historical_average"]
            
            if hist_avg > 0:
                percent_over = ((forecast_total - hist_avg) / hist_avg) * 100
            else:
                percent_over = Decimal('100') if forecast_total > 0 else Decimal('0')
                
            if percent_over > 15:
                severity = "critical" if percent_over > 30 else "warning"
                alerts.append({
                    "category": "Overall",
                    "current_spend": forecast_data["spend_so_far"],
                    "forecasted_spend": forecast_total,
                    "historical_average": hist_avg,
                    "percent_over": percent_over,
                    "severity": severity,
                    "message": f"Overall forecast is {percent_over}% over historical average."
                })
                
    alerts.sort(key=lambda x: x["percent_over"], reverse=True)
    return alerts
