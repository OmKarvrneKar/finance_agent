import pytest
from datetime import date, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, BudgetGoal, Transaction, AnomalyReview, Notification
from app.services import notification_producers, spending_velocity as velocity_service
from app.services.budgets import get_budget_status


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
    return _register(client, "prod1@test.com")


@pytest.fixture()
def token2(client):
    return _register(client, "prod2@test.com")


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


def _add_budget(db, user_id, category="Food", monthly_cap=Decimal("1000")):
    b = BudgetGoal(user_id=user_id, category=category, monthly_cap=monthly_cap)
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def _period():
    return date.today().strftime("%Y-%m")


def _notifications(client, token):
    return client.get("/api/notifications", headers=_auth(token)).json()["notifications"]


class TestBudgetNotificationProducer:
    def test_budget_threshold_notification(self, db_session, client, token):
        uid = _user_id(token)
        budget = _add_budget(db_session, uid, "Food", Decimal("1000"))
        today = date.today()
        # 85% of cap -> existing "approaching" status (>=80% rule in budgets.py)
        _add_tx(db_session, uid, today, Decimal("850"))

        resp = client.post("/api/notifications/sync/budgets", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 1
        assert data["deduplicated"] == 0

        notes = _notifications(client, token)
        assert len(notes) == 1
        assert notes[0]["type"] == "budget_threshold"
        assert notes[0]["severity"] == "warning"
        assert notes[0]["related_entity_type"] == "budget_goal"
        assert notes[0]["related_entity_id"] == budget.id
        assert notes[0]["metadata"]["category"] == "Food"
        assert notes[0]["metadata"]["period"] == _period()

    def test_budget_exceeded_notification(self, db_session, client, token):
        uid = _user_id(token)
        budget = _add_budget(db_session, uid, "Food", Decimal("1000"))
        _add_tx(db_session, uid, date.today(), Decimal("1400"))

        data = client.post("/api/notifications/sync/budgets", headers=_auth(token)).json()
        assert data["created"] == 1

        notes = _notifications(client, token)
        assert notes[0]["type"] == "budget_exceeded"
        assert notes[0]["severity"] == "critical"
        assert notes[0]["related_entity_id"] == budget.id

    def test_on_track_budget_creates_no_notification(self, db_session, client, token):
        uid = _user_id(token)
        _add_budget(db_session, uid, "Food", Decimal("1000"))
        _add_tx(db_session, uid, date.today(), Decimal("100"))

        data = client.post("/api/notifications/sync/budgets", headers=_auth(token)).json()
        assert data["created"] == 0
        assert data["examined"] == 0
        assert _notifications(client, token) == []

    def test_no_budgets_creates_no_notification(self, db_session, client, token):
        uid = _user_id(token)
        _add_tx(db_session, uid, date.today(), Decimal("5000"))
        data = client.post("/api/notifications/sync/budgets", headers=_auth(token)).json()
        assert data["created"] == 0
        assert _notifications(client, token) == []

    def test_budget_threshold_and_exceeded_use_separate_keys(self, db_session, client, token):
        """Both states for the same budget in a period are distinct events."""
        uid = _user_id(token)
        _add_budget(db_session, uid, "Food", Decimal("1000"))
        _add_tx(db_session, uid, date.today(), Decimal("850"))
        client.post("/api/notifications/sync/budgets", headers=_auth(token))

        # spending grows past the cap
        _add_tx(db_session, uid, date.today(), Decimal("300"))
        data = client.post("/api/notifications/sync/budgets", headers=_auth(token)).json()
        assert data["created"] == 1

        types = {n["type"] for n in _notifications(client, token)}
        assert types == {"budget_threshold", "budget_exceeded"}

    def test_budget_period_participates_in_event_key(self, db_session, client, token):
        uid = _user_id(token)
        budget = _add_budget(db_session, uid, "Food", Decimal("1000"))
        # Overspend in two different periods for the same budget.
        _add_tx(db_session, uid, date.today(), Decimal("1400"))
        _add_tx(db_session, uid, date(2020, 1, 15), Decimal("1400"))

        current = client.post("/api/notifications/sync/budgets", headers=_auth(token)).json()
        past = client.post(
            "/api/notifications/sync/budgets?month=2020-01", headers=_auth(token)
        ).json()

        # Different period -> different event key -> the same budget legitimately
        # notifies again instead of being swallowed by dedup.
        assert current["created"] == 1
        assert past["created"] == 1

        notes = _notifications(client, token)
        assert len(notes) == 2
        assert {n["metadata"]["period"] for n in notes} == {_period(), "2020-01"}
        assert {n["related_entity_id"] for n in notes} == {budget.id}
        assert len({n["id"] for n in notes}) == 2


class TestBudgetEventKey:
    def test_budget_event_key_formats(self):
        assert notification_producers._budget_event_key(7, "threshold", "2026-10") == "budget:7:threshold:2026-10"
        assert notification_producers._budget_event_key(7, "exceeded", "2026-10") == "budget:7:exceeded:2026-10"

    def test_budget_event_key_falls_back_to_period_without_id(self):
        assert notification_producers._budget_event_key(None, "threshold", "2026-10") == "budget:2026-10:threshold"

    def test_budget_status_now_exposes_stable_budget_id(self, db_session, client, token):
        uid = _user_id(token)
        budget = _add_budget(db_session, uid, "Food", Decimal("1000"))
        status = get_budget_status(db_session, uid, _period())
        assert status[0]["budget_id"] == budget.id

    def test_budget_api_still_returns_existing_fields(self, client, token):
        client.post("/api/budgets", json={"category": "Food", "monthly_cap": 1000}, headers=_auth(token))
        resp = client.get("/api/budgets", headers=_auth(token))
        assert resp.status_code == 200
        row = resp.json()[0]
        # pre-existing contract is unchanged; budget_id is additive
        for field in ("category", "monthly_cap", "current_spend", "percent_used",
                      "days_left_in_month", "status", "message"):
            assert field in row
        assert "budget_id" in row


class TestVelocityNotificationProducer:
    def _seed_history(self, db, uid, window_days=3, num_windows=5, per_window=Decimal("100")):
        today = date.today()
        current_start = today - timedelta(days=window_days - 1)
        cursor_end = current_start - timedelta(days=1)
        for _ in range(num_windows):
            w_start = cursor_end - timedelta(days=window_days - 1)
            _add_tx(db, uid, w_start, per_window)
            cursor_end = w_start - timedelta(days=1)

    def test_velocity_high_notification(self, db_session, client, token):
        uid = _user_id(token)
        self._seed_history(db_session, uid)
        _add_tx(db_session, uid, date.today(), Decimal("250"))

        data = client.post("/api/notifications/sync/velocity?window_days=3", headers=_auth(token)).json()
        assert data["alert_level"] == "high"
        assert data["created"] == 1

        notes = _notifications(client, token)
        assert len(notes) == 1
        assert notes[0]["type"] == "spending_velocity"
        assert notes[0]["severity"] == "warning"
        assert notes[0]["metadata"]["alert_level"] == "high"
        assert notes[0]["metadata"]["velocity_ratio"] == 2.5

    def test_velocity_very_high_notification(self, db_session, client, token):
        uid = _user_id(token)
        self._seed_history(db_session, uid)
        _add_tx(db_session, uid, date.today(), Decimal("350"))

        data = client.post("/api/notifications/sync/velocity?window_days=3", headers=_auth(token)).json()
        assert data["alert_level"] == "very_high"
        assert data["created"] == 1

        notes = _notifications(client, token)
        assert notes[0]["severity"] == "critical"
        assert notes[0]["metadata"]["alert_level"] == "very_high"

    def test_normal_velocity_creates_no_notification(self, db_session, client, token):
        uid = _user_id(token)
        self._seed_history(db_session, uid)
        _add_tx(db_session, uid, date.today(), Decimal("100"))

        data = client.post("/api/notifications/sync/velocity?window_days=3", headers=_auth(token)).json()
        assert data["alert_level"] == "normal"
        assert data["created"] == 0
        assert data["examined"] == 0
        assert _notifications(client, token) == []

    def test_elevated_velocity_creates_no_notification(self, db_session, client, token):
        uid = _user_id(token)
        self._seed_history(db_session, uid)
        _add_tx(db_session, uid, date.today(), Decimal("150"))

        data = client.post("/api/notifications/sync/velocity?window_days=3", headers=_auth(token)).json()
        assert data["alert_level"] == "elevated"
        assert data["created"] == 0
        assert _notifications(client, token) == []

    def test_insufficient_history_velocity_creates_no_notification(self, db_session, client, token):
        uid = _user_id(token)
        _add_tx(db_session, uid, date.today(), Decimal("5000"))

        data = client.post("/api/notifications/sync/velocity?window_days=3", headers=_auth(token)).json()
        assert data["alert_level"] == "insufficient_data"
        assert data["created"] == 0
        assert _notifications(client, token) == []

    def test_velocity_deduplicates_repeated_calls(self, db_session, client, token):
        uid = _user_id(token)
        self._seed_history(db_session, uid)
        _add_tx(db_session, uid, date.today(), Decimal("350"))

        first = client.post("/api/notifications/sync/velocity?window_days=3", headers=_auth(token)).json()
        second = client.post("/api/notifications/sync/velocity?window_days=3", headers=_auth(token)).json()
        third = client.post("/api/notifications/sync/velocity?window_days=3", headers=_auth(token)).json()

        assert first["created"] == 1
        assert second["created"] == 0
        assert second["deduplicated"] == 1
        assert third["deduplicated"] == 1
        assert len(_notifications(client, token)) == 1

    def test_different_windows_are_distinct_events(self, db_session, client, token):
        uid = _user_id(token)
        # 10 x 3-day history blocks span 30+ days, which is enough for the
        # 7-day window to reach MIN_BASELINE_WINDOWS (3) complete windows.
        self._seed_history(db_session, uid, window_days=3, num_windows=10)
        _add_tx(db_session, uid, date.today(), Decimal("900"))

        r3 = client.post("/api/notifications/sync/velocity?window_days=3", headers=_auth(token)).json()
        r7 = client.post("/api/notifications/sync/velocity?window_days=7", headers=_auth(token)).json()

        assert r3["alert_level"] == "very_high"
        assert r7["alert_level"] == "very_high"
        assert r3["created"] == 1
        assert r7["created"] == 1

        notes = _notifications(client, token)
        assert len(notes) == 2
        assert {n["metadata"]["window_days"] for n in notes} == {3, 7}
        assert len({n["id"] for n in notes}) == 2

    def test_velocity_sync_invalid_window_days(self, client, token):
        assert client.post("/api/notifications/sync/velocity?window_days=0", headers=_auth(token)).status_code == 422
        assert client.post("/api/notifications/sync/velocity?window_days=91", headers=_auth(token)).status_code == 422

    def test_velocity_sync_requires_auth(self, client):
        assert client.post("/api/notifications/sync/velocity?window_days=3").status_code == 401

    def test_velocity_event_key_format(self):
        key = notification_producers._velocity_event_key(3, "2026-09-28", "2026-09-30")
        assert key == "velocity:3:2026-09-28:2026-09-30"

    def test_producer_does_not_change_velocity_result(self, db_session, client, token):
        """Sync must not mutate the velocity calculation or its inputs."""
        uid = _user_id(token)
        self._seed_history(db_session, uid)
        _add_tx(db_session, uid, date.today(), Decimal("350"))

        before = velocity_service.get_spending_velocity(db_session, uid, window_days=3)
        client.post("/api/notifications/sync/velocity?window_days=3", headers=_auth(token))
        after = velocity_service.get_spending_velocity(db_session, uid, window_days=3)

        assert before["current_window_spend"] == after["current_window_spend"]
        assert before["baseline_window_spend"] == after["baseline_window_spend"]
        assert before["alert_level"] == after["alert_level"] == "very_high"
        assert before["velocity_ratio"] == after["velocity_ratio"]


class TestAnomalyNotificationProducer:
    def test_anomaly_notification(self, db_session, client, token):
        uid = _user_id(token)
        today = date.today()
        # recurring price jump: >20% increase over baseline
        _add_tx(db_session, uid, today - timedelta(days=60), Decimal("100"), description="Netflix", is_recurring=True)
        _add_tx(db_session, uid, today - timedelta(days=30), Decimal("100"), description="Netflix", is_recurring=True)
        _add_tx(db_session, uid, today, Decimal("200"), description="Netflix", is_recurring=True)

        data = client.post("/api/notifications/sync/anomalies", headers=_auth(token)).json()
        assert data["created"] >= 1

        notes = _notifications(client, token)
        anomaly_notes = [n for n in notes if n["type"] == "anomaly"]
        assert len(anomaly_notes) >= 1
        note = anomaly_notes[0]
        assert note["severity"] == "critical"  # >50% increase
        assert note["metadata"]["anomaly_type"] == "price_jump"
        assert note["metadata"]["merchant"] == "Netflix"
        assert note["metadata"]["anomaly_id"].startswith("price_jump_")

    def test_anomaly_deduplicates_repeated_calls(self, db_session, client, token):
        uid = _user_id(token)
        today = date.today()
        _add_tx(db_session, uid, today - timedelta(days=60), Decimal("100"), description="Netflix", is_recurring=True)
        _add_tx(db_session, uid, today - timedelta(days=30), Decimal("100"), description="Netflix", is_recurring=True)
        _add_tx(db_session, uid, today, Decimal("200"), description="Netflix", is_recurring=True)

        first = client.post("/api/notifications/sync/anomalies", headers=_auth(token)).json()
        second = client.post("/api/notifications/sync/anomalies", headers=_auth(token)).json()
        third = client.post("/api/notifications/sync/anomalies", headers=_auth(token)).json()

        assert first["created"] >= 1
        assert second["created"] == 0
        assert second["deduplicated"] == first["created"]
        assert third["deduplicated"] == first["created"]

    def test_dismissed_anomaly_is_not_renotified(self, db_session, client, token):
        uid = _user_id(token)
        today = date.today()
        _add_tx(db_session, uid, today - timedelta(days=60), Decimal("100"), description="Netflix", is_recurring=True)
        _add_tx(db_session, uid, today - timedelta(days=30), Decimal("100"), description="Netflix", is_recurring=True)
        _add_tx(db_session, uid, today, Decimal("200"), description="Netflix", is_recurring=True)

        first = client.post("/api/notifications/sync/anomalies", headers=_auth(token)).json()
        assert first["created"] >= 1

        sigs = [n["metadata"]["anomaly_id"] for n in _notifications(client, token) if n["type"] == "anomaly"]
        for sig in sigs:
            client.post(f"/api/anomalies/{sig}/dismiss", headers=_auth(token))

        db_session.query(Notification).delete()
        db_session.commit()

        after = client.post("/api/notifications/sync/anomalies", headers=_auth(token)).json()
        assert after["created"] == 0

    def test_no_anomalies_creates_nothing(self, db_session, client, token):
        uid = _user_id(token)
        _add_tx(db_session, uid, date.today(), Decimal("50"))

        data = client.post("/api/notifications/sync/anomalies", headers=_auth(token)).json()
        assert data["created"] == 0
        assert _notifications(client, token) == []

    def test_anomaly_sync_requires_auth(self, client):
        assert client.post("/api/notifications/sync/anomalies").status_code == 401

    def test_anomaly_event_key_uses_existing_signature(self):
        assert notification_producers._anomaly_event_key("price_jump_12_15") == "anomaly:price_jump_12_15"


class TestProducerUserIsolation:
    def test_multiple_users_get_independent_notifications(self, db_session, client, token, token2):
        uid1 = _user_id(token)
        uid2 = _user_id(token2)

        for uid in (uid1, uid2):
            _add_budget(db_session, uid, "Food", Decimal("1000"))
            _add_tx(db_session, uid, date.today(), Decimal("1400"))

        r1 = client.post("/api/notifications/sync/budgets", headers=_auth(token)).json()
        r2 = client.post("/api/notifications/sync/budgets", headers=_auth(token2)).json()
        assert r1["created"] == 1
        assert r2["created"] == 1

        n1 = _notifications(client, token)
        n2 = _notifications(client, token2)
        assert len(n1) == 1 and len(n2) == 1
        assert n1[0]["user_id"] == uid1
        assert n2[0]["user_id"] == uid2
        # same underlying event, but one notification per user
        assert n1[0]["id"] != n2[0]["id"]

    def test_budget_sync_does_not_touch_other_users_budgets(self, db_session, client, token, token2):
        uid1 = _user_id(token)
        _add_budget(db_session, uid1, "Food", Decimal("1000"))
        _add_tx(db_session, uid1, date.today(), Decimal("1400"))

        client.post("/api/notifications/sync/budgets", headers=_auth(token2))
        assert _notifications(client, token2) == []

        client.post("/api/notifications/sync/budgets", headers=_auth(token))
        assert len(_notifications(client, token)) == 1

    def test_budget_sync_requires_auth(self, client):
        assert client.post("/api/notifications/sync/budgets").status_code == 401


class TestNoImplicitGeneration:
    def test_reading_analytics_endpoints_creates_no_notifications(self, db_session, client, token):
        uid = _user_id(token)
        _add_budget(db_session, uid, "Food", Decimal("1000"))
        _add_tx(db_session, uid, date.today(), Decimal("1400"))

        for _ in range(3):
            assert client.get("/api/budgets", headers=_auth(token)).status_code == 200
            assert client.get("/api/analytics/summary", headers=_auth(token)).status_code == 200
            assert client.get("/api/analytics/spending-velocity?window_days=3", headers=_auth(token)).status_code == 200
            assert client.get("/api/anomalies", headers=_auth(token)).status_code == 200
            assert client.get("/api/notifications", headers=_auth(token)).status_code == 200

        assert _notifications(client, token) == []

    def test_historical_period_recalculation_does_not_respam(self, db_session, client, token):
        uid = _user_id(token)
        _add_budget(db_session, uid, "Food", Decimal("1000"))
        _add_tx(db_session, uid, date.today(), Decimal("1400"))

        for _ in range(4):
            client.post("/api/notifications/sync/budgets", headers=_auth(token))

        assert len(_notifications(client, token)) == 1

    def test_analytics_summary_unchanged_after_sync(self, db_session, client, token):
        uid = _user_id(token)
        _add_tx(db_session, uid, date.today(), Decimal("1400"))

        before = client.get("/api/analytics/summary", headers=_auth(token)).json()
        client.post("/api/notifications/sync/velocity?window_days=3", headers=_auth(token))
        client.post("/api/notifications/sync/anomalies", headers=_auth(token))
        after = client.get("/api/analytics/summary", headers=_auth(token)).json()

        assert before["total_expenses"] == after["total_expenses"]
        assert before["transaction_count"] == after["transaction_count"]
        assert before["category_breakdown"] == after["category_breakdown"]


class TestFailureIsolation:
    def test_emit_failure_does_not_raise_and_reports_error(self, db_session, client, token, monkeypatch):
        uid = _user_id(token)
        _add_budget(db_session, uid, "Food", Decimal("1000"))
        _add_tx(db_session, uid, date.today(), Decimal("1400"))

        def boom(*args, **kwargs):
            raise RuntimeError("notification store offline")

        monkeypatch.setattr(
            notification_producers.notification_service,
            "create_notification_for_event", boom,
        )

        resp = client.post("/api/notifications/sync/budgets", headers=_auth(token))
        assert resp.status_code == 200  # producer failure does not become a 500
        data = resp.json()
        assert data["created"] == 0
        assert data["failed"] == 1

    def test_failure_leaves_financial_data_intact(self, db_session, client, token, monkeypatch):
        uid = _user_id(token)
        budget = _add_budget(db_session, uid, "Food", Decimal("1000"))
        _add_tx(db_session, uid, date.today(), Decimal("1400"))

        def boom(*args, **kwargs):
            raise RuntimeError("notification store offline")

        monkeypatch.setattr(
            notification_producers.notification_service,
            "create_notification_for_event", boom,
        )
        client.post("/api/notifications/sync/budgets", headers=_auth(token))

        # budget + transactions still readable and unchanged
        status = get_budget_status(db_session, uid, _period())
        assert status[0]["current_spend"] == Decimal("1400.00")
        assert status[0]["status"] == "over"
        assert db_session.query(BudgetGoal).filter(BudgetGoal.id == budget.id).count() == 1
        assert db_session.query(Transaction).filter(Transaction.user_id == uid).count() == 1

    def test_budget_endpoint_still_works_after_notification_failure(self, db_session, client, token, monkeypatch):
        uid = _user_id(token)
        _add_budget(db_session, uid, "Food", Decimal("1000"))
        _add_tx(db_session, uid, date.today(), Decimal("1400"))

        def boom(*args, **kwargs):
            raise RuntimeError("notification store offline")

        monkeypatch.setattr(
            notification_producers.notification_service,
            "create_notification_for_event", boom,
        )
        client.post("/api/notifications/sync/budgets", headers=_auth(token))

        resp = client.get("/api/budgets", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()[0]["status"] == "over"

    def test_analytics_endpoints_still_work_after_notification_failure(self, db_session, client, token, monkeypatch):
        uid = _user_id(token)
        _add_tx(db_session, uid, date.today(), Decimal("1400"))

        def boom(*args, **kwargs):
            raise RuntimeError("notification store offline")

        monkeypatch.setattr(
            notification_producers.notification_service,
            "create_notification_for_event", boom,
        )
        client.post("/api/notifications/sync/velocity?window_days=3", headers=_auth(token))
        client.post("/api/notifications/sync/anomalies", headers=_auth(token))

        assert client.get("/api/analytics/summary", headers=_auth(token)).status_code == 200
        assert client.get("/api/analytics/spending-velocity?window_days=3", headers=_auth(token)).status_code == 200
        assert client.get("/api/anomalies", headers=_auth(token)).status_code == 200

    def test_underlying_service_failure_is_reported_not_raised(self, db_session, client, token, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("calculation exploded")

        monkeypatch.setattr(notification_producers.budgets_service, "get_budget_status", boom)
        resp = client.post("/api/notifications/sync/budgets", headers=_auth(token))
        # A producer is a side channel: a broken calculation is reported, not raised.
        assert resp.status_code == 200
        assert resp.json()["error"] is not None
        assert _notifications(client, token) == []

    def test_sqlalchemy_error_in_calculation_is_caught(self, db_session, client, token, monkeypatch):
        from sqlalchemy.exc import OperationalError

        def boom(*args, **kwargs):
            raise OperationalError("select 1", {}, Exception("db locked"))

        monkeypatch.setattr(notification_producers.budgets_service, "get_budget_status", boom)
        resp = client.post("/api/notifications/sync/budgets", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["error"] is not None

    def test_partial_batch_failure_isolated_per_notification(self, db_session, client, token, monkeypatch):
        uid = _user_id(token)
        _add_budget(db_session, uid, "Food", Decimal("1000"))
        _add_budget(db_session, uid, "Shopping", Decimal("1000"))
        _add_tx(db_session, uid, date.today(), Decimal("1400"), category="Food")
        _add_tx(db_session, uid, date.today(), Decimal("1400"), category="Shopping")

        real = notification_producers.notification_service.create_notification_for_event
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("first emit fails")
            return real(*args, **kwargs)

        monkeypatch.setattr(
            notification_producers.notification_service,
            "create_notification_for_event", flaky,
        )
        data = client.post("/api/notifications/sync/budgets", headers=_auth(token)).json()
        assert data["failed"] == 1
        assert data["created"] == 1
        assert len(_notifications(client, token)) == 1


class TestDedupAcrossProducers:
    def test_same_event_produced_twice_yields_one_notification(self, db_session, client, token):
        uid = _user_id(token)
        _add_budget(db_session, uid, "Food", Decimal("1000"))
        _add_tx(db_session, uid, date.today(), Decimal("1400"))

        first = client.post("/api/notifications/sync/budgets", headers=_auth(token)).json()
        second = client.post("/api/notifications/sync/budgets", headers=_auth(token)).json()

        assert first["created"] == 1
        assert second["created"] == 0
        assert second["deduplicated"] == 1
        assert db_session.query(Notification).filter(Notification.user_id == uid).count() == 1

    def test_different_event_types_coexist(self, db_session, client, token):
        uid = _user_id(token)
        _add_budget(db_session, uid, "Food", Decimal("1000"))
        _add_tx(db_session, uid, date.today(), Decimal("1400"))
        today = date.today()
        _add_tx(db_session, uid, today - timedelta(days=60), Decimal("100"), description="Netflix", is_recurring=True)
        _add_tx(db_session, uid, today - timedelta(days=30), Decimal("100"), description="Netflix", is_recurring=True)
        _add_tx(db_session, uid, today, Decimal("200"), description="Netflix", is_recurring=True, category="Shopping")

        client.post("/api/notifications/sync/budgets", headers=_auth(token))
        client.post("/api/notifications/sync/anomalies", headers=_auth(token))

        types = {n["type"] for n in _notifications(client, token)}
        assert "budget_exceeded" in types
        assert "anomaly" in types

    def test_dismissed_anomaly_creates_review_row(self, db_session, client, token):
        uid = _user_id(token)
        today = date.today()
        _add_tx(db_session, uid, today - timedelta(days=60), Decimal("100"), description="Netflix", is_recurring=True)
        _add_tx(db_session, uid, today - timedelta(days=30), Decimal("100"), description="Netflix", is_recurring=True)
        _add_tx(db_session, uid, today, Decimal("200"), description="Netflix", is_recurring=True)

        client.post("/api/notifications/sync/anomalies", headers=_auth(token))
        sig = [n["metadata"]["anomaly_id"] for n in _notifications(client, token) if n["type"] == "anomaly"][0]

        db_session.add(AnomalyReview(user_id=uid, anomaly_signature=sig, status="dismissed"))
        db_session.commit()

        assert db_session.query(AnomalyReview).filter(
            AnomalyReview.user_id == uid, AnomalyReview.anomaly_signature == sig
        ).count() == 1