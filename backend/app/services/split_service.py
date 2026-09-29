from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.database.db import Transaction, TransactionSplit
from app.database import crud


class SplitValidationError(Exception):
    def __init__(self, detail: str):
        self.detail = detail


def validate_splits(
    db: Session,
    transaction_id: int,
    user_id: int,
    splits_data: List[Dict[str, Any]],
    existing_split_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    tx = crud.get_transaction(db, transaction_id, user_id)
    if not tx:
        raise SplitValidationError("Transaction not found.")

    if not splits_data:
        raise SplitValidationError("At least one split is required.")

    validated = []
    total = Decimal('0')
    categories = set()

    for i, s in enumerate(splits_data):
        amount = s.get('amount')
        category = s.get('category', '').strip()

        if not category:
            raise SplitValidationError(f"Split {i+1}: category cannot be empty.")

        if amount is None:
            raise SplitValidationError(f"Split {i+1}: amount is required.")

        try:
            amount = Decimal(str(amount))
        except Exception:
            raise SplitValidationError(f"Split {i+1}: invalid amount.")

        if amount <= 0:
            raise SplitValidationError(f"Split {i+1}: amount must be positive.")

        if category in categories:
            raise SplitValidationError(f"Split {i+1}: duplicate category '{category}'.")
        categories.add(category)

        total += amount
        validated.append({
            'category': category,
            'amount': amount,
            'description': s.get('description'),
        })

    if total != tx.amount:
        raise SplitValidationError(
            f"Split total ({total}) does not match transaction amount ({tx.amount}). "
            f"Splits must sum exactly to the transaction amount."
        )

    return validated


def get_split_summary(db: Session, transaction_id: int) -> Dict[str, Any]:
    splits = crud.get_splits_for_transaction(db, transaction_id, user_id=0)
    split_total = crud.get_split_total(db, transaction_id)
    return {
        'splits': splits,
        'split_total': split_total,
        'is_split': len(splits) > 0,
    }
