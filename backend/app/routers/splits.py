from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from decimal import Decimal

from app.database.db import get_db, User
from app.database import crud
from app.models.schemas import (
    TransactionSplitCreate, TransactionSplitUpdate, TransactionSplitResponse,
    TransactionWithSplitsResponse,
)
from app.services.split_service import validate_splits, SplitValidationError
from app.auth import get_current_user

router = APIRouter()


@router.get("/transactions/{transaction_id}/splits", response_model=List[TransactionSplitResponse])
def list_splits(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tx = crud.get_transaction(db, transaction_id, current_user.id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return crud.get_splits_for_transaction(db, transaction_id, current_user.id)


@router.post("/transactions/{transaction_id}/splits", response_model=List[TransactionSplitResponse],
             status_code=status.HTTP_201_CREATED)
def create_splits(
    transaction_id: int,
    splits: List[TransactionSplitCreate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        splits_data = [s.model_dump() for s in splits]
        validated = validate_splits(db, transaction_id, current_user.id, splits_data)
    except SplitValidationError as e:
        raise HTTPException(status_code=422, detail=e.detail)

    # Delete existing splits if any
    crud.delete_splits_for_transaction(db, transaction_id, current_user.id)

    created = crud.create_splits_batch(db, transaction_id, current_user.id, validated)
    return created


@router.put("/splits/{split_id}", response_model=TransactionSplitResponse)
def update_split(
    split_id: int,
    update: TransactionSplitUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = crud.get_split(db, split_id, current_user.id)
    if not existing:
        raise HTTPException(status_code=404, detail="Split not found.")

    update_data = update.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update.")

    # Validate total after update
    if 'amount' in update_data or 'category' in update_data:
        all_splits = crud.get_splits_for_transaction(db, existing.transaction_id, current_user.id)
        tx = crud.get_transaction(db, existing.transaction_id, current_user.id)
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found.")

        new_amount = Decimal(str(update_data.get('amount', existing.amount)))
        new_total = sum(
            new_amount if s.id == split_id else s.amount
            for s in all_splits
        )
        if new_total != tx.amount:
            raise HTTPException(
                status_code=422,
                detail=f"Split total ({new_total}) would not match transaction amount ({tx.amount}).",
            )

    updated = crud.update_split(db, split_id, current_user.id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Split not found.")
    return updated


@router.delete("/splits/{split_id}")
def delete_split(
    split_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = crud.get_split(db, split_id, current_user.id)
    if not existing:
        raise HTTPException(status_code=404, detail="Split not found.")
    crud.delete_split(db, split_id, current_user.id)
    return {"message": "Split deleted."}


@router.get("/transactions/{transaction_id}/split-summary")
def split_summary(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tx = crud.get_transaction(db, transaction_id, current_user.id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    splits = crud.get_splits_for_transaction(db, transaction_id, current_user.id)
    split_total = crud.get_split_total(db, transaction_id)

    return {
        "transaction_id": transaction_id,
        "transaction_amount": tx.amount,
        "split_count": len(splits),
        "split_total": split_total,
        "is_split": len(splits) > 0,
        "remaining": tx.amount - split_total,
        "splits": [TransactionSplitResponse.model_validate(s) for s in splits],
    }
