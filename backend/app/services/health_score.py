from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from app.database.db import Transaction, BudgetGoal

INSUFFICIENT_DATA = "insufficient_data"

def _get_monthly_income_expense(db: Session, user_id: int, num_months: int = 6) -> List[Dict[str, Any]]:
    end_date = date.today()
    start_date = date(end_date.year - 1, end_date.month, 1)

    txs = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
    ).all()

    monthly = {}
    for t in txs:
        key = t.date.strftime("%Y-%m")
        if key not in monthly:
            monthly[key] = {"income": Decimal("0"), "expense": Decimal("0")}
        if t.transaction_type == "credit":
            monthly[key]["income"] += t.amount
        elif t.transaction_type == "debit":
            monthly[key]["expense"] += t.amount

    sorted_months = sorted(monthly.keys(), reverse=True)[:num_months]
    return [{"month": m, **monthly[m]} for m in sorted_months]


def _calculate_savings_rate(monthly_data: List[Dict[str, Any]]) -> Optional[Decimal]:
    total_income = sum(m["income"] for m in monthly_data)
    total_expense = sum(m["expense"] for m in monthly_data)

    if total_income <= 0:
        return Decimal("0")

    rate = ((total_income - total_expense) / total_income) * 100
    return rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _interpolate_linear(x: Decimal, x1: Decimal, y1: Decimal, x2: Decimal, y2: Decimal) -> Decimal:
    """Linear interpolation between two points (x1,y1) and (x2,y2) at position x."""
    if x2 == x1:
        return y1
    slope = (y2 - y1) / (x2 - x1)
    return y1 + (x - x1) * slope


def _score_savings_rate(rate: Optional[Decimal]) -> Optional[Decimal]:
    """
    Piecewise linear scoring of savings rate (as percentage).
    
    Thresholds:
        <= 0%  -> 0
        5%     -> 25
        10%    -> 50
        20%    -> 75
        >= 30% -> 100
    
    Linear interpolation between thresholds.
    Returns None if rate is None.
    """
    if rate is None:
        return None
    rate = max(rate, Decimal("0"))
    if rate >= Decimal("30"):
        return Decimal("100")
    if rate >= Decimal("20"):
        return _interpolate_linear(rate, Decimal("20"), Decimal("75"), Decimal("30"), Decimal("100"))
    if rate >= Decimal("10"):
        return _interpolate_linear(rate, Decimal("10"), Decimal("50"), Decimal("20"), Decimal("75"))
    if rate >= Decimal("5"):
        return _interpolate_linear(rate, Decimal("5"), Decimal("25"), Decimal("10"), Decimal("50"))
    return _interpolate_linear(rate, Decimal("0"), Decimal("0"), Decimal("5"), Decimal("25"))


def _calculate_budget_adherence(db: Session, user_id: int, monthly_data: List[Dict[str, Any]]) -> Optional[Decimal]:
    budgets = db.query(BudgetGoal).filter(BudgetGoal.user_id == user_id).all()
    if not budgets:
        return None

    if not monthly_data:
        return Decimal("0")

    latest_month = monthly_data[0]
    month_expenses = {}
    txs = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == "debit",
        extract("year", Transaction.date) == int(latest_month["month"][:4]),
        extract("month", Transaction.date) == int(latest_month["month"][5:7]),
    ).all()

    for t in txs:
        cat = t.category.lower()
        month_expenses[cat] = month_expenses.get(cat, Decimal("0")) + t.amount

    on_track = 0
    total = 0
    for b in budgets:
        cat = b.category.lower()
        spent = month_expenses.get(cat, Decimal("0"))
        if spent <= b.monthly_cap:
            on_track += 1
        total += 1

    if total == 0:
        return None

    return (Decimal(str(on_track)) / Decimal(str(total))) * 100


