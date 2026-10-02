import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, User, Notification
from app.services import notifications as notification_service


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client, email="notif1@test.com"):
    client.post("/api/auth/register", json={"email": email, "password": "Password123", "full_name": "N"})
    resp = client.post("/api/auth/login", data={"username": email, "password": "Password123"})
    return resp.json()["access_token"]


@pytest.fixture()
def token(client):
    return _register(client, "notif1@test.com")


@pytest.fixture()
def token2(client):
    return _register(client, "notif2@test.com")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create(db, user_id, type="budget_exceeded", title="Budget exceeded", message="You went over",
            severity="warning", event_key=None, created_at=None, is_read=False):
    n = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        severity=severity,
        is_read=is_read,
        event_key=event_key,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _user_id(token):
    import jwt
    from app.auth import JWT_SECRET_KEY
    return int(jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])["sub"])


def _payload(**overrides):
    base = {
        "type": "budget_exceeded",
        "title": "Food budget exceeded",
        "message": "You spent 120% of your Food budget this month.",
        "severity": "warning",
    }
    base.update(overrides)
    return base


class TestNotificationCreate:
    def test_create_notification(self, db_session, client, token):
        resp = client.post("/api/notifications", json=_payload(), headers=_auth(token))
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "budget_exceeded"
        assert data["title"] == "Food budget exceeded"
        assert data["severity"] == "warning"
        assert data["is_read"] is False
        assert data["user_id"] == _user_id(token)
        assert data["id"] > 0

    def test_create_notification_defaults_severity_info(self, client, token):
        payload = _payload()
        payload.pop("severity")
        resp = client.post("/api/notifications", json=payload, headers=_auth(token))
        assert resp.status_code == 201
        assert resp.json()["severity"] == "info"

    def test_create_notification_with_related_entity(self, client, token):
        resp = client.post("/api/notifications", json=_payload(
            related_entity_type="budget_goal", related_entity_id=42,
        ), headers=_auth(token))
        assert resp.status_code == 201
        data = resp.json()
        assert data["related_entity_type"] == "budget_goal"
        assert data["related_entity_id"] == 42

    def test_create_notification_with_metadata(self, client, token):
        resp = client.post("/api/notifications", json=_payload(
            metadata={"limit": 5000, "spent": 6200, "ratio": 1.24},
        ), headers=_auth(token))
        assert resp.status_code == 201
        assert resp.json()["metadata"] == {"limit": 5000, "spent": 6200, "ratio": 1.24}

    def test_create_notification_metadata_decimal_stringified(self, db_session, token):
        """Unserializable values (e.g. Decimal) degrade to strings, never crash."""
        uid = _user_id(token)
        notification, _created = notification_service.create_notification_for_event(
            db_session, user_id=uid, type="budget_exceeded", title="t", message="m",
            metadata={"limit": Decimal("5000.00"), "ratio": Decimal("1.24")},
        )
        assert notification_service.deserialize_metadata(notification.metadata_json) == {
            "limit": "5000.00", "ratio": "1.24",
        }

    @pytest.mark.parametrize("ntype", [
        "budget_threshold", "budget_exceeded", "spending_velocity", "anomaly",
    ])
    def test_all_supported_types_accepted(self, client, token, ntype):
        resp = client.post("/api/notifications", json=_payload(type=ntype), headers=_auth(token))
        assert resp.status_code == 201
        assert resp.json()["type"] == ntype

    @pytest.mark.parametrize("severity", ["info", "warning", "critical"])
    def test_all_supported_severities_accepted(self, client, token, severity):
        resp = client.post("/api/notifications", json=_payload(severity=severity), headers=_auth(token))
        assert resp.status_code == 201
        assert resp.json()["severity"] == severity

    def test_invalid_notification_type_rejected(self, client, token):
        resp = client.post("/api/notifications", json=_payload(type="not_a_type"), headers=_auth(token))
        assert resp.status_code == 422

    def test_invalid_severity_rejected(self, client, token):
        resp = client.post("/api/notifications", json=_payload(severity="catastrophic"), headers=_auth(token))
        assert resp.status_code == 422

    def test_empty_title_rejected(self, client, token):
        resp = client.post("/api/notifications", json=_payload(title="   "), headers=_auth(token))
        assert resp.status_code == 422

    def test_create_requires_auth(self, client):
        resp = client.post("/api/notifications", json=_payload())
        assert resp.status_code == 401


