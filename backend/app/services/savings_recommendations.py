from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from typing import List, Dict, Any, Optional, Tuple
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from app.database.db import Transaction


MIN_MONTHS_FOR_RECOMMENDATIONS = 2
MIN_TRANSACTIONS_FOR_CATEGORY = 3
MIN_TRANSACTIONS_FOR_MERCHANT = 2
HIGH_SPENDING_PERCENTILE = Decimal("0.75")
SPENDING_INCREASE_THRESHOLD = Decimal("0.15")


def _get_monthly_data(
    db: Session, user_id: int, months: int = 6
) -> Tuple[List[Dict[str, Any]], int]:
    end_date = date.today()
    start_date = date(end_date.year, end_date.month, 1)
    for _ in range(months - 1):
        if start_date.month == 1:
            start_date = date(start_date.year - 1, 12, 1)
        else:
            start_date = date(start_date.year, start_date.month - 1, 1)

    txs = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.transaction_type == "debit",
    ).all()

    monthly = {}
    for t in txs:
        key = t.date.strftime("%Y-%m")
        if key not in monthly:
            monthly[key] = {}
        if t.category not in monthly[key]:
            monthly[key][t.category] = Decimal("0")
        monthly[key][t.category] += t.amount

    sorted_months = sorted(monthly.keys())
    data = []
    for m in sorted_months:
        total = sum(monthly[m].values())
        data.append({"month": m, "categories": monthly[m], "total": total})

    return data, len(data)


def _get_merchant_data(
    db: Session, user_id: int, months: int = 6
) -> List[Dict[str, Any]]:
    end_date = date.today()
    start_date = date(end_date.year, end_date.month, 1)
    for _ in range(months - 1):
        if start_date.month == 1:
            start_date = date(start_date.year - 1, 12, 1)
        else:
            start_date = date(start_date.year, start_date.month - 1, 1)

    txs = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.transaction_type == "debit",
    ).all()

    merchants: Dict[str, Dict[str, Any]] = {}
    for t in txs:
        desc = t.description.strip()
        if desc not in merchants:
            merchants[desc] = {
                "total": Decimal("0"),
                "count": 0,
                "category": t.category,
                "dates": [],
            }
        merchants[desc]["total"] += t.amount
        merchants[desc]["count"] += 1
        merchants[desc]["dates"].append(t.date)

    result = []
    for desc, data in merchants.items():
        first_date = min(data["dates"])
        last_date = max(data["dates"])
        span_months = max(
            1,
            (last_date.year - first_date.year) * 12
            + (last_date.month - first_date.month)
            + 1,
        )
        monthly_freq = Decimal(str(data["count"])) / Decimal(str(span_months))
        avg_per_visit = data["total"] / Decimal(str(data["count"])) if data["count"] > 0 else Decimal("0")
        result.append({
            "merchant": desc,
            "category": data["category"],
            "total_spent": data["total"],
            "visit_count": data["count"],
            "monthly_frequency": monthly_freq.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "average_per_visit": avg_per_visit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "months_analyzed": span_months,
        })

    return result


