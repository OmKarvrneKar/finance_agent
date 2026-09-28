from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.db import Transaction


def get_merchant_analytics(
    db: Session,
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    query = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == "debit",
    )

    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if search:
        query = query.filter(Transaction.description.ilike(f"%{search}%"))

    txs = query.all()

    if not txs:
        return {
            "merchants": [],
            "total_merchants": 0,
            "total_expenses": Decimal("0"),
            "date_range": {
                "start_date": start_date,
                "end_date": end_date,
            },
        }

    total_expenses = sum(t.amount for t in txs)

    merchant_data: Dict[str, Dict[str, Any]] = {}
    for t in txs:
        desc = t.description.strip()
        if desc not in merchant_data:
            merchant_data[desc] = {
                "total": Decimal("0"),
                "count": 0,
                "amounts": [],
                "dates": [],
                "category": t.category,
            }
        merchant_data[desc]["total"] += t.amount
        merchant_data[desc]["count"] += 1
        merchant_data[desc]["amounts"].append(t.amount)
        merchant_data[desc]["dates"].append(t.date)
        if t.category:
            merchant_data[desc]["category"] = t.category

    merchants = []
    for desc, data in merchant_data.items():
        avg = data["total"] / Decimal(str(data["count"])) if data["count"] > 0 else Decimal("0")
        largest = max(data["amounts"]) if data["amounts"] else Decimal("0")
        pct = (data["total"] / total_expenses * 100) if total_expenses > 0 else Decimal("0")

        merchants.append({
            "merchant": desc,
            "total_spent": data["total"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "transaction_count": data["count"],
            "average_amount": avg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "largest_transaction": largest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "spending_percent": pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "first_seen": min(data["dates"]).isoformat(),
            "last_seen": max(data["dates"]).isoformat(),
            "category": data["category"],
        })

    merchants.sort(key=lambda m: m["total_spent"], reverse=True)
    merchants = merchants[:limit]

    return {
        "merchants": merchants,
        "total_merchants": len(merchants),
        "total_expenses": total_expenses.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "date_range": {
            "start_date": start_date,
            "end_date": end_date,
        },
    }
