from sqlalchemy.orm import Session
from sqlalchemy import func
from .db import (
    Transaction, TransactionSplit, SavingsGoal, SavingsGoalContribution, Notification,
)
from typing import List, Dict, Any, Tuple, Optional, Sequence
from decimal import Decimal
from datetime import date, datetime

def create_transactions(db: Session, transactions: List[Dict[str, Any]], user_id: int) -> Tuple[List[Transaction], int]:
    db_transactions = []
    duplicate_count = 0
    for tx in transactions:
        exists = db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.date == tx['date'],
            Transaction.description == tx['description'],
            Transaction.amount == Decimal(str(tx['amount'])),
            Transaction.transaction_type == tx['transaction_type']
        ).first()

        if exists:
            duplicate_count += 1
            continue

        db_tx = Transaction(
            user_id=user_id,
            date=tx['date'],
            description=tx['description'],
            amount=tx['amount'],
            transaction_type=tx['transaction_type'],
            category=tx['category'],
            subcategory=tx.get('subcategory'),
            is_recurring=tx.get('is_recurring', False),
            raw_text=tx.get('raw_text')
        )
        db.add(db_tx)
        db_transactions.append(db_tx)
    db.commit()
    for db_tx in db_transactions:
        db.refresh(db_tx)
    return db_transactions, duplicate_count

def get_transactions_paginated(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    category: str = None,
    transaction_type: str = None,
    search: str = None,
    start_date: str = None,
    end_date: str = None,
    amount_min: Decimal = None,
    amount_max: Decimal = None,
) -> Tuple[List[Transaction], int]:
    query = db.query(Transaction).filter(Transaction.user_id == user_id)
    if category:
        query = query.filter(Transaction.category == category)
    if transaction_type:
        query = query.filter(Transaction.transaction_type == transaction_type)
    if search:
        query = query.filter(Transaction.description.ilike(f"%{search}%"))
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if amount_min is not None:
        query = query.filter(Transaction.amount >= amount_min)
    if amount_max is not None:
        query = query.filter(Transaction.amount <= amount_max)

    query = query.order_by(Transaction.date.desc(), Transaction.id.desc())
    total = query.count()
    transactions = query.offset(skip).limit(limit).all()
    return transactions, total

def get_distinct_categories(db: Session, user_id: int) -> List[str]:
    rows = (
        db.query(Transaction.category)
        .filter(Transaction.user_id == user_id)
        .distinct()
        .all()
    )
    return [r[0] for r in rows]

def update_transaction(db: Session, transaction_id: int, user_id: int, updates: Dict[str, Any]) -> Transaction:
    tx = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
    ).first()
    if not tx:
        return None
    for key, value in updates.items():
        if hasattr(tx, key) and value is not None:
            if key == "date":
                if isinstance(value, str):
                    try:
                        value = datetime.strptime(value, "%Y-%m-%d").date()
                    except ValueError:
                        raise ValueError(f"Invalid date format: '{value}'. Expected YYYY-MM-DD.")
                elif isinstance(value, date) and not isinstance(value, datetime):
                    pass  # already a date object
                else:
                    raise ValueError(f"Invalid date value: {value}")
            setattr(tx, key, value)
    db.commit()
    db.refresh(tx)
    return tx

def delete_transaction(db: Session, transaction_id: int, user_id: int) -> bool:
    tx = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
    ).first()
    if not tx:
        return False
    db.delete(tx)
    db.commit()
    return True


def get_recurring_transactions(db: Session, user_id: int) -> List[Transaction]:
    return db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.is_recurring == True,
        Transaction.transaction_type == 'debit'
    ).order_by(Transaction.date.desc()).all()


def mark_recurring(db: Session, transaction_id: int, user_id: int) -> Transaction:
    tx = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
    ).first()
    if not tx:
        return None
    tx.is_recurring = True
    tx.is_user_confirmed_recurring = True
    db.commit()
    db.refresh(tx)
    return tx


def unmark_recurring(db: Session, transaction_id: int, user_id: int) -> Transaction:
    tx = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
    ).first()
    if not tx:
        return None
    tx.is_recurring = False
    tx.is_user_confirmed_recurring = False
    db.commit()
    db.refresh(tx)
    return tx


