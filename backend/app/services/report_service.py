from decimal import Decimal
from datetime import date
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.db import Transaction, TransactionSplit, BudgetGoal, SavingsGoal
from app.database.crud import get_splits_by_transaction_ids


def get_monthly_report_data(
    db: Session,
    user_id: int,
    year: int,
    month: int,
) -> Dict[str, Any]:
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)

    txs = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.date >= start_date,
        Transaction.date < end_date,
    ).all()

    total_income = Decimal('0')
    total_expenses = Decimal('0')
    category_map: Dict[str, Decimal] = {}
    merchant_map: Dict[str, Decimal] = {}
    recurring_txs: List[Dict[str, Any]] = []

    # Bulk-fetch splits for all debit transactions
    debit_tx_ids = [tx.id for tx in txs if tx.transaction_type == 'debit']
    splits_map = get_splits_by_transaction_ids(db, debit_tx_ids, user_id)

    for tx in txs:
        if tx.transaction_type == 'credit':
            total_income += tx.amount
        elif tx.transaction_type == 'debit':
            total_expenses += tx.amount
            # Split-aware: use split categories if splits exist
            if tx.id in splits_map:
                for split in splits_map[tx.id]:
                    cat = split['category'] or 'Other'
                    category_map[cat] = category_map.get(cat, Decimal('0')) + split['amount']
            else:
                cat = tx.category or 'Other'
                category_map[cat] = category_map.get(cat, Decimal('0')) + tx.amount
            # Merchant analytics: always uses transaction.description + transaction.amount
            merchant = tx.description or 'Unknown'
            merchant_map[merchant] = merchant_map.get(merchant, Decimal('0')) + tx.amount
            if tx.is_recurring:
                recurring_txs.append({
                    'description': tx.description,
                    'amount': tx.amount,
                    'category': tx.category,
                    'date': tx.date,
                })

    net_cashflow = total_income - total_expenses

    category_breakdown = [
        {"category": cat, "amount": amt}
        for cat, amt in sorted(category_map.items(), key=lambda x: x[1], reverse=True)
    ]

    top_merchants = [
        {"merchant": m, "total_spent": amt}
        for m, amt in sorted(merchant_map.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    budgets = db.query(BudgetGoal).filter(BudgetGoal.user_id == user_id).all()
    budget_status = []
    for b in budgets:
        spent = category_map.get(b.category, Decimal('0'))
        budget_status.append({
            'category': b.category,
            'monthly_cap': b.monthly_cap,
            'spent': spent,
            'remaining': b.monthly_cap - spent,
            'utilization': float(spent / b.monthly_cap * 100) if b.monthly_cap > 0 else 0,
        })

    goals = db.query(SavingsGoal).filter(
        SavingsGoal.user_id == user_id,
        SavingsGoal.status == 'active',
    ).all()
    savings_progress = []
    for g in goals:
        progress = float(g.current_amount / g.target_amount * 100) if g.target_amount > 0 else 0
        savings_progress.append({
            'name': g.name,
            'target_amount': g.target_amount,
            'current_amount': g.current_amount,
            'progress_percent': round(progress, 1),
            'target_date': g.target_date.isoformat() if g.target_date else None,
        })

    return {
        'year': year,
        'month': month,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'net_cashflow': net_cashflow,
        'transaction_count': len(txs),
        'category_breakdown': category_breakdown,
        'top_merchants': top_merchants,
        'recurring_expenses': recurring_txs,
        'budget_status': budget_status,
        'savings_progress': savings_progress,
    }
