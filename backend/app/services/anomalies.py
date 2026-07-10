import math
from datetime import datetime
from collections import defaultdict
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

def detect_recurring_price_jumps(db: Session, threshold_percent: float = 20):
    txs = db.query(Transaction).filter(Transaction.is_recurring == True).order_by(Transaction.date.asc()).all()
    groups = defaultdict(list)
    for tx in txs:
        groups[normalize_merchant(tx.description)].append(tx)
        
    anomalies = []
    for merchant, group_txs in groups.items():
        if len(group_txs) < 2:
            continue
            
        previous = group_txs[:-1]
        latest = group_txs[-1]
        
        baseline = sum(tx.amount for tx in previous) / len(previous)
        if baseline == 0:
            continue
            
        increase = (latest.amount - baseline) / baseline * 100
        if increase > threshold_percent:
            anomalies.append({
                "type": "price_jump",
                "transaction_ids": [latest.id],
                "merchant": latest.description,
                "previous_amount": round(baseline, 2),
                "new_amount": round(latest.amount, 2),
                "percent_increase": round(increase, 1),
                "date": latest.date.isoformat() if latest.date else None,
                "severity": "critical" if increase > 50 else "warning",
                "message": f"Price jump: {latest.description} increased by {increase:.0f}% (from ₹{baseline:.2f} to ₹{latest.amount:.2f})."
            })
            
    return anomalies

def detect_duplicate_charges(db: Session, window_hours: int = 48):
    txs = db.query(Transaction).filter(Transaction.transaction_type == 'debit').order_by(Transaction.date.asc()).all()
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

def detect_unfamiliar_large_merchant(db: Session, std_dev_multiplier: float = 2.0, min_history_transactions: int = 10):
    txs = db.query(Transaction).filter(Transaction.transaction_type == 'debit').order_by(Transaction.date.asc()).all()
    if len(txs) < min_history_transactions:
        return []
        
    amounts = [tx.amount for tx in txs]
    mean = sum(amounts) / len(amounts)
    variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
    if variance == 0:
        return []
        
    std_dev = math.sqrt(variance)
    
    threshold = mean + (std_dev_multiplier * std_dev)
    extreme_threshold = mean + (3.0 * std_dev)
    
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
                    "amount": round(tx.amount, 2),
                    "user_avg_amount": round(mean, 2),
                    "user_std_dev": round(std_dev, 2),
                    "date": tx.date.isoformat() if tx.date else None,
                    "severity": severity,
                    "message": f"Unusually large new expense: {tx.description} for ₹{tx.amount:.2f}."
                })
        merchants_seen.add(norm)
        
    return anomalies

def generate_anomaly_report(db: Session):
    price_jumps = detect_recurring_price_jumps(db)
    duplicates = detect_duplicate_charges(db)
    unfamiliar = detect_unfamiliar_large_merchant(db)
    
    all_anomalies = price_jumps + duplicates + unfamiliar
    
    reviews = db.query(AnomalyReview).all()
    reviewed_sigs = set(r.anomaly_signature for r in reviews)
    
    filtered = []
    for a in all_anomalies:
        sig = f"{a['type']}_{'-'.join(map(str, sorted(a['transaction_ids'])))}"
        if sig not in reviewed_sigs:
            a["id"] = sig
            filtered.append(a)
            
    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    
    # Sort most recent first
    filtered.sort(key=lambda x: x.get("date") or "", reverse=True)
    # Then by severity
    filtered.sort(key=lambda x: severity_rank[x["severity"]])
    
    return filtered
