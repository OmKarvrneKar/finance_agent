"""Phase 5A: write-path wiring proves producers fire from real product flows.

Each test drives a real authenticated endpoint (budget save, statement
upload, receipt confirm) and proves the existing producers emit (or do not
emit) notifications, with deduplication preserved and strict user isolation.
"""

import io
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, BudgetGoal, PendingReceipt, Transaction


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


def _register(client, email):
    client.post("/api/auth/register", json={"email": email, "password": "Password123", "full_name": "N"})
    resp = client.post("/api/auth/login", data={"username": email, "password": "Password123"})
    return resp.json()["access_token"]


@pytest.fixture()
def token(client):
    return _register(client, "flow1@test.com")


@pytest.fixture()
def token2(client):
    return _register(client, "flow2@test.com")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _user_id(token):
    import jwt
    from app.auth import JWT_SECRET_KEY
    return int(jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])["sub"])


def _add_tx(db, user_id, tx_date, amount, tx_type="debit", description="Spend", category="Food", is_recurring=False):
    db.add(Transaction(
        user_id=user_id, date=tx_date, description=description,
        amount=Decimal(str(amount)), transaction_type=tx_type,
        category=category, is_recurring=is_recurring,
    ))
    db.commit()


def _notifications(client, token):
    return client.get("/api/notifications", headers=_auth(token)).json()["notifications"]


def _tx_entry(tx_date, description, amount, tx_type="debit", category="Food", is_recurring=False):
    return {
        "date": tx_date,
        "description": description,
        "amount": amount,
        "transaction_type": tx_type,
        "raw_text": "",
        "category": category,
        "subcategory": None,
        "is_recurring": is_recurring,
    }


def _upload(client, token, categorized):
    csv_bytes = b"Date,Description,Debit,Credit\n2026-07-01,Amazon,49.99,\n"
    with patch("app.routers.transactions.categorize_transactions") as mock:
        mock.return_value = categorized
        return client.post(
            "/api/upload-statement",
            files={"file": ("tx.csv", io.BytesIO(csv_bytes), "text/csv")},
            headers=_auth(token),
        )


def _seed_velocity_history(db, uid, per_window=Decimal("100"), num_windows=5, window_days=3):
    today = date.today()
    current_start = today - timedelta(days=window_days - 1)
    cursor_end = current_start - timedelta(days=1)
    for _ in range(num_windows):
        w_start = cursor_end - timedelta(days=window_days - 1)
        _add_tx(db, uid, w_start, per_window)
        cursor_end = w_start - timedelta(days=1)


def _seed_netflix_jump(db, uid):
    today = date.today()
    _add_tx(db, uid, today - timedelta(days=60), Decimal("100"), description="Netflix", is_recurring=True)
    _add_tx(db, uid, today - timedelta(days=30), Decimal("100"), description="Netflix", is_recurring=True)


def _save_budget(client, token, category, cap):
    return client.post(
        "/api/budgets",
        json={"category": category, "monthly_cap": cap},
        headers=_auth(token),
    )


