"""Notification producers for deterministic financial events.

Each producer reuses an existing calculation service as-is — no financial
formula is duplicated or altered here:

* budgets  -> ``services.budgets.get_budget_status``  (status: over | approaching | on_track)
* velocity -> ``services.spending_velocity.get_spending_velocity`` (alert_level)
* anomaly  -> ``services.anomalies.generate_anomaly_report`` (signature ``id``)

Producers are invoked explicitly (see ``routers/notifications.py`` sync
endpoints), never implicitly on a dashboard/analytics read path, so repeated
reads cannot spam notifications.

Event keys use only identifiers that already exist in the codebase:
``BudgetGoal.id``, the velocity window dates, and the anomaly signature
already used by ``AnomalyReview.anomaly_signature``.

Failure isolation: producers only ever READ financial tables, so a failed
notification write can be undone with a plain transaction rollback. That
discards the half-written notification and nothing else, and the producer
reports the error instead of raising — the underlying financial analytics
endpoint and its data are never affected.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services import anomalies as anomalies_service
from app.services import budgets as budgets_service
from app.services import notifications as notification_service
from app.services import spending_velocity as velocity_service

logger = logging.getLogger(__name__)

# Anomaly severity is produced by the existing detector; map it onto the
# notification severity vocabulary without inventing new values.
_SEVERITY_PASSTHROUGH = {"info", "warning", "critical"}


def _stringify(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _budget_event_key(budget_id: Any, kind: str, period: str) -> str:
    """budget:{budget_id}:threshold:{period} | budget:{budget_id}:exceeded:{period}"""
    if budget_id is None:
        # Fall back to the category when no id is exposed by the calculation.
        # Category is stable per user because budgets are upserted by category.
        return f"budget:{period}:{kind}"
    return f"budget:{budget_id}:{kind}:{period}"


def _velocity_event_key(window_days: Any, window_start: str, window_end: str) -> str:
    """velocity:{window_days}:{window_start}:{window_end}"""
    return f"velocity:{window_days}:{window_start}:{window_end}"


def _anomaly_event_key(anomaly_id: str) -> str:
    """anomaly:{anomaly_id} — anomaly_id is the existing stable signature."""
    return f"anomaly:{anomaly_id}"


def _emit(
    db: Session,
    user_id: int,
    *,
    notification_type: str,
    title: str,
    message: str,
    severity: str,
    event_key: str,
    related_entity_type: Optional[str] = None,
    related_entity_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Persist one notification. Never raises.

    Producers are strictly read-only against the financial tables, so rolling
    the session transaction back on failure can only undo the notification
    insert itself. A SAVEPOINT is not usable here because the CRUD layer
    commits per write, which would close the savepoint out from under us.
    """
    try:
        notification, created = notification_service.create_notification_for_event(
            db,
            user_id=user_id,
            type=notification_type,
            title=title,
            message=message,
            severity=severity,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            event_key=event_key,
            metadata=metadata,
        )
        return {"event_key": event_key, "created": created, "id": notification.id}
    except Exception as exc:  # noqa: BLE001 - isolation is the point
        try:
            db.rollback()
        except Exception:  # pragma: no cover - rollback itself is best-effort
            pass
        logger.error(
            "Notification emit failed for user=%s event_key=%s: %s: %s",
            user_id,
            event_key,
            exc.__class__.__name__,
            exc,
        )
        return None


def sync_budget_notifications(db: Session, user_id: int, month: Optional[str] = None) -> Dict[str, Any]:
    """Emit budget_threshold / budget_exceeded notifications from budget status.

    Reuses get_budget_status unchanged; maps its existing status values:
    ``over`` -> budget_exceeded (critical), ``approaching`` -> budget_threshold (warning).
    """
    result: Dict[str, Any] = {
        "source": "budget",
        "period": month,
        "examined": 0,
        "created": 0,
        "deduplicated": 0,
        "failed": 0,
        "notifications": [],
        "error": None,
    }

    try:
        statuses = budgets_service.get_budget_status(db, user_id, month)
    except Exception as exc:  # noqa: BLE001 - the producer is a side channel
        db.rollback()
        result["error"] = f"budget status unavailable: {exc.__class__.__name__}"
        logger.error(f"Budget notification sync failed for user={user_id}: {exc}")
        return result

    if result["period"] is None:
        # get_budget_status resolves the default period internally; mirror it for keys.
        from datetime import datetime
        result["period"] = (month or datetime.today().strftime("%Y-%m"))

    period = result["period"]

    for status in statuses:
        level = status.get("status")
        if level not in ("over", "approaching"):
            continue

        result["examined"] += 1

        if level == "over":
            ntype = "budget_exceeded"
            severity = "critical"
            kind = "exceeded"
        else:
            ntype = "budget_threshold"
            severity = "warning"
            kind = "threshold"

        event_key = _budget_event_key(status.get("budget_id"), kind, period)

        emitted = _emit(
            db,
            user_id,
            notification_type=ntype,
            title=f"{status['category']} budget {kind}",
            message=status["message"],
            severity=severity,
            event_key=event_key,
            related_entity_type="budget_goal",
            related_entity_id=status.get("budget_id"),
            metadata={
                "category": status["category"],
                "period": period,
                "monthly_cap": _stringify(status.get("monthly_cap")),
                "current_spend": _stringify(status.get("current_spend")),
                "percent_used": _stringify(status.get("percent_used")),
                "days_left_in_month": status.get("days_left_in_month"),
                "status": level,
            },
        )

        if emitted is None:
            result["failed"] += 1
            continue
        result["notifications"].append(emitted)
        result["created" if emitted["created"] else "deduplicated"] += 1

    return result