def _score_budget_adherence(adherence: Optional[Decimal]) -> Optional[Decimal]:
    """Budget adherence score: percentage of budgets on track (0-100), or None if no budgets."""
    if adherence is None:
        return None
    return adherence.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _calculate_income_stability(monthly_data: List[Dict[str, Any]]) -> Optional[Decimal]:
    incomes = [m["income"] for m in monthly_data if m["income"] > 0]
    if len(incomes) < 2:
        return None

    mean_income = sum(incomes) / Decimal(str(len(incomes)))
    if mean_income == 0:
        return Decimal("0")

    variance = sum((i - mean_income) ** 2 for i in incomes) / Decimal(str(len(incomes)))
    std_dev = variance.sqrt()
    cv = (std_dev / mean_income) * 100

    stability = max(Decimal("100") - cv, Decimal("0"))
    return stability.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _score_income_stability(stability: Optional[Decimal]) -> Optional[Decimal]:
    """Income stability score (0-100), or None if insufficient data."""
    if stability is None:
        return None
    return stability.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _calculate_spending_consistency(monthly_data: List[Dict[str, Any]]) -> Optional[Decimal]:
    expenses = [m["expense"] for m in monthly_data if m["expense"] > 0]
    if len(expenses) < 2:
        return None

    mean_expense = sum(expenses) / Decimal(str(len(expenses)))
    if mean_expense == 0:
        return Decimal("0")

    variance = sum((e - mean_expense) ** 2 for e in expenses) / Decimal(str(len(expenses)))
    std_dev = variance.sqrt()
    cv = (std_dev / mean_expense) * 100

    consistency = max(Decimal("100") - cv, Decimal("0"))
    return consistency.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _score_spending_consistency(consistency: Optional[Decimal]) -> Optional[Decimal]:
    """Spending consistency score (0-100), or None if insufficient data."""
    if consistency is None:
        return None
    return consistency.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_health_score(db: Session, user_id: int) -> Dict[str, Any]:
    monthly_data = _get_monthly_income_expense(db, user_id, num_months=6)

    has_income = any(m["income"] > 0 for m in monthly_data)
    has_expense = any(m["expense"] > 0 for m in monthly_data)
    has_enough_data = len(monthly_data) >= 2 and has_income and has_expense

    savings_rate = _calculate_savings_rate(monthly_data) if has_enough_data else None
    budget_adherence = _calculate_budget_adherence(db, user_id, monthly_data) if has_enough_data else None
    income_stability = _calculate_income_stability(monthly_data) if has_enough_data else None
    spending_consistency = _calculate_spending_consistency(monthly_data) if has_enough_data else None

    score_savings = _score_savings_rate(savings_rate)
    score_budget = _score_budget_adherence(budget_adherence)
    score_income = _score_income_stability(income_stability)
    score_spending = _score_spending_consistency(spending_consistency)

    has_score = has_enough_data
    
    # Define base weights
    weights = {
        "savings_rate": Decimal("0.40"),
        "budget_adherence": Decimal("0.25"),
        "income_stability": Decimal("0.20"),
        "spending_consistency": Decimal("0.15"),
    }
    
    # Identify which components have scores (not None)
    scored_components = {}
    if score_savings is not None:
        scored_components["savings_rate"] = score_savings
    if score_budget is not None:
        scored_components["budget_adherence"] = score_budget
    if score_income is not None:
        scored_components["income_stability"] = score_income
    if score_spending is not None:
        scored_components["spending_consistency"] = score_spending
    
    if has_score and scored_components:
        # Calculate total weight of scored components
        total_weight = sum(weights[k] for k in scored_components)
        
        # Compute weighted average with redistributed weights
        overall = Decimal("0")
        for k, score in scored_components.items():
            redistributed_weight = weights[k] / total_weight
            overall += score * redistributed_weight
        overall = overall.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        overall = None

    # Calculate effective weights for display
    if has_score and scored_components:
        total_weight = sum(weights[k] for k in scored_components)
        effective_weights = {k: (weights[k] / total_weight * 100).quantize(Decimal("0.01")) for k in scored_components}
    else:
        effective_weights = {}

    def _desc(component, value, raw):
        if not has_score:
            return f"Insufficient data to calculate {component}."
        if component == "savings_rate":
            if raw is None:
                return "No income data available."
            ew = effective_weights.get("savings_rate", weights["savings_rate"] * 100)
            return f"Savings rate: {raw}%. Higher is better (30%+ = excellent). Weight: {ew}%."
        if component == "budget_adherence":
            if raw is None:
                return "No budgets set. Weight redistributed to other components."
            ew = effective_weights.get("budget_adherence", weights["budget_adherence"] * 100)
            return f"Budget adherence: {raw}% of budgets on track. Weight: {ew}%."
        if component == "income_stability":
            if raw is None:
                return "Not enough income months to measure stability."
            ew = effective_weights.get("income_stability", weights["income_stability"] * 100)
            return f"Income stability: {raw}/100 (lower variation = higher score). Weight: {ew}%."
        if component == "spending_consistency":
            if raw is None:
                return "Not enough spending months to measure consistency."
            ew = effective_weights.get("spending_consistency", weights["spending_consistency"] * 100)
            return f"Spending consistency: {raw}/100 (lower variation = higher score). Weight: {ew}%."
        return ""

    return {
        "overall_score": overall,
        "insufficient_data": not has_score,
        "components": {
            "savings_rate": {
                "score": score_savings if has_score else None,
                "raw_value": savings_rate,
                "weight": f"{effective_weights.get('savings_rate', weights['savings_rate'] * 100)}%",
                "description": _desc("savings_rate", score_savings, savings_rate),
            },
            "budget_adherence": {
                "score": score_budget if has_score else None,
                "raw_value": budget_adherence,
                "weight": f"{effective_weights.get('budget_adherence', weights['budget_adherence'] * 100)}%" if score_budget is not None else "0% (no budgets)",
                "description": _desc("budget_adherence", score_budget, budget_adherence),
            },
            "income_stability": {
                "score": score_income if has_score else None,
                "raw_value": income_stability,
                "weight": f"{effective_weights.get('income_stability', weights['income_stability'] * 100)}%",
                "description": _desc("income_stability", score_income, income_stability),
            },
            "spending_consistency": {
                "score": score_spending if has_score else None,
                "raw_value": spending_consistency,
                "weight": f"{effective_weights.get('spending_consistency', weights['spending_consistency'] * 100)}%",
                "description": _desc("spending_consistency", score_spending, spending_consistency),
            },
        },
        "formula": {
            "overall": "weighted_average(score_savings * w_savings + score_budget * w_budget + score_income * w_income + score_spending * w_spending) / sum(active_weights)",
            "savings_rate_score": "piecewise_linear: 0%->0, 5%->25, 10%->50, 20%->75, 30%+->100",
            "budget_adherence_score": "percentage_of_budgets_on_track (0-100), or null if no budgets (weight redistributed)",
            "income_stability_score": "max(0, 100 - coefficient_of_variation_of_income)",
            "spending_consistency_score": "max(0, 100 - coefficient_of_variation_of_expenses)",
            "weights": f"savings={effective_weights.get('savings_rate', 40)}%, budget={effective_weights.get('budget_adherence', 25)}%, income_stability={effective_weights.get('income_stability', 20)}%, spending_consistency={effective_weights.get('spending_consistency', 15)}%",
        },
        "months_analyzed": len(monthly_data),
    }
