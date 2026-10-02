"""Deterministic savings-goal progress analytics.

This service answers "when will this goal actually be funded?" using only data
that genuinely exists. It never mutates a goal: ``target_amount`` and
``current_amount`` are read-only inputs here, so calling this has no side
effects on stored state.

Methodology
-----------
progress
    ``current_amount / target_amount``, clamped to ``[0, 100]`` and quantized
    to 2dp. Taken straight from the stored aggregate, not reconstructed.

contribution rate
    Mean money added per month, measured from the append-only
    ``savings_goal_contributions`` ledger: ``total_contributed / months_observed``
    where the window spans first contribution -> today. An alternative "average
    contribution" is also reported as the mean of the individual deposits.

    A ledger is required for this to mean anything. Goals created before the
    ledger existed have no rows, so their rate is genuinely unknown and the
    service says so rather than inventing a number.

projection
    ``months_remaining = ceil(remaining / monthly_rate)``. A projection is only
    emitted when the data supports one:

    * ``completed``            - target already reached, no projection needed.
    * ``no_progress``          - rate is zero or negative.
    * ``insufficient_data``    - no ledger rows, or fewer than
      ``MIN_CONTRIBUTIONS`` deposits, or the observation window is under
      ``MIN_MONTHS_OBSERVED``.
    * ``on_track``             - projected completion on or before target date.
    * ``behind``               - projected completion after the target date.
    * ``no_target_date``       - projected completion computed, but the goal has
                                 no deadline to compare it against.

    ``target_date`` is respected as a comparison point, never as an input to the
    arithmetic, and a projection is never stretched to fit a deadline.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.database import crud
from app.database.db import SavingsGoal

# A rate computed from a single deposit is not a rate. Require real history.
MIN_CONTRIBUTIONS = 2
# Below this the window is too short to annualise into a monthly pace.
MIN_MONTHS_OBSERVED = 1

# Money is stored to 2dp; rates and projections follow the same convention.
_CENT = Decimal("0.01")
_DAYS_PER_MONTH = Decimal("30.4375")  # 365.25 / 12, avoids calendar drift

# Projection status vocabulary, returned verbatim to the client.
STATUS_COMPLETED = "completed"
STATUS_ON_TRACK = "on_track"
STATUS_BEHIND = "behind"
STATUS_NO_TARGET_DATE = "no_target_date"
STATUS_INSUFFICIENT_DATA = "insufficient_data"
STATUS_NO_PROGRESS = "no_progress"


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _months_between(start: date, end: date) -> Decimal:
    """Decimal month distance between two dates."""
    days = Decimal((end - start).days)
    if days <= 0:
        return Decimal("0")
    return days / _DAYS_PER_MONTH


def _add_months(base: date, months: int) -> date:
    """Calendar-safe month addition (clamps to the end of the target month)."""
    total = base.month - 1 + months
    year = base.year + total // 12
    month = total % 12 + 1
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day = (next_month_first - timedelta(days=1)).day
    return date(year, month, min(base.day, last_day))


def compute_goal_progress(goal: SavingsGoal, contributions: List[Any]) -> Dict[str, Any]:
    """Compute progress + projection for one goal.

    ``contributions`` is the goal's ledger rows (objects exposing ``amount`` and
    ``contributed_at``). Pure function: it reads but never writes.
    """
    target = goal.target_amount or Decimal("0")
    current = goal.current_amount or Decimal("0")

    # --- Progress: read straight off the stored aggregate ---
    if target > 0:
        raw_percent = (current / target) * Decimal("100")
    else:
        raw_percent = Decimal("0")
    # Clamp: over-funding is reported through `remaining_amount` going negative,
    # not by showing progress above 100.
    clamped = min(max(raw_percent, Decimal("0")), Decimal("100"))
    progress_percent = _quantize_money(clamped)

    remaining = target - current

    result: Dict[str, Any] = {
        "goal_id": goal.id,
        "goal_name": goal.name,
        "target_amount": _quantize_money(target),
        "current_amount": _quantize_money(current),
        "remaining_amount": _quantize_money(remaining),
        "progress_percent": float(progress_percent),
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "monthly_contribution_rate": None,
        "average_monthly_contribution": None,
        "contribution_count": len(contributions),
        "projected_completion_date": None,
        "projected_months_remaining": None,
        "projection_status": STATUS_INSUFFICIENT_DATA,
    }

    # --- Target already reached: nothing left to project ---
    if target > 0 and current >= target:
        result["projection_status"] = STATUS_COMPLETED
        result["projected_months_remaining"] = 0
        return result

    # --- Measure the contribution rate from real history ---
    if not contributions:
        # No ledger rows: a rate cannot be measured. Report the gap rather than
        # deriving a pace from goal age, which says nothing about saving.
        result["projection_status"] = STATUS_INSUFFICIENT_DATA
        return result

    total_contributed = sum(
        (Decimal(str(c.amount)) for c in contributions), Decimal("0")
    )
    average_contribution = total_contributed / Decimal(str(len(contributions)))

    first_contribution = _as_date(contributions[0].contributed_at)
    today = date.today()
    months_observed = _months_between(first_contribution, today)

    result["average_monthly_contribution"] = _quantize_money(average_contribution)

    if len(contributions) < MIN_CONTRIBUTIONS or months_observed < Decimal(str(MIN_MONTHS_OBSERVED)):
        result["projection_status"] = STATUS_INSUFFICIENT_DATA
        return result

    monthly_rate = total_contributed / months_observed
    result["monthly_contribution_rate"] = _quantize_money(monthly_rate)

    # --- Projection ---
    if monthly_rate <= 0:
        # Only reachable with non-positive deposits in the ledger.
        result["projection_status"] = STATUS_NO_PROGRESS
        return result

    if remaining <= 0:
        result["projection_status"] = STATUS_COMPLETED
        result["projected_months_remaining"] = 0
        return result

    months_remaining = int(
        (remaining / monthly_rate).to_integral_value(rounding=ROUND_CEILING)
    )
    projected_completion = _add_months(today, months_remaining)

    result["projected_months_remaining"] = months_remaining
    result["projected_completion_date"] = projected_completion.isoformat()

    if goal.target_date is None:
        result["projection_status"] = STATUS_NO_TARGET_DATE
    elif projected_completion <= goal.target_date:
        result["projection_status"] = STATUS_ON_TRACK
    else:
        # Projection still reported honestly; the deadline is just missed.
        result["projection_status"] = STATUS_BEHIND

    return result


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def get_goal_progress(db: Session, user_id: int, goal_id: int) -> Optional[Dict[str, Any]]:
    """Progress + projection for one owned goal, or None if not owned."""
    goal = crud.get_savings_goal(db, goal_id, user_id)
    if not goal:
        return None
    contributions = crud.get_savings_goal_contributions(db, goal_id, user_id)
    return compute_goal_progress(goal, contributions)


def get_all_goals_progress(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """Progress + projection for every goal owned by this user."""
    goals = crud.get_savings_goals(db, user_id)
    return [
        compute_goal_progress(
            goal, crud.get_savings_goal_contributions(db, goal.id, user_id)
        )
        for goal in goals
    ]