class TestBudgetSaveFlow:
    def test_budget_save_creates_exceeded_notification(self, db_session, client, token):
        uid = _user_id(token)
        _add_tx(db_session, uid, date.today(), Decimal("1400"))

        resp = _save_budget(client, token, "Food", 1000)
        assert resp.status_code == 200
        assert resp.json()["category"] == "Food"

        notes = _notifications(client, token)
        assert len(notes) == 1
        assert notes[0]["type"] == "budget_exceeded"
        assert notes[0]["severity"] == "critical"
        assert notes[0]["user_id"] == uid
        assert notes[0]["related_entity_type"] == "budget_goal"
        assert notes[0]["related_entity_id"] == resp.json()["id"]
        assert notes[0]["metadata"]["category"] == "Food"
        assert notes[0]["metadata"]["period"] == date.today().strftime("%Y-%m")

    def test_budget_save_onttrack_creates_nothing(self, db_session, client, token):
        uid = _user_id(token)
        _add_tx(db_session, uid, date.today(), Decimal("100"))

        resp = _save_budget(client, token, "Food", 1000)
        assert resp.status_code == 200
        assert _notifications(client, token) == []

    def test_repeated_budget_save_does_not_duplicate(self, db_session, client, token):
        uid = _user_id(token)
        _add_tx(db_session, uid, date.today(), Decimal("1400"))

        first = _save_budget(client, token, "Food", 1000)
        second = _save_budget(client, token, "Food", 900)
        third = _save_budget(client, token, "Food", 800)
        assert first.status_code == second.status_code == third.status_code == 200

        notes = _notifications(client, token)
        assert len(notes) == 1
        assert notes[0]["type"] == "budget_exceeded"
        assert notes[0]["related_entity_id"] == first.json()["id"]

    def test_upload_crossing_cap_creates_budget_notification(self, db_session, client, token):
        uid = _user_id(token)
        assert _save_budget(client, token, "Food", 100).status_code == 200
        assert _notifications(client, token) == []

        resp = _upload(client, token, [_tx_entry(date.today(), "Groceries", 500.0, category="Food")])
        assert resp.status_code == 200
        assert resp.json()["new_transactions"] == 1

        notes = _notifications(client, token)
        assert len(notes) == 1
        assert notes[0]["type"] == "budget_exceeded"
        assert notes[0]["user_id"] == uid


class TestUploadFlowVelocity:
    def test_upload_spike_creates_velocity_notification(self, db_session, client, token):
        uid = _user_id(token)
        _seed_velocity_history(db_session, uid)

        resp = _upload(client, token, [_tx_entry(date.today(), "Big Shop", 250.0, category="Shopping")])
        assert resp.status_code == 200

        notes = _notifications(client, token)
        assert len(notes) == 1
        assert notes[0]["type"] == "spending_velocity"
        assert notes[0]["severity"] == "warning"
        assert notes[0]["user_id"] == uid
        assert notes[0]["metadata"]["alert_level"] == "high"
        assert notes[0]["metadata"]["velocity_ratio"] == 2.5

    def test_repeated_upload_same_window_deduplicates(self, db_session, client, token):
        uid = _user_id(token)
        _seed_velocity_history(db_session, uid)

        first = _upload(client, token, [_tx_entry(date.today(), "Big Shop", 250.0, category="Shopping")])
        second = _upload(client, token, [_tx_entry(date.today(), "More Shop", 300.0, category="Shopping")])
        assert first.status_code == 200
        assert second.status_code == 200

        notes = _notifications(client, token)
        velocity_notes = [n for n in notes if n["type"] == "spending_velocity"]
        assert len(velocity_notes) == 1
        assert len(notes) == 1


class TestUploadFlowAnomaly:
    def test_upload_price_jump_creates_anomaly_notification(self, db_session, client, token):
        uid = _user_id(token)
        _seed_netflix_jump(db_session, uid)

        resp = _upload(
            client, token,
            [_tx_entry(date.today(), "Netflix", 200.0, is_recurring=True)],
        )
        assert resp.status_code == 200

        notes = _notifications(client, token)
        anomaly_notes = [n for n in notes if n["type"] == "anomaly"]
        assert len(anomaly_notes) == 1
        note = anomaly_notes[0]
        assert note["severity"] == "critical"
        assert note["user_id"] == uid
        assert note["metadata"]["anomaly_type"] == "price_jump"
        assert note["metadata"]["merchant"] == "Netflix"
        assert note["metadata"]["anomaly_id"].startswith("price_jump_")

    def test_manual_sync_after_flow_deduplicates(self, db_session, client, token):
        uid = _user_id(token)
        _seed_netflix_jump(db_session, uid)

        resp = _upload(
            client, token,
            [_tx_entry(date.today(), "Netflix", 200.0, is_recurring=True)],
        )
        assert resp.status_code == 200
        assert len([n for n in _notifications(client, token) if n["type"] == "anomaly"]) == 1

        data = client.post("/api/notifications/sync/anomalies", headers=_auth(token)).json()
        assert data["created"] == 0
        assert data["deduplicated"] >= 1
        assert len([n for n in _notifications(client, token) if n["type"] == "anomaly"]) == 1