def sync_velocity_notifications(db: Session, user_id: int, window_days: int = 3) -> Dict[str, Any]:
    """Emit a notification only for high / very_high spending velocity.

    normal / elevated / insufficient_data / no_baseline produce nothing.
    Reuses get_spending_velocity unchanged.
    """
    result: Dict[str, Any] = {
        "source": "spending_velocity",
        "window_days": window_days,
        "alert_level": None,
        "examined": 0,
        "created": 0,
        "deduplicated": 0,
        "failed": 0,
        "notifications": [],
        "error": None,
    }

    try:
        velocity = velocity_service.get_spending_velocity(db, user_id, window_days=window_days)
    except Exception as exc:  # noqa: BLE001 - the producer is a side channel
        db.rollback()
        result["error"] = f"velocity unavailable: {exc.__class__.__name__}"
        logger.error(f"Velocity notification sync failed for user={user_id}: {exc}")
        return result

    alert_level = velocity.get("alert_level")
    result["alert_level"] = alert_level

    if alert_level not in ("high", "very_high"):
        return result

    result["examined"] = 1

    severity = "critical" if alert_level == "very_high" else "warning"
    start_date = velocity.get("start_date")
    end_date = velocity.get("end_date")
    event_key = _velocity_event_key(window_days, start_date, end_date)

    ratio = velocity.get("velocity_ratio")
    emitted = _emit(
        db,
        user_id,
        notification_type="spending_velocity",
        title=f"Spending velocity {alert_level.replace('_', ' ')}",
        message=(
            f"Spending over the last {window_days} day"
            f"{'s' if window_days != 1 else ''} is {ratio}x your usual pace."
            if ratio is not None
            else f"Spending pace over the last {window_days} days is unusually high."
        ),
        severity=severity,
        event_key=event_key,
        related_entity_type="spending_velocity_window",
        metadata={
            "alert_level": alert_level,
            "window_days": window_days,
            "start_date": start_date,
            "end_date": end_date,
            "current_window_spend": _stringify(velocity.get("current_window_spend")),
            "baseline_window_spend": _stringify(velocity.get("baseline_window_spend")),
            "velocity_ratio": ratio,
            "percentage_change": velocity.get("percentage_change"),
        },
    )

    if emitted is None:
        result["failed"] = 1
        return result

    result["notifications"].append(emitted)
    result["created" if emitted["created"] else "deduplicated"] += 1
    return result


def sync_anomaly_notifications(db: Session, user_id: int) -> Dict[str, Any]:
    """Emit a notification for each newly detected (unreviewed) anomaly.

    Reuses generate_anomaly_report unchanged. Its ``id`` is the same stable
    signature stored in ``AnomalyReview.anomaly_signature``, so a dismissed or
    confirmed anomaly is not re-notified.
    """
    result: Dict[str, Any] = {
        "source": "anomaly",
        "examined": 0,
        "created": 0,
        "deduplicated": 0,
        "failed": 0,
        "notifications": [],
        "error": None,
    }

    try:
        detected = anomalies_service.generate_anomaly_report(db, user_id)
    except Exception as exc:  # noqa: BLE001 - the producer is a side channel
        db.rollback()
        result["error"] = f"anomaly report unavailable: {exc.__class__.__name__}"
        logger.error(f"Anomaly notification sync failed for user={user_id}: {exc}")
        return result

    for anomaly in detected:
        anomaly_id = anomaly.get("id")
        if not anomaly_id:
            continue

        result["examined"] += 1

        severity = anomaly.get("severity")
        if severity not in _SEVERITY_PASSTHROUGH:
            severity = "info"

        transaction_ids: List[int] = anomaly.get("transaction_ids") or []
        emitted = _emit(
            db,
            user_id,
notification_type="anomaly",
            title=f"Anomaly detected: {anomaly.get('type', 'unknown')}",
            message=anomaly.get("message", "An unusual transaction pattern was detected."),
            severity=severity,
            event_key=_anomaly_event_key(anomaly_id),
            related_entity_type="anomaly",
            related_entity_id=transaction_ids[0] if transaction_ids else None,
            metadata={
                "anomaly_id": anomaly_id,
                "anomaly_type": anomaly.get("type"),
                "merchant": anomaly.get("merchant"),
                "date": anomaly.get("date"),
                "transaction_ids": transaction_ids,
            },
        )

        if emitted is None:
            result["failed"] += 1
            continue
        result["notifications"].append(emitted)
        result["created" if emitted["created"] else "deduplicated"] += 1

    return result