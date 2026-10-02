"""Notification creation with deterministic event deduplication.

Notifications are never generated implicitly on read paths. They are created
explicitly by an event producer (a future phase will wire budget/velocity/anomaly
detectors to this service). Every call is user-scoped.

Deduplication
-------------
Callers may pass an ``event_key`` — a deterministic identifier for the event
that produced the notification, e.g.::

    budget_exceeded:Food & Dining:2026-10
    spending_velocity:3:2026-10-02
    anomaly:duplicate_charge:<merchant>

The same ``event_key`` for the same user maps to exactly one notification: a
unique constraint on ``(user_id, event_key)`` backs a pre-check so repeated
emission of the same event never creates a duplicate row.
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import crud
from app.database.db import Notification

logger = logging.getLogger(__name__)

NOTIFICATION_TYPES = ("budget_threshold", "budget_exceeded", "spending_velocity", "anomaly")
NOTIFICATION_SEVERITIES = ("info", "warning", "critical")


def build_event_key(notification_type: str, *parts: Any) -> str:
    """Build a deterministic dedup key for an event.

    Parts are normalized so equivalent events always produce the same key.
    """
    normalized = [str(p).strip().lower() for p in parts if p is not None and str(p).strip() != ""]
    return ":".join([notification_type, *normalized])


def serialize_metadata(metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    """Serialize an optional metadata dict to JSON text."""
    if metadata is None:
        return None
    try:
        return json.dumps(metadata, default=str)
    except (TypeError, ValueError) as exc:
        logger.warning(f"Dropping unserializable notification metadata: {exc}")
        return None


def deserialize_metadata(metadata_json: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse stored metadata JSON back to a dict, tolerating corrupt rows."""
    if not metadata_json:
        return None
    try:
        parsed = json.loads(metadata_json)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def create_notification_for_event(
    db: Session,
    user_id: int,
    type: str,
    title: str,
    message: str,
    severity: str = "info",
    related_entity_type: Optional[str] = None,
    related_entity_id: Optional[int] = None,
    event_key: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[Notification, bool]:
    """Create a notification for a user, deduplicating on event_key.

    Returns ``(notification, created)`` — ``created`` is False when an existing
    notification for the same event_key was returned instead.
    """
    if type not in NOTIFICATION_TYPES:
        raise ValueError(f"Invalid notification type: {type}")
    if severity not in NOTIFICATION_SEVERITIES:
        raise ValueError(f"Invalid notification severity: {severity}")

    if event_key:
        existing = crud.get_notification_by_event_key(db, user_id, event_key)
        if existing:
            return existing, False

    try:
        notification = crud.create_notification(
            db,
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            severity=severity,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            event_key=event_key,
            metadata_json=serialize_metadata(metadata),
        )
        return notification, True
    except IntegrityError:
        # Lost a race on the unique (user_id, event_key) constraint.
        db.rollback()
        existing = crud.get_notification_by_event_key(db, user_id, event_key)
        if existing:
            return existing, False
        raise


def to_response_dict(notification: Notification) -> Dict[str, Any]:
    """Map a Notification row to its API representation."""
    return {
        "id": notification.id,
        "user_id": notification.user_id,
        "type": notification.type,
        "title": notification.title,
        "message": notification.message,
        "severity": notification.severity,
        "is_read": notification.is_read,
        "created_at": notification.created_at,
        "related_entity_type": notification.related_entity_type,
        "related_entity_id": notification.related_entity_id,
        "metadata": deserialize_metadata(notification.metadata_json),
    }