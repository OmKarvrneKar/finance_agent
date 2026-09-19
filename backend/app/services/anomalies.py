import math
from datetime import datetime
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN
from sqlalchemy.orm import Session
from app.database.db import Transaction, AnomalyReview
import string

def normalize_merchant(name: str) -> str:
    if not name:
        return ""
    name = name.lower()
    for p in string.punctuation:
        name = name.replace(p, " ")
    return " ".join(name.split())

def detect_recurring_price_jumps(db: Session, user_id: int, threshold_percent: float = 20):
    txs = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.is_recurring == True
    ).order_by(Transaction.date.asc()).all()
    groups = defaultdict(list)
    for tx in txs:
        groups[normalize_merchant(tx.description)].append(tx)
        
    anomalies = []
    for merchant, group_txs in groups.items():
        if len(group_txs) < 2:
            continue
            
        previous = group_txs[:-1]
        latest = group_txs[-1]
        
        baseline = sum(tx.amount for tx in previous) / Decimal(str(len(previous)))
        if baseline == 0:
            continue
            
        increase = (latest.amount - baseline) / baseline * 100
        if increase > threshold_percent:
            anomalies.append({
                "type": "price_jump",
                "transaction_ids": [latest.id],
                "merchant": latest.description,
                "previous_amount": baseline,
                "new_amount": latest.amount,
                "percent_increase": increase,
                "date": latest.date.isoformat() if latest.date else None,
                "severity": "critical" if increase > 50 else "warning",
                "message": f"Price jump: {latest.description} increased by {increase:.0f}% (from ₹{baseline:.2f} to ₹{latest.amount:.2f})."
            })
            
    return anomalies

def detect_duplicate_charges(db: Session, user_id: int, window_hours: int = 48):
    txs = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == 'debit'
    ).order_by(Transaction.date.asc()).all()
    groups = defaultdict(list)
    for tx in txs:
        groups[(normalize_merchant(tx.description), tx.amount)].append(tx)
        
    anomalies = []
    for (merchant, amount), group_txs in groups.items():
        if len(group_txs) < 2:
            continue
            
        for i in range(1, len(group_txs)):
            prev = group_txs[i-1]
            curr = group_txs[i]
            
            if prev.date and curr.date:
                gap_days = (curr.date - prev.date).days
                if gap_days <= window_hours / 24:
                    if any(tx.is_recurring for tx in [prev, curr]) and gap_days > 0:
                        continue
                        
                    anomalies.append({
                        "type": "duplicate",
                        "transaction_ids": [prev.id, curr.id],
                        "merchant": curr.description,
                        "amount": curr.amount,
                        "dates": [prev.date.isoformat(), curr.date.isoformat()],
                        "gap_hours": gap_days * 24,
                        "severity": "critical",
                        "message": f"Possible duplicate: {curr.description} charged ₹{curr.amount} twice within {gap_days} days."
                    })
    return anomalies

def detect_unfamiliar_large_merchant(db: Session, user_id: int, std_dev_multiplier: float = 2.0, min_history_transactions: int = 10):
    txs = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == 'debit'
    ).order_by(Transaction.date.asc()).all()
    if len(txs) < min_history_transactions:
        return []
        
    amounts = [tx.amount for tx in txs]
    mean = sum(amounts) / Decimal(str(len(amounts)))
    variance = sum((x - mean) ** 2 for x in amounts) / Decimal(str(len(amounts)))
    if variance == 0:
        return []
    
    std_dev = Decimal(str(math.sqrt(float(variance))))
    
    threshold = mean + (Decimal(str(std_dev_multiplier)) * std_dev)
    extreme_threshold = mean + (Decimal('3.0') * std_dev)
    
    merchants_seen = set()
    anomalies = []
    
    for tx in txs:
        norm = normalize_merchant(tx.description)
        if norm not in merchants_seen:
            if tx.amount > threshold:
                severity = "warning" if tx.amount > extreme_threshold else "info"
                anomalies.append({
                    "type": "unfamiliar_merchant",
                    "transaction_ids": [tx.id],
                    "merchant": tx.description,
                    "amount": tx.amount,
                    "user_avg_amount": mean,
                    "user_std_dev": std_dev,
                    "date": tx.date.isoformat() if tx.date else None,
                    "severity": severity,
                    "message": f"Unusually large new expense: {tx.description} for ₹{tx.amount:.2f}."
                })
        merchants_seen.add(norm)
        
    return anomalies

def generate_anomaly_report(db: Session, user_id: int):
    price_jumps = detect_recurring_price_jumps(db, user_id)
    duplicates = detect_duplicate_charges(db, user_id)
    unfamiliar = detect_unfamiliar_large_merchant(db, user_id)
    
    all_anomalies = price_jumps + duplicates + unfamiliar
    
    reviews = db.query(AnomalyReview).filter(AnomalyReview.user_id == user_id).all()
    reviewed_sigs = set(r.anomaly_signature for r in reviews)
    
    filtered = []
    for a in all_anomalies:
        sig = f"{a['type']}_{'-'.join(map(str, sorted(a['transaction_ids'])))}"
        if sig not in reviewed_sigs:
            a["id"] = sig
            filtered.append(a)
            
    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    filtered.sort(key=lambda x: x.get("date") or "", reverse=True)
    filtered.sort(key=lambda x: severity_rank[x["severity"]])
    
    return filtered