class TestNotificationDedup:
    def test_duplicate_event_key_does_not_create_second_notification(self, client, token):
        first = client.post("/api/notifications", json=_payload(
            event_key="budget_exceeded:food:2026-10",
        ), headers=_auth(token))
        assert first.status_code == 201

        second = client.post("/api/notifications", json=_payload(
            event_key="budget_exceeded:food:2026-10",
        ), headers=_auth(token))
        assert second.status_code == 201
        assert second.json()["id"] == first.json()["id"]

        listing = client.get("/api/notifications", headers=_auth(token)).json()
        assert listing["total"] == 1

    def test_distinct_event_keys_create_distinct_notifications(self, client, token):
        for key in ("budget_exceeded:food:2026-10", "budget_exceeded:food:2026-11"):
            resp = client.post("/api/notifications", json=_payload(event_key=key), headers=_auth(token))
            assert resp.status_code == 201
        listing = client.get("/api/notifications", headers=_auth(token)).json()
        assert listing["total"] == 2

    def test_notifications_without_event_key_are_not_deduplicated(self, client, token):
        for _ in range(3):
            resp = client.post("/api/notifications", json=_payload(), headers=_auth(token))
            assert resp.status_code == 201
        listing = client.get("/api/notifications", headers=_auth(token)).json()
        assert listing["total"] == 3

    def test_same_event_key_allowed_for_different_users(self, db_session, client, token, token2):
        uid1 = _user_id(token)
        uid2 = _user_id(token2)
        client.post("/api/notifications", json=_payload(event_key="shared:event"), headers=_auth(token))
        client.post("/api/notifications", json=_payload(event_key="shared:event"), headers=_auth(token2))

        t1 = client.get("/api/notifications", headers=_auth(token)).json()
        t2 = client.get("/api/notifications", headers=_auth(token2)).json()
        assert t1["total"] == 1
        assert t2["total"] == 1
        assert t1["notifications"][0]["user_id"] == uid1
        assert t2["notifications"][0]["user_id"] == uid2

    def test_service_returns_existing_on_duplicate(self, db_session, token):
        uid = _user_id(token)
        first, created_first = notification_service.create_notification_for_event(
            db_session, user_id=uid, type="spending_velocity", title="Spike", message="High pace",
            severity="critical", event_key="spending_velocity:3:2026-10-02",
        )
        assert created_first is True

        second, created_second = notification_service.create_notification_for_event(
            db_session, user_id=uid, type="spending_velocity", title="Spike", message="High pace",
            severity="critical", event_key="spending_velocity:3:2026-10-02",
        )
        assert created_second is False
        assert second.id == first.id

    def test_service_build_event_key_is_deterministic(self):
        a = notification_service.build_event_key("budget_exceeded", "Food & Dining", "2026-10")
        b = notification_service.build_event_key("budget_exceeded", "food & dining", "2026-10")
        assert a == b
        assert a == "budget_exceeded:food & dining:2026-10"

    def test_service_rejects_invalid_type(self, db_session, token):
        uid = _user_id(token)
        with pytest.raises(ValueError):
            notification_service.create_notification_for_event(
                db_session, user_id=uid, type="nope", title="t", message="m",
            )

    def test_service_rejects_invalid_severity(self, db_session, token):
        uid = _user_id(token)
        with pytest.raises(ValueError):
            notification_service.create_notification_for_event(
                db_session, user_id=uid, type="anomaly", title="t", message="m", severity="nope",
            )

    def test_deserialize_metadata_tolerates_corrupt_json(self):
        assert notification_service.deserialize_metadata("not json") is None
        assert notification_service.deserialize_metadata(None) is None
        assert notification_service.deserialize_metadata('{"a":1}') == {"a": 1}


