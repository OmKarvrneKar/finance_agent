import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.database.db import Transaction


DEFAULT_WINDOW_DAYS = 30
MAX_PROJECTION_STEPS = 240


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        parts = value.strip().split("-")
        if len(parts) != 3:
            return None
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, TypeError):
        return None


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def _classify_frequency(
    valid_dates: List[date],
) -> Tuple[str, Optional[Any], str]:
    """Classify frequency from historical dates.

    Returns (frequency_label, advance_fn, date_status).
    advance_fn is None when dates cannot support projection.
    """
    if len(valid_dates) < 2:
        return "Monthly (Assumed)", None, "uncertain"

    dates = sorted(valid_dates)
    days_span = (dates[-1] - dates[0]).days
    if days_span <= 0:
        return "One-time / Initial", None, "uncertain"

    avg_days_between = days_span / (len(dates) - 1)

    if avg_days_between <= 10:
        return "Weekly", lambda d: d + timedelta(days=7), "projected"
    if avg_days_between <= 20:
        return "Bi-weekly", lambda d: d + timedelta(days=14), "projected"
    if avg_days_between <= 45:
        return "Monthly", lambda d: _add_months(d, 1), "projected"
    if avg_days_between <= 100:
        return "Quarterly", lambda d: _add_months(d, 3), "projected"
    return "Yearly", lambda d: _add_months(d, 12), "projected"


def _project_date_in_range(
    last_seen: date,
    advance_fn,
    start_date: date,
    end_date: date,
) -> Optional[date]:
    """Roll forward from last_seen until a date lands in [start_date, end_date]."""
    current = last_seen
    for _ in range(MAX_PROJECTION_STEPS):
        current = advance_fn(current)
        if current > end_date:
            return None
        if current >= start_date:
            return current
    return None


def _normalize_description(description: str) -> str:
    return description.lower().strip()


def get_upcoming_bills(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """Deterministic recurring-bills calendar for the authenticated user.

    Read-only: does not create or modify recurring records.
    Amounts are Decimal and taken from historical transactions (authoritative).
    Dates are only projected when >= 2 distinct historical dates support the
    frequency interval; otherwise expected_date is None with a clear status.
    """
    recurring_txs = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.is_recurring == True,  # noqa: E712
            Transaction.transaction_type == "debit",
        )
        .all()
    )

    grouped: Dict[str, List[Transaction]] = {}
    for tx in recurring_txs:
        if not tx.description:
            continue
        key = _normalize_description(tx.description)
        grouped.setdefault(key, []).append(tx)

    bills: List[Dict[str, Any]] = []

    for _, txs in grouped.items():
        occurrences = len(txs)
        total_amount = sum(tx.amount for tx in txs)
        avg_amount = total_amount / Decimal(str(occurrences))

        valid_dates: List[date] = []
        for tx in txs:
            if tx.date is not None:
                if hasattr(tx.date, "isoformat"):
                    valid_dates.append(tx.date)
                else:
                    parsed = _parse_date(str(tx.date))
                    if parsed:
                        valid_dates.append(parsed)

        sorted_dates = sorted(valid_dates)
        last_seen = sorted_dates[-1] if sorted_dates else None

        frequency, advance_fn, date_status = _classify_frequency(valid_dates)

        expected_date: Optional[date] = None
        if advance_fn is not None and last_seen is not None:
            projected = _project_date_in_range(
                last_seen, advance_fn, start_date, end_date
            )
            if projected is None:
                # Bill exists but next occurrence falls outside the window.
                continue
            expected_date = projected
            date_status = "projected"
        elif not valid_dates:
            date_status = "missing"
        else:
            # Insufficient history to project a date — never fabricate one.
            date_status = "uncertain"
            expected_date = None

        is_user_confirmed = any(
            tx.is_user_confirmed_recurring for tx in txs
        )

        bills.append(
            {
                "description": txs[0].description,
                "category": txs[0].category if txs[0].category else None,
                "expected_amount": avg_amount.quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
                "expected_date": (
                    expected_date.isoformat() if expected_date else None
                ),
                "date_status": date_status,
                "frequency": frequency,
                "is_user_confirmed": is_user_confirmed,
                "occurrences": occurrences,
                "last_seen": (
                    last_seen.isoformat() if last_seen else "Unknown"
                ),
            }
        )

    # Projected dates ascending; uncertain/missing last (name-sorted).
    bills.sort(
        key=lambda b: (
            b["expected_date"] is None,
            b["expected_date"] or "",
            b["description"].lower(),
        )
    )

    total_expected = sum(
        (b["expected_amount"] for b in bills), Decimal("0.00")
    )

    return {
        "bills": bills,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_expected_amount": total_expected,
        "count": len(bills),
    }
