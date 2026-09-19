from sqlalchemy.orm import Session
from .db import Transaction
from typing import List, Dict, Any, Tuple
from decimal import Decimal

def create_transactions(db: Session, transactions: List[Dict[str, Any]]) -> Tuple[List[Transaction], int]:
    db_transactions = []
    duplicate_count = 0
    for tx in transactions:
        exists = db.query(Transaction).filter(
            Transaction.date == tx['date'],
            Transaction.description == tx['description'],
            Transaction.amount == Decimal(str(tx['amount'])),
            Transaction.transaction_type == tx['transaction_type']
        ).first()
        
        if exists:
            duplicate_count += 1
            continue
            
        db_tx = Transaction(
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

def get_transactions_paginated(db: Session, skip: int = 0, limit: int = 100, category: str = None, transaction_type: str = None) -> Tuple[List[Transaction], int]:
    query = db.query(Transaction)
    if category:
        query = query.filter(Transaction.category == category)
    if transaction_type:
        query = query.filter(Transaction.transaction_type == transaction_type)
        
    query = query.order_by(Transaction.date.desc(), Transaction.id.desc())
    total = query.count()
    transactions = query.offset(skip).limit(limit).all()
    return transactions, total
