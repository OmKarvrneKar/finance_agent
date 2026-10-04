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

def _apply_account_filter(query, account_id: Optional[int]):
    """Restrict a Transaction query to one account when account_id is given.

    Omitting account_id leaves the query untouched, so existing behaviour is
    byte-for-byte unchanged. A specific account excludes NULL-account rows.
    """
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)
    return query

def _get_monthly_totals(db: Session, user_id: int, category: Optional[str] = None,
                        start_date: Optional[date] = None, end_date: Optional[date] = None,
                        transaction_type: str = 'debit') -> Dict[str, Decimal]:
    query = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == transaction_type,
    )
    if category:
        query = query.filter(func.lower(Transaction.category) == category.lower())
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)

    txs = query.all()
    monthly = {}
    for t in txs:
        key = t.date.strftime("%Y-%m")
        monthly[key] = monthly.get(key, Decimal('0')) + t.amount
    return monthly

def get_daily_run_rate(category: Optional[str], month: str, db: Session, user_id: int,
                       account_id: Optional[int] = None) -> Dict[str, Any]:
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

    query = _apply_account_filter(query, account_id)

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

def forecast_month_end_spend(category: Optional[str], month: str, db: Session, user_id: int,
                             account_id: Optional[int] = None) -> Dict[str, Any]:
    run_rate_data = get_daily_run_rate(category, month, db, user_id, account_id=account_id)
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

def get_historical_average(category: Optional[str], db: Session, user_id: int, num_past_months: int = 3,
                           exclude_month: Optional[str] = None,
                           account_id: Optional[int] = None) -> Dict[str, Any]:
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

    query = _apply_account_filter(query, account_id)

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

def get_moving_average(monthly_totals: Dict[str, Decimal], num_months: int = 3) -> Optional[Decimal]:
    sorted_months = sorted(monthly_totals.keys(), reverse=True)
    recent = sorted_months[:num_months]
    if not recent:
        return None
    total = sum(monthly_totals[m] for m in recent)
    return total / Decimal(str(len(recent)))

def get_improved_forecast(category: Optional[str], month: str, db: Session, user_id: int,
                          account_id: Optional[int] = None) -> Dict[str, Any]:
    year, m = parse_month(month)
    month_start = date(year, m, 1)
    month_end = date(year, m, calendar.monthrange(year, m)[1])
    today = date.today()

    total_days_in_month = calendar.monthrange(year, m)[1]
    days_passed = (min(today, month_end) - month_start).days + 1
    if days_passed > total_days_in_month:
        days_passed = total_days_in_month
    days_remaining = max(total_days_in_month - days_passed, 0)

    actual_query = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == 'debit',
        Transaction.date >= month_start,
        Transaction.date <= (min(today, month_end)),
    )
    if category:
        actual_query = actual_query.filter(func.lower(Transaction.category) == category.lower())

    actual_query = _apply_account_filter(actual_query, account_id)

    actual_txs = actual_query.all()
    actual_spend = sum(t.amount for t in actual_txs) if actual_txs else Decimal('0')
    num_transactions = len(actual_txs)

    hist_query = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == 'debit',
        Transaction.date < month_start,
    )
    if category:
        hist_query = hist_query.filter(func.lower(Transaction.category) == category.lower())

    hist_query = _apply_account_filter(hist_query, account_id)

    hist_txs = hist_query.all()
    hist_monthly: Dict[str, Decimal] = {}
    for t in hist_txs:
        key = t.date.strftime("%Y-%m")
        hist_monthly[key] = hist_monthly.get(key, Decimal('0')) + t.amount

    moving_avg = get_moving_average(hist_monthly, num_months=3)
    months_of_history = len(hist_monthly)

    daily_run_rate = None
    if days_passed > 0 and actual_spend > 0:
        daily_run_rate = actual_spend / Decimal(str(days_passed))

    method = "unknown"
    projected_month_end = None
    confidence = "low"

    if today > month_end:
        projected_month_end = actual_spend
        method = "actual_complete"
        confidence = "high"
    elif actual_spend == 0 and moving_avg is not None:
        projected_month_end = moving_avg
        method = "moving_average"
        confidence = "medium" if months_of_history >= 2 else "low"
    elif actual_spend > 0 and daily_run_rate is not None and days_remaining > 0:
        daily_projection = actual_spend + (daily_run_rate * Decimal(str(days_remaining)))
        if moving_avg is not None:
            projected_month_end = (daily_projection + moving_avg) / 2
            method = "blended_daily_run_rate_and_moving_average"
            confidence = "medium"
        else:
            projected_month_end = daily_projection
            method = "daily_run_rate"
            confidence = "medium" if days_passed >= 5 else "low"
    elif actual_spend > 0 and days_remaining == 0:
        projected_month_end = actual_spend
        method = "actual_current_month"
        confidence = "high"
    elif moving_avg is not None:
        projected_month_end = moving_avg
        method = "moving_average_fallback"
        confidence = "low"
    else:
        method = "insufficient_data"
        confidence = "none"

    remaining_spend = None
    if projected_month_end is not None:
        remaining_spend = max(projected_month_end - actual_spend, Decimal('0'))

    hist_avg = moving_avg

    return {
        "month": month,
        "actual_spend": actual_spend,
        "num_transactions": num_transactions,
        "projected_month_end": projected_month_end,
        "remaining_spend": remaining_spend,
        "daily_run_rate": daily_run_rate,
        "days_passed": days_passed,
        "days_remaining": days_remaining,
        "total_days_in_month": total_days_in_month,
        "method": method,
        "method_description": _describe_method(method, days_passed, months_of_history),
        "confidence": confidence,
        "historical_average": hist_avg,
        "months_of_history": months_of_history,
        "insufficient_data": method == "insufficient_data",
    }

def _describe_method(method: str, days_passed: int, months_of_history: int) -> str:
    descriptions = {
        "actual_complete": "Month is complete. Showing actual total spending.",
        "daily_run_rate": f"Projected using daily run rate from {days_passed} days of actual spending this month.",
        "moving_average": f"Projected using average of last {months_of_history} month(s) of historical spending (no spending yet this month).",
        "blended_daily_run_rate_and_moving_average": f"Blended projection combining daily run rate ({days_passed} days actual) with historical monthly average.",
        "moving_average_fallback": f"Falling back to historical monthly average (limited current month data).",
        "actual_current_month": "Month is ending. Showing actual spending to date.",
        "insufficient_data": "Not enough historical or current-month data to generate a reliable forecast.",
        "unknown": "Forecast method could not be determined.",
    }
    return descriptions.get(method, "Forecast method unknown.")

def generate_overspend_alerts(db: Session, user_id: int, month: Optional[str] = None,
                              account_id: Optional[int] = None) -> List[Dict[str, Any]]:
    if not month:
        month = datetime.today().strftime("%Y-%m")

    categories = _apply_account_filter(
        db.query(Transaction.category).filter(
            Transaction.user_id == user_id,
            Transaction.transaction_type == 'debit'
        ),
        account_id,
    ).distinct().all()
    category_names = [c[0] for c in categories if c[0]]

    alerts = []

    for cat in category_names:
        forecast_data = forecast_month_end_spend(cat, month, db, user_id, account_id=account_id)
        if "error" in forecast_data:
            continue

        hist_data = get_historical_average(cat, db, user_id, num_past_months=3, exclude_month=month,
                                           account_id=account_id)
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

    forecast_data = forecast_month_end_spend(None, month, db, user_id, account_id=account_id)
    if "error" not in forecast_data:
        hist_data = get_historical_average(None, db, user_id, num_past_months=3, exclude_month=month,
                                           account_id=account_id)
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
