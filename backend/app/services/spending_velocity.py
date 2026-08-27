"""Deterministic spending-velocity detection.

Baseline methodology
--------------------
Current window: the most recent ``window_days`` calendar days ending today
(inclusive). Only debit/credit-type 'debit' transactions count as spending.

Baseline: mean spend over up to ``MAX_BASELINE_WINDOWS`` most recent complete,
non-overlapping windows of the same length that fit in the user's history
immediately before the current window. History coverage starts at the user's
earliest debit transaction date. Zero-spend windows count as valid baseline
periods.

Alert levels (pace relative to the user's own history, never absolute size):
- insufficient_data: fewer than MIN_BASELINE_WINDOWS complete baseline windows
- no_baseline: baseline windows exist but historical spend is zero (ratio undefined)
- normal: velocity_ratio < 1.25
- elevated: 1.25 <= velocity_ratio < 2.00
- high: 2.00 <= velocity_ratio < 3.00
- very_high: velocity_ratio >= 3.00

Strong alerts (high/very_high) are only reported when at least
MIN_BASELINE_WINDOWS baseline windows are available.
"""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.db import Transaction

DEFAULT_WINDOW_DAYS = 3
MAX_WINDOW_DAYS = 90
MIN_BASELINE_WINDOWS = 3
MAX_BASELINE_WINDOWS = 10

ALERT_NORMAL_MAX_RATIO = Decimal("1.25")
ALERT_ELEVATED_MAX_RATIO = Decimal("2.00")
ALERT_HIGH_MAX_RATIO = Decimal("3.00")

BASELINE_METHOD_TEMPLATE = (
    "Mean spend over up to {max_windows} most recent complete non-overlapping "
    "{window_days}-day windows immediately preceding the current window, "
    "using debit transactions at original transaction amounts only. "
    "History coverage starts at the earliest debit transaction date. "
    "Zero-spend windows count toward the baseline. "
    "Strong alerts require at least {min_windows} baseline windows. "
    "Alert thresholds are pace multipliers vs the user's own baseline "
    "(normal < 1.25x, elevated < 2.00x, high < 3.00x, very_high >= 3.00x); "
    "absolute spend alone never triggers an alert."
)


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _sum_debits(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
) -> Decimal:
    """Sum debit transaction amounts in [start_date, end_date].

    Uses original Transaction.amount only — split rows are never added.
    Future-dated transactions (date > today) are excluded by the caller
    passing end_date <= today.
    """
    result = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_type == "debit",
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
        .scalar()
    )
    return Decimal(str(result)) if result is not None else Decimal("0")


def get_spending_velocity(
    db: Session,
    user_id: int,
    window_days: int = DEFAULT_WINDOW_DAYS,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Compute spending pace vs the user's own historical N-day windows."""
    if today is None:
        today = date.today()

    window_days = int(window_days)
    end_date = today
    start_date = today - timedelta(days=window_days - 1)

    current_spend = _sum_debits(db, user_id, start_date, end_date)

    earliest = (
        db.query(func.min(Transaction.date))
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_type == "debit",
            Transaction.date <= end_date,
        )
        .scalar()
    )

    baseline_method = BASELINE_METHOD_TEMPLATE.format(
        max_windows=MAX_BASELINE_WINDOWS,
        window_days=window_days,
        min_windows=MIN_BASELINE_WINDOWS,
    )

    baseline = Decimal("0")
    windows_used = 0
    velocity_ratio: Optional[float] = None
    percentage_change: Optional[float] = None
    alert_level = "insufficient_data"
    history_start: Optional[str] = None

    if earliest is not None:
        history_start = earliest.isoformat()
        history_end = start_date - timedelta(days=1)
        if history_end >= earliest:
            history_days = (history_end - earliest).days + 1
            n_possible = history_days // window_days if window_days > 0 else 0
            windows_to_use = min(n_possible, MAX_BASELINE_WINDOWS)

            window_spends: List[Decimal] = []
            cursor_end = history_end
            for _ in range(windows_to_use):
                w_end = cursor_end
                w_start = w_end - timedelta(days=window_days - 1)
                window_spends.append(_sum_debits(db, user_id, w_start, w_end))
                cursor_end = w_start - timedelta(days=1)

            windows_used = len(window_spends)

            if windows_used > 0:
                baseline = _quantize(
                    sum(window_spends, Decimal("0")) / Decimal(str(windows_used))
                )

    if windows_used > 0 and baseline > 0:
        ratio_dec = current_spend / baseline
        velocity_ratio = float(ratio_dec.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        pct_dec = (current_spend - baseline) / baseline * Decimal("100")
        percentage_change = float(pct_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        if windows_used < MIN_BASELINE_WINDOWS:
            alert_level = "insufficient_data"
        elif ratio_dec < ALERT_NORMAL_MAX_RATIO:
            alert_level = "normal"
        elif ratio_dec < ALERT_ELEVATED_MAX_RATIO:
            alert_level = "elevated"
        elif ratio_dec < ALERT_HIGH_MAX_RATIO:
            alert_level = "high"
        else:
            alert_level = "very_high"
    elif windows_used > 0 and baseline == 0:
        alert_level = "no_baseline"
    else:
        alert_level = "insufficient_data"

    return {
        "current_window_spend": _quantize(current_spend),
        "baseline_window_spend": _quantize(baseline),
        "velocity_ratio": velocity_ratio,
        "percentage_change": percentage_change,
        "window_days": window_days,
        "baseline_method": baseline_method,
        "alert_level": alert_level,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "baseline_windows_used": windows_used,
        "history_start_date": history_start,
    }
