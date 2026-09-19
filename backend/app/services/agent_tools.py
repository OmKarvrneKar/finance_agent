import datetime
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database.db import Transaction

def parse_date(date_str: str):
    if not date_str:
        return None
    try:
        return datetime.datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None

def filter_transactions(db: Session, category: str = None, start_date: str = None, end_date: str = None, transaction_type: str = None) -> list:
    """
    Filter transactions in the database by category, date range, or transaction type.
    If start_date/end_date are not provided, defaults to all-time.
    """
    query = db.query(Transaction)
    if category:
        query = query.filter(Transaction.category.ilike(category.strip()))
    if start_date:
        parsed_start = parse_date(start_date)
        if parsed_start:
            query = query.filter(Transaction.date >= parsed_start)
    if end_date:
        parsed_end = parse_date(end_date)
        if parsed_end:
            query = query.filter(Transaction.date <= parsed_end)
    if transaction_type:
        query = query.filter(Transaction.transaction_type == transaction_type.strip().lower())
        
    transactions = query.order_by(Transaction.date.desc()).all()
    return [
        {
            "id": tx.id,
            "date": tx.date.isoformat(),
            "description": tx.description,
            "amount": tx.amount,
            "transaction_type": tx.transaction_type,
            "category": tx.category,
            "subcategory": tx.subcategory,
            "is_recurring": tx.is_recurring,
            "raw_text": tx.raw_text,
            "created_at": tx.created_at.isoformat()
        }
        for tx in transactions
    ]

def sum_by_category(db: Session, start_date: str = None, end_date: str = None) -> dict:
    """
    Compute total spend (debits) grouped by category for the given date range.
    If start_date/end_date are not provided, defaults to all-time.
    """
    query = db.query(Transaction.category, func.sum(Transaction.amount)).filter(Transaction.transaction_type == 'debit')
    if start_date:
        parsed_start = parse_date(start_date)
        if parsed_start:
            query = query.filter(Transaction.date >= parsed_start)
    if end_date:
        parsed_end = parse_date(end_date)
        if parsed_end:
            query = query.filter(Transaction.date <= parsed_end)
            
    results = query.group_by(Transaction.category).all()
    return {category: total for category, total in results if total is not None}

def compare_periods(db: Session, category: str, period1_start: str, period1_end: str, period2_start: str, period2_end: str) -> dict:
    """
    Compare spending in a specific category between two time periods, computing difference and percent change.
    All dates must be formatted as YYYY-MM-DD.
    """
    p1_start = parse_date(period1_start)
    p1_end = parse_date(period1_end)
    p2_start = parse_date(period2_start)
    p2_end = parse_date(period2_end)
    
    if not p1_start or not p1_end or not p2_start or not p2_end:
        return {"error": "Invalid date formats. Use YYYY-MM-DD."}
        
    p1_total = db.query(func.sum(Transaction.amount))\
        .filter(Transaction.category.ilike(category.strip()))\
        .filter(Transaction.transaction_type == 'debit')\
        .filter(Transaction.date >= p1_start)\
        .filter(Transaction.date <= p1_end).scalar() or 0.0
        
    p2_total = db.query(func.sum(Transaction.amount))\
        .filter(Transaction.category.ilike(category.strip()))\
        .filter(Transaction.transaction_type == 'debit')\
        .filter(Transaction.date >= p2_start)\
        .filter(Transaction.date <= p2_end).scalar() or 0.0
        
    pct_change = 0.0
    if p1_total > 0:
        pct_change = ((p2_total - p1_total) / p1_total) * 100
        
    return {
        "category": category,
        "period1": {
            "start": period1_start,
            "end": period1_end,
            "total_spent": p1_total
        },
        "period2": {
            "start": period2_start,
            "end": period2_end,
            "total_spent": p2_total
        },
        "difference": p2_total - p1_total,
        "percentage_change": pct_change
    }

def find_recurring_transactions(db: Session) -> list:
    """
    Detect recurring transactions (subscriptions, bills, salary) where is_recurring is True.
    Groups them by merchant/description, showing occurrence count, average cost, frequency, and estimated monthly cost.
    """
    txs = db.query(Transaction).filter(Transaction.is_recurring == True).all()
    if not txs:
        return []
        
    groups = {}
    for tx in txs:
        desc = tx.description.strip()
        norm_desc = desc.lower()
        if norm_desc not in groups:
            groups[norm_desc] = []
        groups[norm_desc].append(tx)
        
    results = []
    for norm_desc, group_txs in groups.items():
        count = len(group_txs)
        avg_amount = sum(tx.amount for tx in group_txs) / count
        dates = sorted([tx.date for tx in group_txs])
        
        frequency_str = "Monthly"
        est_monthly_cost = avg_amount
        
        if len(dates) > 1:
            days_span = (dates[-1] - dates[0]).days
            if days_span > 0:
                avg_days_between = days_span / (len(dates) - 1)
                if avg_days_between <= 10:
                    frequency_str = "Weekly"
                    est_monthly_cost = avg_amount * 4.33
                elif avg_days_between <= 20:
                    frequency_str = "Bi-weekly"
                    est_monthly_cost = avg_amount * 2.16
                elif avg_days_between <= 45:
                    frequency_str = "Monthly"
                    est_monthly_cost = avg_amount
                elif avg_days_between <= 100:
                    frequency_str = "Quarterly"
                    est_monthly_cost = avg_amount / 3.0
                else:
                    frequency_str = "Irregular/Yearly"
                    est_monthly_cost = avg_amount / 12.0
            else:
                frequency_str = "One-time / Initial"
        else:
            frequency_str = "Monthly (Assumed)"
            
        results.append({
            "description": group_txs[0].description,
            "category": group_txs[0].category,
            "occurrences": count,
            "average_amount": avg_amount,
            "frequency": frequency_str,
            "estimated_monthly_cost": est_monthly_cost,
            "last_seen": dates[-1].isoformat()
        })
        
    return results

def get_total_spent(db: Session, start_date: str = None, end_date: str = None) -> Decimal:
    """
    Calculate the total spending (debits) in the given date range.
    If start_date/end_date are not provided, defaults to all-time.
    """
    query = db.query(func.sum(Transaction.amount)).filter(Transaction.transaction_type == 'debit')
    if start_date:
        parsed_start = parse_date(start_date)
        if parsed_start:
            query = query.filter(Transaction.date >= parsed_start)
    if end_date:
        parsed_end = parse_date(end_date)
        if parsed_end:
            query = query.filter(Transaction.date <= parsed_end)
            
    result = query.scalar()
    return result if result is not None else Decimal('0.00')

def get_total_income(db: Session, start_date: str = None, end_date: str = None) -> Decimal:
    """
    Calculate the total income (credits) in the given date range.
    If start_date/end_date are not provided, defaults to all-time.
    """
    query = db.query(func.sum(Transaction.amount)).filter(Transaction.transaction_type == 'credit')
    if start_date:
        parsed_start = parse_date(start_date)
        if parsed_start:
            query = query.filter(Transaction.date >= parsed_start)
    if end_date:
        parsed_end = parse_date(end_date)
        if parsed_end:
            query = query.filter(Transaction.date <= parsed_end)
            
    result = query.scalar()
    return result if result is not None else Decimal('0.00')
