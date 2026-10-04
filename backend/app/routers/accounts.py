from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import crud
from app.database.db import Account, User, get_db
from app.models.schemas import (
    AccountCreate,
    AccountResponse,
    AccountUpdate,
    TransactionAccountAssign,
    TransactionResponse,
)

router = APIRouter()


def _serialize(account: Account, derived: dict) -> AccountResponse:
    """Build the response from a stored account plus its derived balance."""
    return AccountResponse(
        id=account.id,
        user_id=account.user_id,
        name=account.name,
        account_type=account.account_type,
        institution_name=account.institution_name,
        last4=account.last4,
        currency=account.currency,
        opening_balance=account.opening_balance,
        current_balance=derived["current_balance"],
        balance_nature=derived["balance_nature"],
        transaction_count=derived["transaction_count"],
        is_active=account.is_active,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    account_in: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create one account owned by the authenticated user.

    Duplicate names are allowed on purpose: several accounts at the same
    institution is normal.
    """
    account = crud.create_account(
        db,
        user_id=current_user.id,
        name=account_in.name,
        account_type=account_in.account_type,
        institution_name=account_in.institution_name,
        last4=account_in.last4,
        currency=account_in.currency,
        opening_balance=account_in.opening_balance,
    )
    derived = crud.get_account_balance(db, account)
    return _serialize(account, derived)


@router.get("/accounts", response_model=List[AccountResponse])
def list_accounts(
    is_active: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every account belonging to the authenticated user, newest first."""
    accounts = crud.get_accounts(db, current_user.id, is_active=is_active)
    derived_by_id = crud.get_accounts_balances(db, accounts)
    return [
        _serialize(account, derived_by_id[account.id])
        for account in accounts
    ]


@router.get("/accounts/summary")
def get_accounts_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-account summary for the dashboard: balances and totals.

    Registered before ``/accounts/{account_id}`` so the literal path is never
    parsed as an integer id. Every figure is derived from stored transactions
    on the backend; clients only display the values returned here.
    """
    accounts = crud.get_accounts(db, current_user.id)
    derived = crud.get_accounts_balances(db, accounts)
    return [
        {
            "account_id": account.id,
            "name": account.name,
            "account_type": account.account_type,
            "currency": account.currency,
            "current_balance": derived[account.id]["current_balance"],
            "balance_nature": derived[account.id]["balance_nature"],
            "total_credits": derived[account.id]["total_credits"],
            "total_debits": derived[account.id]["total_debits"],
            "transaction_count": derived[account.id]["transaction_count"],
        }
        for account in accounts
    ]


@router.get("/accounts/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """One account. An account owned by another user is reported as 404 rather
    than 403, so this endpoint cannot be used to probe which account ids exist.
    """
    account = crud.get_account(db, account_id, current_user.id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")
    derived = crud.get_account_balance(db, account)
    return _serialize(account, derived)


@router.patch("/accounts/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int,
    account_in: AccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Partially update an account. Only supplied fields change."""
    account = crud.get_account(db, account_id, current_user.id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")

    updates = account_in.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update.")

    updated = crud.update_account(db, account_id, current_user.id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found.")

    derived = crud.get_account_balance(db, updated)
    return _serialize(updated, derived)


@router.delete("/accounts/{account_id}")
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an account. Its transactions are kept and simply become unassigned."""
    success = crud.delete_account(db, account_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found.")
    return {"message": "Account deleted successfully."}


@router.patch("/transactions/{transaction_id}/account", response_model=TransactionResponse)
def assign_transaction_account(
    transaction_id: int,
    assignment: TransactionAccountAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Associate an existing transaction with one of the caller's accounts.

    Send ``{"account_id": null}`` to detach the transaction again. This is the
    only way a transaction is ever linked: no existing transaction is assigned
    automatically, because guessing would silently misattribute history.

    Both records must belong to the caller. A transaction or account owned by
    somebody else is reported as 404 so ids cannot be probed.
    """
    transaction = crud.get_transaction(db, transaction_id, current_user.id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    if assignment.account_id is not None:
        account = crud.get_account(db, assignment.account_id, current_user.id)
        if not account:
            # Same response whether the account is missing or owned by another
            # user, so this cannot be used to discover foreign account ids.
            raise HTTPException(status_code=404, detail="Account not found.")

    updated = crud.assign_transaction_account(
        db, transaction_id, current_user.id, assignment.account_id
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return updated