def _recommend_high_spending_categories(
    monthly_data: List[Dict[str, Any]], num_months: int
) -> List[Dict[str, Any]]:
    if num_months < MIN_MONTHS_FOR_RECOMMENDATIONS:
        return []

    category_totals: Dict[str, List[Decimal]] = {}
    for m in monthly_data:
        for cat, amount in m["categories"].items():
            if cat not in category_totals:
                category_totals[cat] = []
            category_totals[cat].append(amount)

    category_avgs: Dict[str, Decimal] = {}
    for cat, amounts in category_totals.items():
        total = sum(amounts)
        avg = total / Decimal(str(len(amounts)))
        category_avgs[cat] = avg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if not category_avgs:
        return []

    overall_avg = sum(category_avgs.values()) / Decimal(str(len(category_avgs)))
    overall_avg = overall_avg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if overall_avg <= 0:
        return []

    recommendations = []
    for cat, avg in category_avgs.items():
        if avg > overall_avg * HIGH_SPENDING_PERCENTILE:
            excess = avg - overall_avg
            suggested_reduction = excess * Decimal("0.20")
            monthly_savings = suggested_reduction.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            annual_savings = (monthly_savings * 12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            percent_above = ((avg - overall_avg) / overall_avg * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            recommendations.append({
                "type": "high_spending_category",
                "title": f"Reduce spending on {cat}",
                "description": (
                    f"Your average monthly spending on '{cat}' is {percent_above}% above "
                    f"your overall category average. Consider a 20% reduction."
                ),
                "estimated_monthly_savings": monthly_savings,
                "estimated_annual_savings": annual_savings,
                "confidence": "medium",
                "supporting_data": {
                    "category": cat,
                    "current_monthly_avg": str(avg),
                    "overall_category_avg": str(overall_avg),
                    "percent_above_average": str(percent_above),
                    "months_analyzed": num_months,
                },
            })

    return recommendations


def _recommend_high_frequency_merchants(
    merchant_data: List[Dict[str, Any]], num_months: int
) -> List[Dict[str, Any]]:
    if num_months < MIN_MONTHS_FOR_RECOMMENDATIONS:
        return []

    discretionary_categories = {
        "food", "dining", "restaurants", "coffee", "entertainment",
        "shopping", "subscriptions", "personal", "fitness", "travel",
    }

    recommendations = []
    for m in merchant_data:
        if m["visit_count"] < MIN_TRANSACTIONS_FOR_MERCHANT:
            continue
        if m["category"].lower() not in discretionary_categories:
            continue

        freq = m["monthly_frequency"]
        if freq < Decimal("2"):
            continue

        suggested_reduction = m["average_per_visit"] * Decimal("0.15")
        monthly_savings = suggested_reduction.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        annual_savings = (monthly_savings * 12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        recommendations.append({
            "type": "high_frequency_merchant",
            "title": f"Reduce visits to {m['merchant'][:30]}",
            "description": (
                f"You visit '{m['merchant'][:30]}' approximately {m['monthly_frequency']} times/month "
                f"with an average spend of {m['average_per_visit']} per visit. "
                f"Reducing visits by 15% could save money."
            ),
            "estimated_monthly_savings": monthly_savings,
            "estimated_annual_savings": annual_savings,
            "confidence": "medium",
            "supporting_data": {
                "merchant": m["merchant"],
                "category": m["category"],
                "visit_count": m["visit_count"],
                "monthly_frequency": str(m["monthly_frequency"]),
                "average_per_visit": str(m["average_per_visit"]),
                "months_analyzed": m["months_analyzed"],
            },
        })

    return recommendations


def _recommend_spending_increases(
    monthly_data: List[Dict[str, Any]], num_months: int
) -> List[Dict[str, Any]]:
    if num_months < 3:
        return []

    split_point = len(monthly_data) // 2
    earlier = monthly_data[:split_point]
    later = monthly_data[split_point:]

    if not earlier or not later:
        return []

    earlier_totals: Dict[str, List[Decimal]] = {}
    later_totals: Dict[str, List[Decimal]] = {}

    for m in earlier:
        for cat, amount in m["categories"].items():
            if cat not in earlier_totals:
                earlier_totals[cat] = []
            earlier_totals[cat].append(amount)

    for m in later:
        for cat, amount in m["categories"].items():
            if cat not in later_totals:
                later_totals[cat] = []
            later_totals[cat].append(amount)

    recommendations = []
    for cat in later_totals:
        if cat not in earlier_totals:
            continue

        earlier_avg = sum(earlier_totals[cat]) / Decimal(str(len(earlier_totals[cat])))
        later_avg = sum(later_totals[cat]) / Decimal(str(len(later_totals[cat])))

        if earlier_avg <= 0:
            continue

        percent_change = (later_avg - earlier_avg) / earlier_avg * 100
        if percent_change < SPENDING_INCREASE_THRESHOLD * 100:
            continue

        excess = later_avg - earlier_avg
        monthly_savings = excess.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        annual_savings = (monthly_savings * 12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        percent_increase = percent_change.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        recommendations.append({
            "type": "spending_increase",
            "title": f"Increased spending detected in {cat}",
            "description": (
                f"Your spending on '{cat}' increased by {percent_increase}% "
                f"from {earlier_avg.quantize(Decimal('0.01'))}/month to "
                f"{later_avg.quantize(Decimal('0.01'))}/month. "
                f"Review recent purchases for savings opportunities."
            ),
            "estimated_monthly_savings": monthly_savings,
            "estimated_annual_savings": annual_savings,
            "confidence": "high",
            "supporting_data": {
                "category": cat,
                "previous_monthly_avg": str(earlier_avg.quantize(Decimal("0.01"))),
                "current_monthly_avg": str(later_avg.quantize(Decimal("0.01"))),
                "percent_increase": str(percent_increase),
                "months_analyzed": num_months,
            },
        })

    return recommendations


def generate_savings_recommendations(
    db: Session, user_id: int
) -> Dict[str, Any]:
    monthly_data, num_months = _get_monthly_data(db, user_id, months=6)
    merchant_data = _get_merchant_data(db, user_id, months=6)

    recs = []
    recs.extend(_recommend_high_spending_categories(monthly_data, num_months))
    recs.extend(_recommend_high_frequency_merchants(merchant_data, num_months))
    recs.extend(_recommend_spending_increases(monthly_data, num_months))

    total_monthly = sum(r["estimated_monthly_savings"] for r in recs)
    total_annual = sum(r["estimated_annual_savings"] for r in recs)

    categories_analyzed = set()
    for m in monthly_data:
        categories_analyzed.update(m["categories"].keys())

    return {
        "recommendations": recs,
        "total_estimated_monthly_savings": total_monthly,
        "total_estimated_annual_savings": total_annual,
        "categories_analyzed": len(categories_analyzed),
        "merchants_analyzed": len(merchant_data),
        "months_of_data": num_months,
        "generated_at": datetime.utcnow(),
    }