def get_analytics_summary(
    db: Session,
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    query = db.query(Transaction).filter(Transaction.user_id == user_id)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)

    txs = query.all()

    total_income = Decimal('0')
    total_expenses = Decimal('0')
    category_map: Dict[str, Decimal] = {}

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

    net_cashflow = total_income - total_expenses

    category_breakdown = [
        {"category": cat, "amount": amt}
        for cat, amt in sorted(category_map.items(), key=lambda x: x[1], reverse=True)
    ]

    # Spending trend: group debits by month (uses original transaction.amount — no double-count)
    debit_query = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == 'debit',
    )
    if start_date:
        debit_query = debit_query.filter(Transaction.date >= start_date)
    if end_date:
        debit_query = debit_query.filter(Transaction.date <= end_date)

    debit_txs = debit_query.all()
    monthly_spending: Dict[str, Decimal] = {}
    for tx in debit_txs:
        month_key = tx.date.strftime('%Y-%m')
        monthly_spending[month_key] = monthly_spending.get(month_key, Decimal('0')) + tx.amount

    spending_trend = [
        {"month": m, "amount": amt}
        for m, amt in sorted(monthly_spending.items())
    ]

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_cashflow": net_cashflow,
        "transaction_count": len(txs),
        "category_breakdown": category_breakdown,
        "spending_trend": spending_trend,
    }


# --- Savings Goal CRUD ---

def create_savings_goal(db: Session, user_id: int, name: str, target_amount: Decimal,
                        target_date=None, description=None) -> SavingsGoal:
    goal = SavingsGoal(
        user_id=user_id,
        name=name,
        target_amount=target_amount,
        current_amount=Decimal('0'),
        target_date=target_date,
        description=description,
        status='active',
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def get_savings_goals(db: Session, user_id: int, status: str = None) -> List[SavingsGoal]:
    query = db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id)
    if status:
        query = query.filter(SavingsGoal.status == status)
    return query.order_by(SavingsGoal.created_at.desc()).all()


def get_savings_goal(db: Session, goal_id: int, user_id: int) -> Optional[SavingsGoal]:
    return db.query(SavingsGoal).filter(
        SavingsGoal.id == goal_id,
        SavingsGoal.user_id == user_id,
    ).first()


def update_savings_goal(db: Session, goal_id: int, user_id: int, updates: Dict[str, Any]) -> Optional[SavingsGoal]:
    goal = db.query(SavingsGoal).filter(
        SavingsGoal.id == goal_id,
        SavingsGoal.user_id == user_id,
    ).first()
    if not goal:
        return None
    for key, value in updates.items():
        if hasattr(goal, key) and value is not None:
            if key == "target_date" and isinstance(value, str):
                try:
                    value = datetime.strptime(value, "%Y-%m-%d").date()
                except ValueError:
                    pass
            setattr(goal, key, value)
    if goal.current_amount >= goal.target_amount and goal.status == 'active':
        goal.status = 'completed'
    db.commit()
    db.refresh(goal)
    return goal


def delete_savings_goal(db: Session, goal_id: int, user_id: int) -> bool:
    goal = db.query(SavingsGoal).filter(
        SavingsGoal.id == goal_id,
        SavingsGoal.user_id == user_id,
    ).first()
    if not goal:
        return False
    db.delete(goal)
    db.commit()
    return True


def contribute_to_savings_goal(db: Session, goal_id: int, user_id: int, amount: Decimal) -> Optional[SavingsGoal]:
    if amount <= 0:
        return None
    goal = db.query(SavingsGoal).filter(
        SavingsGoal.id == goal_id,
        SavingsGoal.user_id == user_id,
    ).first()
    if not goal:
        return None
    goal.current_amount = (goal.current_amount or Decimal('0')) + amount
    if goal.current_amount >= goal.target_amount:
        goal.status = 'completed'
    # Record when the money actually arrived so a contribution rate can be
    # measured later. The aggregate above remains the progress source of truth.
    db.add(SavingsGoalContribution(goal_id=goal.id, user_id=user_id, amount=amount))
    db.commit()
    db.refresh(goal)
    return goal