class TestNonQualifyingConditions:
    def test_upload_without_qualifying_conditions_creates_nothing(self, db_session, client, token):
        resp = _upload(client, token, [_tx_entry(date.today(), "Coffee", 49.99, category="Shopping")])
        assert resp.status_code == 200
        assert _notifications(client, token) == []

    def test_onttrack_budget_save_after_upload_creates_nothing(self, db_session, client, token):
        resp = _upload(client, token, [_tx_entry(date.today(), "Coffee", 49.99, category="Shopping")])
        assert resp.status_code == 200

        assert _save_budget(client, token, "Shopping", 1000).status_code == 200
        assert _save_budget(client, token, "Food", 1000).status_code == 200
        assert _notifications(client, token) == []


class TestReceiptConfirmFlow:
    def test_receipt_confirm_creates_velocity_notification(self, db_session, client, token):
        uid = _user_id(token)
        _seed_velocity_history(db_session, uid)

        pending = PendingReceipt(
            user_id=uid, image_path="fake.jpg", raw_text="raw",
            merchant="Store", amount=Decimal("250"),
            date=date.today(), category="Shopping",
        )
        db_session.add(pending)
        db_session.commit()
        db_session.refresh(pending)

        resp = client.post(
            f"/api/receipts/{pending.id}/confirm",
            json={
                "merchant": "Store",
                "date": date.today().isoformat(),
                "amount": "250",
                "category": "Shopping",
            },
            headers=_auth(token),
        )
        assert resp.status_code == 200

        notes = _notifications(client, token)
        assert len(notes) == 1
        assert notes[0]["type"] == "spending_velocity"
        assert notes[0]["user_id"] == uid


class TestUserIsolation:
    def test_flow_notifies_only_the_flow_user(self, db_session, client, token, token2):
        uid1 = _user_id(token)
        uid2 = _user_id(token2)

        _add_tx(db_session, uid1, date.today(), Decimal("1400"))
        assert _save_budget(client, token, "Food", 1000).status_code == 200

        notes1 = _notifications(client, token)
        assert len(notes1) == 1
        assert notes1[0]["user_id"] == uid1

        assert _notifications(client, token2) == []

        _add_tx(db_session, uid2, date.today(), Decimal("1400"))
        assert _save_budget(client, token2, "Food", 1000).status_code == 200

        notes2 = _notifications(client, token2)
        assert len(notes2) == 1
        assert notes2[0]["user_id"] == uid2

        notes1_after = _notifications(client, token)
        assert len(notes1_after) == 1
        assert notes1_after[0]["id"] == notes1[0]["id"]

    def test_upload_flow_is_user_scoped(self, db_session, client, token, token2):
        uid1 = _user_id(token)
        _seed_velocity_history(db_session, uid1)

        resp = _upload(client, token, [_tx_entry(date.today(), "Big Shop", 250.0, category="Shopping")])
        assert resp.status_code == 200

        assert len(_notifications(client, token)) == 1
        assert _notifications(client, token2) == []


class TestNotificationCrudStillWorks:
    def test_full_crud_cycle_on_flow_created_notification(self, db_session, client, token):
        uid = _user_id(token)
        _add_tx(db_session, uid, date.today(), Decimal("1400"))
        assert _save_budget(client, token, "Food", 1000).status_code == 200

        listing = client.get("/api/notifications", headers=_auth(token)).json()
        assert listing["total"] == 1
        assert listing["unread_count"] == 1
        note_id = listing["notifications"][0]["id"]

        read = client.patch(f"/api/notifications/{note_id}/read", headers=_auth(token))
        assert read.status_code == 200
        assert read.json()["is_read"] is True

        unread = client.get("/api/notifications?unread_only=true", headers=_auth(token)).json()
        assert unread["notifications"] == []
        assert unread["unread_count"] == 0

        unread_again = client.patch(f"/api/notifications/{note_id}/unread", headers=_auth(token))
        assert unread_again.status_code == 200
        assert unread_again.json()["is_read"] is False

        deleted = client.delete(f"/api/notifications/{note_id}", headers=_auth(token))
        assert deleted.status_code == 200

        after = client.get("/api/notifications", headers=_auth(token)).json()
        assert after["total"] == 0
        assert after["unread_count"] == 0
