import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import crud
from app.database.db import get_db, User
from app.models import schemas
from app.services import notifications as notification_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_owned_notification(db: Session, notification_id: int, user_id: int):
    """Fetch a notification owned by this user, or 404.

    A notification belonging to another user is reported as not found so the
    API never reveals that another user's notification id exists.
    """
    notification = crud.get_notification(db, notification_id, user_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification


@router.get("/notifications", response_model=schemas.NotificationListResponse)
def list_notifications(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(20, ge=1, le=100, description="Notifications per page"),
    unread_only: bool = Query(False, description="Only return unread notifications"),
    type: Optional[str] = Query(None, description="Filter by notification type"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if type is not None and type not in notification_service.NOTIFICATION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid notification type '{type}'. "
                f"Must be one of: {sorted(notification_service.NOTIFICATION_TYPES)}"
            ),
        )

    rows, total = crud.get_notifications_paginated(
        db, current_user.id, page=page, limit=limit,
        unread_only=unread_only, type_filter=type,
    )
    pages = (total + limit - 1) // limit if limit else 0

    return {
        "notifications": [notification_service.to_response_dict(n) for n in rows],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
        "unread_count": crud.count_unread_notifications(db, current_user.id),
    }


@router.post("/notifications", response_model=schemas.NotificationResponse, status_code=201)
def create_notification(
    payload: schemas.NotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a notification for the authenticated user.

    Never generated implicitly — an event producer must call this explicitly.
    """
    try:
        notification, _created = notification_service.create_notification_for_event(
            db,
            user_id=current_user.id,
            type=payload.type,
            title=payload.title,
            message=payload.message,
            severity=payload.severity,
            related_entity_type=payload.related_entity_type,
            related_entity_id=payload.related_entity_id,
            event_key=payload.event_key,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return notification_service.to_response_dict(notification)


@router.patch("/notifications/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated = crud.mark_all_notifications_read(db, current_user.id)
    return {
        "message": "All notifications marked as read.",
        "updated": updated,
        "unread_count": crud.count_unread_notifications(db, current_user.id),
    }


@router.patch("/notifications/{notification_id}/read", response_model=schemas.NotificationResponse)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = _get_owned_notification(db, notification_id, current_user.id)
    notification = crud.set_notification_read(db, notification, is_read=True)
    return notification_service.to_response_dict(notification)


@router.patch("/notifications/{notification_id}/unread", response_model=schemas.NotificationResponse)
def mark_notification_unread(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = _get_owned_notification(db, notification_id, current_user.id)
    notification = crud.set_notification_read(db, notification, is_read=False)
    return notification_service.to_response_dict(notification)


@router.delete("/notifications/{notification_id}")
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = _get_owned_notification(db, notification_id, current_user.id)
    crud.delete_notification(db, notification)
    return {"message": "Notification deleted."}