def add_savings_goal_contribution(
    db: Session,
    goal_id: int,
    user_id: int,
    amount: Decimal,
    contributed_at: Optional[datetime] = None,
) -> Optional[SavingsGoalContribution]:
    """Append a contribution ledger row for an existing, owned goal."""
    goal = db.query(SavingsGoal).filter(
        SavingsGoal.id == goal_id,
        SavingsGoal.user_id == user_id,
    ).first()
    if not goal:
        return None
    contribution = SavingsGoalContribution(
        goal_id=goal_id,
        user_id=user_id,
        amount=amount,
    )
    if contributed_at is not None:
        contribution.contributed_at = contributed_at
    db.add(contribution)
    db.commit()
    db.refresh(contribution)
    return contribution


def get_savings_goal_contributions(
    db: Session, goal_id: int, user_id: int
) -> List[SavingsGoalContribution]:
    """Contribution history for one owned goal, oldest first."""
    return (
        db.query(SavingsGoalContribution)
        .filter(
            SavingsGoalContribution.goal_id == goal_id,
            SavingsGoalContribution.user_id == user_id,
        )
        .order_by(SavingsGoalContribution.contributed_at.asc())
        .all()
    )


def get_savings_goal_contributions_bulk(
    db: Session, user_id: int, goal_ids: Sequence[int]
) -> Dict[int, List[SavingsGoalContribution]]:
    """Contribution history for many owned goals in a single query.

    Returns ``{goal_id: [contribution, ...]}`` with each list ordered oldest
    first, matching :func:`get_savings_goal_contributions`. Goals with no rows
    are present with an empty list, so callers never need a per-goal query to
    discover that history is missing.
    """
    grouped: Dict[int, List[SavingsGoalContribution]] = {
        goal_id: [] for goal_id in goal_ids
    }
    if not goal_ids:
        return grouped

    rows = (
        db.query(SavingsGoalContribution)
        .filter(
            SavingsGoalContribution.user_id == user_id,
            SavingsGoalContribution.goal_id.in_(list(goal_ids)),
        )
        .order_by(
            SavingsGoalContribution.goal_id.asc(),
            SavingsGoalContribution.contributed_at.asc(),
        )
        .all()
    )
    for row in rows:
        grouped.setdefault(row.goal_id, []).append(row)
    return grouped


def get_savings_goals_summary(db: Session, user_id: int) -> Dict[str, Any]:
    goals = db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).all()
    active = [g for g in goals if g.status == 'active']
    completed = [g for g in goals if g.status == 'completed']
    total_target = sum((g.target_amount or Decimal('0')) for g in goals)
    total_saved = sum((g.current_amount or Decimal('0')) for g in goals)
    return {
        "total_goals": len(goals),
        "active_goals": len(active),
        "completed_goals": len(completed),
        "total_target": total_target,
        "total_saved": total_saved,
        "overall_progress": float(total_saved / total_target * 100) if total_target > 0 else 0,
    }


# --- Transaction Split CRUD ---

def get_transaction(db: Session, transaction_id: int, user_id: int) -> Optional[Transaction]:
    return db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
    ).first()


def get_splits_for_transaction(db: Session, transaction_id: int, user_id: int) -> List[TransactionSplit]:
    return db.query(TransactionSplit).filter(
        TransactionSplit.transaction_id == transaction_id,
        TransactionSplit.user_id == user_id,
    ).order_by(TransactionSplit.id).all()


def get_split(db: Session, split_id: int, user_id: int) -> Optional[TransactionSplit]:
    return db.query(TransactionSplit).filter(
        TransactionSplit.id == split_id,
        TransactionSplit.user_id == user_id,
    ).first()


def create_split(db: Session, transaction_id: int, user_id: int, category: str,
                 amount: Decimal, description: Optional[str] = None) -> TransactionSplit:
    split = TransactionSplit(
        transaction_id=transaction_id,
        user_id=user_id,
        category=category,
        amount=amount,
        description=description,
    )
    db.add(split)
    db.commit()
    db.refresh(split)
    return split