class TestNotificationList:
    def test_empty_notification_list(self, client, token):
        resp = client.get("/api/notifications", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["notifications"] == []
        assert data["total"] == 0
        assert data["unread_count"] == 0

    def test_list_notifications(self, db_session, client, token):
        uid = _user_id(token)
        _create(db_session, uid, title="First")
        _create(db_session, uid, title="Second")

        data = client.get("/api/notifications", headers=_auth(token)).json()
        assert data["total"] == 2
        assert len(data["notifications"]) == 2
        titles = {n["title"] for n in data["notifications"]}
        assert titles == {"First", "Second"}

    def test_newest_first_ordering(self, db_session, client, token):
        uid = _user_id(token)
        base = datetime(2026, 10, 1, 12, 0, 0)
        _create(db_session, uid, title="oldest", created_at=base)
        _create(db_session, uid, title="middle", created_at=base + timedelta(hours=1))
        _create(db_session, uid, title="newest", created_at=base + timedelta(hours=2))

        data = client.get("/api/notifications", headers=_auth(token)).json()
        assert [n["title"] for n in data["notifications"]] == ["newest", "middle", "oldest"]

    def test_same_timestamp_breaks_tie_by_id_desc(self, db_session, client, token):
        uid = _user_id(token)
        ts = datetime(2026, 10, 1, 12, 0, 0)
        _create(db_session, uid, title="first", created_at=ts)
        _create(db_session, uid, title="second", created_at=ts)

        data = client.get("/api/notifications", headers=_auth(token)).json()
        assert [n["title"] for n in data["notifications"]] == ["second", "first"]

    def test_pagination_first_page(self, db_session, client, token):
        uid = _user_id(token)
        base = datetime(2026, 10, 1, 12, 0, 0)
        for i in range(7):
            _create(db_session, uid, title=f"n{i}", created_at=base + timedelta(minutes=i))

        data = client.get("/api/notifications?page=1&limit=3", headers=_auth(token)).json()
        assert data["total"] == 7
        assert data["page"] == 1
        assert data["limit"] == 3
        assert data["pages"] == 3
        assert len(data["notifications"]) == 3
        assert [n["title"] for n in data["notifications"]] == ["n6", "n5", "n4"]

    def test_pagination_second_page(self, db_session, client, token):
        uid = _user_id(token)
        base = datetime(2026, 10, 1, 12, 0, 0)
        for i in range(7):
            _create(db_session, uid, title=f"n{i}", created_at=base + timedelta(minutes=i))

        data = client.get("/api/notifications?page=2&limit=3", headers=_auth(token)).json()
        assert [n["title"] for n in data["notifications"]] == ["n3", "n2", "n1"]

    def test_pagination_last_partial_page(self, db_session, client, token):
        uid = _user_id(token)
        base = datetime(2026, 10, 1, 12, 0, 0)
        for i in range(7):
            _create(db_session, uid, title=f"n{i}", created_at=base + timedelta(minutes=i))

        data = client.get("/api/notifications?page=3&limit=3", headers=_auth(token)).json()
        assert len(data["notifications"]) == 1
        assert data["notifications"][0]["title"] == "n0"

    def test_pagination_beyond_last_page_is_empty(self, db_session, client, token):
        uid = _user_id(token)
        _create(db_session, uid, title="only")
        data = client.get("/api/notifications?page=5&limit=10", headers=_auth(token)).json()
        assert data["notifications"] == []
        assert data["total"] == 1

    def test_invalid_page_rejected(self, client, token):
        resp = client.get("/api/notifications?page=0", headers=_auth(token))
        assert resp.status_code == 422

    def test_invalid_limit_rejected(self, client, token):
        resp = client.get("/api/notifications?limit=0", headers=_auth(token))
        assert resp.status_code == 422
        resp = client.get("/api/notifications?limit=500", headers=_auth(token))
        assert resp.status_code == 422

    def test_filter_by_type(self, db_session, client, token):
        uid = _user_id(token)
        _create(db_session, uid, type="budget_exceeded", title="b")
        _create(db_session, uid, type="anomaly", title="a")

        data = client.get("/api/notifications?type=anomaly", headers=_auth(token)).json()
        assert data["total"] == 1
        assert data["notifications"][0]["type"] == "anomaly"

    def test_invalid_type_filter_rejected(self, client, token):
        resp = client.get("/api/notifications?type=bogus", headers=_auth(token))
        assert resp.status_code == 422

    def test_list_requires_auth(self, client):
        assert client.get("/api/notifications").status_code == 401


class TestNotificationUnreadCount:
    def test_unread_count_reflects_unread_only(self, db_session, client, token):
        uid = _user_id(token)
        _create(db_session, uid, title="unread1")
        _create(db_session, uid, title="unread2")
        _create(db_session, uid, title="read1", is_read=True)

        data = client.get("/api/notifications", headers=_auth(token)).json()
        assert data["unread_count"] == 2
        assert data["total"] == 3

    def test_unread_count_zero_when_empty(self, client, token):
        data = client.get("/api/notifications", headers=_auth(token)).json()
        assert data["unread_count"] == 0

    def test_unread_only_filter(self, db_session, client, token):
        uid = _user_id(token)
        _create(db_session, uid, title="unread")
        _create(db_session, uid, title="read", is_read=True)

        data = client.get("/api/notifications?unread_only=true", headers=_auth(token)).json()
        assert data["total"] == 1
        assert data["notifications"][0]["title"] == "unread"

    def test_unread_count_scoped_per_user(self, db_session, client, token, token2):
        uid1 = _user_id(token)
        _create(db_session, uid1, title="u1")
        _create(db_session, uid1, title="u2")
        _create(db_session, uid1, title="u3")

        data2 = client.get("/api/notifications", headers=_auth(token2)).json()
        assert data2["unread_count"] == 0
        assert data2["total"] == 0


class TestNotificationMarkRead:
    def test_mark_read(self, db_session, client, token):
        uid = _user_id(token)
        n = _create(db_session, uid, title="unread one")

        resp = client.patch(f"/api/notifications/{n.id}/read", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True

        data = client.get("/api/notifications", headers=_auth(token)).json()
        assert data["unread_count"] == 0

    def test_mark_read_is_idempotent(self, db_session, client, token):
        uid = _user_id(token)
        n = _create(db_session, uid)
        client.patch(f"/api/notifications/{n.id}/read", headers=_auth(token))
        resp = client.patch(f"/api/notifications/{n.id}/read", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True

    def test_mark_unread(self, db_session, client, token):
        uid = _user_id(token)
        n = _create(db_session, uid, is_read=True)
        resp = client.patch(f"/api/notifications/{n.id}/unread", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["is_read"] is False

    def test_mark_read_nonexistent_returns_404(self, client, token):
        resp = client.patch("/api/notifications/999999/read", headers=_auth(token))
        assert resp.status_code == 404

    def test_mark_read_requires_auth(self, client):
        # no login in this test: no Authorization header and no auth cookie
        assert client.patch("/api/notifications/1/read").status_code == 401

    def test_mark_all_read(self, db_session, client, token):
        uid = _user_id(token)
        for i in range(4):
            _create(db_session, uid, title=f"n{i}")
        _create(db_session, uid, title="already read", is_read=True)

        resp = client.patch("/api/notifications/read-all", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["updated"] == 4
        assert resp.json()["unread_count"] == 0

        data = client.get("/api/notifications", headers=_auth(token)).json()
        assert all(n["is_read"] for n in data["notifications"])
        assert data["total"] == 5

    def test_mark_all_read_only_affects_own_user(self, db_session, client, token, token2):
        uid1 = _user_id(token)
        uid2 = _user_id(token2)
        _create(db_session, uid1, title="mine")
        _create(db_session, uid2, title="theirs")

        client.patch("/api/notifications/read-all", headers=_auth(token))

        data2 = client.get("/api/notifications", headers=_auth(token2)).json()
        assert data2["unread_count"] == 1
        assert data2["notifications"][0]["is_read"] is False

    def test_mark_all_read_on_empty_list(self, client, token):
        resp = client.patch("/api/notifications/read-all", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["updated"] == 0

    def test_mark_all_read_requires_auth(self, client):
        assert client.patch("/api/notifications/read-all").status_code == 401


class TestNotificationDelete:
    def test_delete_notification(self, db_session, client, token):
        uid = _user_id(token)
        n = _create(db_session, uid, title="delete me")

        resp = client.delete(f"/api/notifications/{n.id}", headers=_auth(token))
        assert resp.status_code == 200

        data = client.get("/api/notifications", headers=_auth(token)).json()
        assert data["total"] == 0

    def test_delete_nonexistent_returns_404(self, client, token):
        resp = client.delete("/api/notifications/424242", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_requires_auth(self, client):
        assert client.delete("/api/notifications/1").status_code == 401


class TestNotificationUserIsolation:
    def test_cannot_read_other_users_notification(self, db_session, client, token, token2):
        uid1 = _user_id(token)
        n = _create(db_session, uid1, title="private")

        resp = client.patch(f"/api/notifications/{n.id}/read", headers=_auth(token2))
        assert resp.status_code == 404

    def test_cannot_delete_other_users_notification(self, db_session, client, token, token2):
        uid1 = _user_id(token)
        n = _create(db_session, uid1, title="private")

        resp = client.delete(f"/api/notifications/{n.id}", headers=_auth(token2))
        assert resp.status_code == 404

        # still present for the owner
        data = client.get("/api/notifications", headers=_auth(token)).json()
        assert data["total"] == 1

    def test_other_users_notification_not_marked_read_by_mark_all(self, db_session, client, token, token2):
        uid1 = _user_id(token)
        n = _create(db_session, uid1, title="private")

        client.patch("/api/notifications/read-all", headers=_auth(token2))

        data = client.get("/api/notifications", headers=_auth(token)).json()
        assert data["notifications"][0]["is_read"] is False
        assert data["unread_count"] == 1

    def test_list_never_exposes_other_users_notifications(self, db_session, client, token, token2):
        uid1 = _user_id(token)
        _create(db_session, uid1, title="secret one")
        _create(db_session, uid1, title="secret two")

        data2 = client.get("/api/notifications", headers=_auth(token2)).json()
        assert data2["notifications"] == []
        assert data2["total"] == 0

    def test_unread_count_never_includes_other_users(self, db_session, client, token, token2):
        uid1 = _user_id(token)
        for i in range(5):
            _create(db_session, uid1, title=f"secret {i}")

        data2 = client.get("/api/notifications", headers=_auth(token2)).json()
        assert data2["unread_count"] == 0

    def test_notification_always_scoped_to_creator(self, client, token):
        resp = client.post("/api/notifications", json=_payload(user_id=99999), headers=_auth(token))
        assert resp.status_code == 201
        assert resp.json()["user_id"] == _user_id(token)