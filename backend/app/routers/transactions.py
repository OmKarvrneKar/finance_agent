from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy.orm import Session
from typing import Dict, Any, List
import logging

from app.database.db import get_db
from app.database import crud
from app.services.csv_parser import parse_bank_csv
from app.services.categorizer import categorize_transactions
from app.models.schemas import UploadSummaryResponse, PaginatedTransactionsResponse

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/upload-statement", response_model=UploadSummaryResponse)
async def upload_statement(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Validate file extension
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only CSV files are supported."
        )
        
    try:
        file_bytes = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {str(e)}"
        )
        
    if not file_bytes or len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded CSV file is empty."
        )
        
    # 1. Parse CSV
    try:
        parsed_transactions = parse_bank_csv(file_bytes)
    except ValueError as e:
        logger.error(f"CSV Parsing failure: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"CSV parsing failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected CSV parsing failure: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected parsing error occurred: {str(e)}"
        )
        
    if not parsed_transactions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid transactions could be parsed from the CSV file."
        )
        
    # 2. Categorize using AI
    try:
        categorized_transactions = categorize_transactions(parsed_transactions)
    except ValueError as e:
        logger.error(f"Gemini Configuration Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gemini API is not configured properly: {str(e)}"
        )
    except RuntimeError as e:
        logger.error(f"Gemini API failure: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Transaction categorization failed via AI API: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected categorization failure: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during categorization: {str(e)}"
        )
        
    # 3. Save to database
    try:
        db_txs, duplicates = crud.create_transactions(db, categorized_transactions)
    except Exception as e:
        logger.error(f"Database insertion error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save transactions to database: {str(e)}"
        )
        
    # 4. Generate summary
    total_tx = len(db_txs)
    total_spent = sum(tx.amount for tx in db_txs if tx.transaction_type == 'debit')
    
    category_counts = {}
    for tx in db_txs:
        cat = tx.category
        category_counts[cat] = category_counts.get(cat, 0) + 1
        
    return {
        "total_transactions": total_tx,
        "total_spent": round(total_spent, 2),
        "category_breakdown": category_counts,
        "new_transactions": total_tx,
        "duplicate_transactions": duplicates,
        "total_in_file": len(categorized_transactions)
    }

@router.get("/transactions", response_model=PaginatedTransactionsResponse)
def get_transactions(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=10000, description="Transactions per page"),
    category: str = Query(None, description="Filter by category"),
    transaction_type: str = Query(None, description="Filter by transaction type"),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * limit
    try:
        transactions, total = crud.get_transactions_paginated(
            db, skip=skip, limit=limit, category=category, transaction_type=transaction_type
        )
    except Exception as e:
        logger.error(f"Database query error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query transactions from database: {str(e)}"
        )
        
    pages = (total + limit - 1) // limit if total > 0 else 1
    
    return {
        "transactions": transactions,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages
    }

@router.get("/subscriptions")
def get_subscriptions(db: Session = Depends(get_db)):
    from app.database.db import Transaction
    import datetime
    
    recurring_txs = db.query(Transaction).filter(
        Transaction.is_recurring == True,
        Transaction.transaction_type == 'debit'
    ).all()
    
    grouped = {}
    for tx in recurring_txs:
        if not tx.description: continue
        desc = tx.description.lower().strip()
        if desc not in grouped:
            grouped[desc] = []
        grouped[desc].append(tx)
        
    results = []
    for desc, txs in grouped.items():
        occurrences = len(txs)
        total_amount = sum(tx.amount for tx in txs)
        avg_amount = total_amount / occurrences
        
        valid_dates = []
        for tx in txs:
            if tx.date is not None:
                if hasattr(tx.date, "isoformat"):
                    valid_dates.append(tx.date)
                elif isinstance(tx.date, str):
                    try:
                        valid_dates.append(datetime.datetime.strptime(tx.date, "%Y-%m-%d").date())
                    except ValueError:
                        pass
        
        sorted_dates = sorted(valid_dates)
        
        distinct_months = len(set((d.year, d.month) for d in valid_dates))
        distinct_months = distinct_months if distinct_months > 0 else 1
        
        charges_per_month = occurrences / distinct_months
        
        if charges_per_month >= 3.5:
            frequency = "Weekly"
            monthly_cost = avg_amount * 4.33
        elif charges_per_month >= 1.5:
            frequency = "Bi-weekly"
            monthly_cost = avg_amount * 2.16
        elif charges_per_month >= 0.8:
            frequency = "Monthly"
            monthly_cost = avg_amount
        elif charges_per_month >= 0.3:
            frequency = "Quarterly"
            monthly_cost = avg_amount / 3.0
        else:
            frequency = "Yearly"
            monthly_cost = avg_amount / 12.0
            
        results.append({
            "description": txs[0].description,
            "category": txs[0].category,
            "occurrences": occurrences,
            "average_amount": round(avg_amount, 2),
            "frequency": frequency,
            "estimated_monthly_cost": round(monthly_cost, 2),
            "estimated_annual_cost": round(monthly_cost * 12, 2),
            "last_seen": sorted_dates[-1].isoformat() if sorted_dates else "Unknown"
        })
        
    results.sort(key=lambda x: x["estimated_monthly_cost"], reverse=True)
    return results