def create_splits_batch(db: Session, transaction_id: int, user_id: int,
                        splits_data: List[Dict[str, Any]]) -> List[TransactionSplit]:
    db_splits = []
    for s in splits_data:
        split = TransactionSplit(
            transaction_id=transaction_id,
            user_id=user_id,
            category=s['category'],
            amount=s['amount'],
            description=s.get('description'),
        )
        db.add(split)
        db_splits.append(split)
    db.commit()
    for s in db_splits:
        db.refresh(s)
    return db_splits


def update_split(db: Session, split_id: int, user_id: int, updates: Dict[str, Any]) -> Optional[TransactionSplit]:
    split = db.query(TransactionSplit).filter(
        TransactionSplit.id == split_id,
        TransactionSplit.user_id == user_id,
    ).first()
    if not split:
        return None
    for key, value in updates.items():
        if hasattr(split, key) and value is not None:
            setattr(split, key, value)
    db.commit()
    db.refresh(split)
    return split


def delete_split(db: Session, split_id: int, user_id: int) -> bool:
    split = db.query(TransactionSplit).filter(
        TransactionSplit.id == split_id,
        TransactionSplit.user_id == user_id,
    ).first()
    if not split:
        return False
    db.delete(split)
    db.commit()
    return True


def delete_splits_for_transaction(db: Session, transaction_id: int, user_id: int) -> int:
    splits = db.query(TransactionSplit).filter(
        TransactionSplit.transaction_id == transaction_id,
        TransactionSplit.user_id == user_id,
    ).all()
    count = len(splits)
    for s in splits:
        db.delete(s)
    db.commit()
    return count


def get_split_total(db: Session, transaction_id: int) -> Decimal:
    result = db.query(func.sum(TransactionSplit.amount)).filter(
        TransactionSplit.transaction_id == transaction_id,
    ).scalar()
    return result or Decimal('0')


def get_splits_by_transaction_ids(
    db: Session, transaction_ids: List[int], user_id: int
) -> Dict[int, List[Dict[str, Any]]]:
    if not transaction_ids:
        return {}
    splits = db.query(TransactionSplit).filter(
        TransactionSplit.transaction_id.in_(transaction_ids),
        TransactionSplit.user_id == user_id,
    ).all()
    result: Dict[int, List[Dict[str, Any]]] = {}
    for s in splits:
        if s.transaction_id not in result:
            result[s.transaction_id] = []
        result[s.transaction_id].append({
            'category': s.category,
            'amount': s.amount,
        })
    return result


# --- Notification CRUD ---

def get_notifications_paginated(
    db: Session,
    user_id: int,
    page: int = 1,
    limit: int = 20,
    unread_only: bool = False,
    type_filter: Optional[str] = None,
) -> Tuple[List[Notification], int]:
    """List a user's notifications, newest first."""
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.is_read == False)  # noqa: E712
    if type_filter:
        query = query.filter(Notification.type == type_filter)
    total = query.count()
    notifications = (
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return notifications, total


def get_notification(
    db: Session, notification_id: int, user_id: int
) -> Optional[Notification]:
    return db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user_id,
    ).first()


def get_notification_by_event_key(
    db: Session, user_id: int, event_key: Optional[str]
) -> Optional[Notification]:
    if not event_key:
        return None
    return db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.event_key == event_key,
    ).first()


def create_notification(
    db: Session,
    user_id: int,
    type: str,
    title: str,
    message: str,
    severity: str = "info",
    related_entity_type: Optional[str] = None,
    related_entity_id: Optional[int] = None,
    event_key: Optional[str] = None,
    metadata_json: Optional[str] = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        severity=severity,
        is_read=False,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        event_key=event_key,
        metadata_json=metadata_json,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def set_notification_read(
    db: Session, notification: Notification, is_read: bool = True
) -> Notification:
    notification.is_read = is_read
    db.commit()
    db.refresh(notification)
    return notification


def mark_all_notifications_read(db: Session, user_id: int) -> int:
    """Mark every unread notification for the user as read. Returns count updated."""
    unread = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,  # noqa: E712
    )
    count = unread.count()
    unread.update({Notification.is_read: True}, synchronize_session=False)
    db.commit()
    return count


def delete_notification(db: Session, notification: Notification) -> bool:
    db.delete(notification)
    db.commit()
    return True


def count_unread_notifications(db: Session, user_id: int) -> int:
    return db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,  # noqa: E712
    ).count()
