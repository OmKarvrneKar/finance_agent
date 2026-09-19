from sqlalchemy.orm import Session
from .db import Transaction
from typing import List, Dict, Any, Tuple
from decimal import Decimal

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
