import pytest
from datetime import date, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, Transaction, TransactionSplit
from app.services.spending_velocity import (
    get_spending_velocity,
    MIN_BASELINE_WINDOWS,
    MAX_BASELINE_WINDOWS,
    DEFAULT_WINDOW_DAYS,
)


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


@pytest.fixture()
def user1_token(client):
    client.post("/api/auth/register", json={"email": "sv1@test.com", "password": "Password123", "full_name": "SV1"})
    resp = client.post("/api/auth/login", data={"username": "sv1@test.com", "password": "Password123"})
    return resp.json()["access_token"]


@pytest.fixture()
def user2_token(client):
    client.post("/api/auth/register", json={"email": "sv2@test.com", "password": "Password123", "full_name": "SV2"})
    resp = client.post("/api/auth/login", data={"username": "sv2@test.com", "password": "Password123"})
    return resp.json()["access_token"]


def _get_user_id(token: str) -> int:
    import jwt
    from app.auth import JWT_SECRET_KEY
    return int(jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])["sub"])


def _add_tx(db, user_id, tx_date, amount, tx_type="debit", description="Spend"):
    db.add(Transaction(
        user_id=user_id,
        date=tx_date,
        description=description,
        amount=Decimal(str(amount)),
        transaction_type=tx_type,
        category="Other",
    ))
    db.commit()


def _add_split(db, user_id, transaction_id, category, amount):
    db.add(TransactionSplit(
        transaction_id=transaction_id,
        user_id=user_id,
        category=category,
        amount=Decimal(str(amount)),
    ))
    db.commit()


def _seed_prior_windows(
    db,
    user_id,
    today,
    window_days=3,
    num_windows=5,
    spend_per_window=Decimal("100"),
    tx_type="debit",
):
    """Seed one transaction per prior non-overlapping window immediately before today's window.

    Transaction is placed on the first day of each window so history coverage
    starts at the earliest complete window boundary.
    """
    current_start = today - timedelta(days=window_days - 1)
    cursor_end = current_start - timedelta(days=1)
    for _ in range(num_windows):
        w_end = cursor_end
        w_start = w_end - timedelta(days=window_days - 1)
        _add_tx(db, user_id, w_start, spend_per_window, tx_type=tx_type, description="hist")
        cursor_end = w_start - timedelta(days=1)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestSpendingVelocityAPI:
    def test_api_normal_spending(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        _seed_prior_windows(db_session, uid, today, 3, 5, Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("100"))

        resp = client.get(
            "/api/analytics/spending-velocity?window_days=3",
            headers=_auth(user1_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(str(data["current_window_spend"])) == Decimal("100.00")
        assert Decimal(str(data["baseline_window_spend"])) == Decimal("100.00")
        assert data["velocity_ratio"] == 1.0
        assert data["percentage_change"] == 0.0
        assert data["window_days"] == 3
        assert data["alert_level"] == "normal"
        assert data["start_date"] == (today - timedelta(days=2)).isoformat()
        assert data["end_date"] == today.isoformat()
        assert data["baseline_method"]
        assert "debit" in data["baseline_method"].lower()
        assert "1.25" in data["baseline_method"]

    def test_api_elevated_spending(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        _seed_prior_windows(db_session, uid, today, 3, 5, Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("150"))

        resp = client.get(
            "/api/analytics/spending-velocity?window_days=3",
            headers=_auth(user1_token),
        )
        data = resp.json()
        assert data["alert_level"] == "elevated"
        assert data["velocity_ratio"] == 1.5
        assert data["percentage_change"] == 50.0

    def test_api_high_spending(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        _seed_prior_windows(db_session, uid, today, 3, 5, Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("250"))

        resp = client.get(
            "/api/analytics/spending-velocity?window_days=3",
            headers=_auth(user1_token),
        )
        data = resp.json()
        assert data["alert_level"] == "high"
        assert data["velocity_ratio"] == 2.5

    def test_api_very_high_spending(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        _seed_prior_windows(db_session, uid, today, 3, 5, Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("350"))

        resp = client.get(
            "/api/analytics/spending-velocity?window_days=3",
            headers=_auth(user1_token),
        )
        data = resp.json()
        assert data["alert_level"] == "very_high"
        assert data["velocity_ratio"] == 3.5

    def test_api_insufficient_history(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        _seed_prior_windows(db_session, uid, today, 3, 1, Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("5000"))

        resp = client.get(
            "/api/analytics/spending-velocity?window_days=3",
            headers=_auth(user1_token),
        )
        data = resp.json()
        assert data["alert_level"] == "insufficient_data"
        assert data["baseline_windows_used"] == 1
        assert data["baseline_windows_used"] < MIN_BASELINE_WINDOWS

    def test_api_requires_auth(self, client):
        resp = client.get("/api/analytics/spending-velocity?window_days=3")
        assert resp.status_code == 401

    def test_invalid_window_days_zero(self, client, user1_token):
        resp = client.get(
            "/api/analytics/spending-velocity?window_days=0",
            headers=_auth(user1_token),
        )
        assert resp.status_code == 422

    def test_invalid_window_days_negative(self, client, user1_token):
        resp = client.get(
            "/api/analytics/spending-velocity?window_days=-5",
            headers=_auth(user1_token),
        )
        assert resp.status_code == 422

    def test_invalid_window_days_too_large(self, client, user1_token):
        resp = client.get(
            "/api/analytics/spending-velocity?window_days=91",
            headers=_auth(user1_token),
        )
        assert resp.status_code == 422

    def test_max_allowed_window_days(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        _seed_prior_windows(db_session, uid, today, window_days=90, num_windows=3, spend_per_window=Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("100"))

        resp = client.get(
            "/api/analytics/spending-velocity?window_days=90",
            headers=_auth(user1_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["window_days"] == 90
        assert data["alert_level"] == "normal"

    def test_default_window_days_is_three(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        _seed_prior_windows(db_session, uid, today, DEFAULT_WINDOW_DAYS, 5, Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("100"))

        resp = client.get(
            "/api/analytics/spending-velocity",
            headers=_auth(user1_token),
        )
        assert resp.status_code == 200
        assert resp.json()["window_days"] == DEFAULT_WINDOW_DAYS

    def test_user_isolation(self, db_session, client, user1_token, user2_token):
        uid1 = _get_user_id(user1_token)
        uid2 = _get_user_id(user2_token)
        today = date.today()
        window_days = 3
        _seed_prior_windows(db_session, uid1, today, window_days, 5, Decimal("100"))
        _add_tx(db_session, uid1, today, Decimal("350"))

        resp2 = client.get(
            "/api/analytics/spending-velocity?window_days=3",
            headers=_auth(user2_token),
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert Decimal(str(data2["current_window_spend"])) == Decimal("0.00")
        assert data2["alert_level"] == "insufficient_data"

        resp1 = client.get(
            "/api/analytics/spending-velocity?window_days=3",
            headers=_auth(user1_token),
        )
        assert Decimal(str(resp1.json()["current_window_spend"])) == Decimal("350.00")
        assert resp1.json()["alert_level"] == "very_high"


class TestSpendingVelocityService:
    def test_normal_spending_ratio_near_baseline(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        _seed_prior_windows(db_session, uid, today, window_days, num_windows=5, spend_per_window=Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("100"), description="now")

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert Decimal(str(result["current_window_spend"])) == Decimal("100.00")
        assert Decimal(str(result["baseline_window_spend"])) == Decimal("100.00")
        assert result["velocity_ratio"] == 1.0
        assert result["percentage_change"] == 0.0
        assert result["alert_level"] == "normal"
        assert result["baseline_windows_used"] == 5

    def test_large_absolute_amount_with_matching_history_is_normal(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        _seed_prior_windows(
            db_session, uid, today, window_days,
            num_windows=5, spend_per_window=Decimal("5000"),
        )
        _add_tx(db_session, uid, today, Decimal("5000"), description="big but normal pace")

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert result["alert_level"] == "normal"
        assert Decimal(str(result["current_window_spend"])) == Decimal("5000.00")

    def test_zero_historical_baseline(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        current_start = today - timedelta(days=window_days - 1)
        cursor_end = current_start - timedelta(days=1)
        for _ in range(5):
            w_end = cursor_end
            w_start = w_end - timedelta(days=window_days - 1)
            _add_tx(db_session, uid, w_start, Decimal("200"), tx_type="credit", description="income")
            cursor_end = w_start - timedelta(days=1)
        _add_tx(db_session, uid, today, Decimal("300"), description="current spend")

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert Decimal(str(result["current_window_spend"])) == Decimal("300.00")
        assert Decimal(str(result["baseline_window_spend"])) == Decimal("0.00")
        assert result["velocity_ratio"] is None
        assert result["percentage_change"] is None
        assert result["alert_level"] == "no_baseline"
        assert result["baseline_windows_used"] == 5

    def test_no_data_at_all_insufficient(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        result = get_spending_velocity(db_session, uid, window_days=3, today=today)
        assert result["alert_level"] == "insufficient_data"
        assert Decimal(str(result["current_window_spend"])) == Decimal("0.00")
        assert Decimal(str(result["baseline_window_spend"])) == Decimal("0.00")
        assert result["baseline_windows_used"] == 0
        assert result["history_start_date"] is None

    def test_income_and_credit_exclusion(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        _seed_prior_windows(db_session, uid, today, window_days, 5, Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("9999"), tx_type="credit", description="salary")
        _add_tx(db_session, uid, today - timedelta(days=1), Decimal("50"), tx_type="debit", description="real")

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert Decimal(str(result["current_window_spend"])) == Decimal("50.00")
        assert result["alert_level"] == "normal"

    def test_date_boundaries_inclusive(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        start_date = today - timedelta(days=window_days - 1)

        _seed_prior_windows(db_session, uid, today, window_days, 5, Decimal("100"))

        _add_tx(db_session, uid, start_date - timedelta(days=1), Decimal("40"), description="day before window")
        _add_tx(db_session, uid, start_date, Decimal("30"), description="first day of window")
        _add_tx(db_session, uid, today, Decimal("30"), description="last day of window")

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert Decimal(str(result["current_window_spend"])) == Decimal("60.00")
        assert result["start_date"] == start_date.isoformat()
        assert result["end_date"] == today.isoformat()

    def test_future_transactions_excluded(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        _seed_prior_windows(db_session, uid, today, window_days, 5, Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("100"), description="current")
        _add_tx(db_session, uid, today + timedelta(days=1), Decimal("9999"), description="future")
        _add_tx(db_session, uid, today + timedelta(days=10), Decimal("5000"), description="far future")

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert Decimal(str(result["current_window_spend"])) == Decimal("100.00")
        assert result["alert_level"] == "normal"

    def test_decimal_precision(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        _seed_prior_windows(
            db_session, uid, today, window_days,
            num_windows=5, spend_per_window=Decimal("10.01"),
        )
        _add_tx(db_session, uid, today, Decimal("10.01"))
        _add_tx(db_session, uid, today - timedelta(days=1), Decimal("20.02"))

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert Decimal(str(result["current_window_spend"])) == Decimal("30.03")
        assert Decimal(str(result["baseline_window_spend"])) == Decimal("10.01")
        assert result["velocity_ratio"] == 3.0
        assert result["alert_level"] == "very_high"

    def test_split_transactions_no_double_counting(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        _seed_prior_windows(db_session, uid, today, window_days, 5, Decimal("100"))

        _add_tx(db_session, uid, today, Decimal("100"), description="split parent")
        db_session.flush()
        parent = (
            db_session.query(Transaction)
            .filter(
                Transaction.user_id == uid,
                Transaction.description == "split parent",
            )
            .first()
        )
        _add_split(db_session, uid, parent.id, "Food", Decimal("60"))
        _add_split(db_session, uid, parent.id, "Transport", Decimal("40"))

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert Decimal(str(result["current_window_spend"])) == Decimal("100.00")
        assert result["alert_level"] == "normal"

    def test_zero_spend_current_with_baseline(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        _seed_prior_windows(db_session, uid, today, window_days, 5, Decimal("100"))

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert Decimal(str(result["current_window_spend"])) == Decimal("0.00")
        assert Decimal(str(result["baseline_window_spend"])) == Decimal("100.00")
        assert result["velocity_ratio"] == 0.0
        assert result["percentage_change"] == -100.0
        assert result["alert_level"] == "normal"

    def test_history_start_date_reported(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        current_start = today - timedelta(days=window_days - 1)
        earliest = current_start - timedelta(days=15)
        _add_tx(db_session, uid, earliest, Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("100"))

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert result["history_start_date"] == earliest.isoformat()
        assert result["baseline_windows_used"] == 5

    def test_methodology_documents_thresholds(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        result = get_spending_velocity(db_session, uid, window_days=3, today=today)
        method = result["baseline_method"]
        assert "non-overlapping" in method
        assert "debit" in method.lower()
        assert "1.25" in method
        assert "2.00" in method
        assert "3.00" in method
        assert "absolute spend alone never triggers" in method.lower()

    def test_three_windows_enough_for_strong_alert(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        _seed_prior_windows(db_session, uid, today, window_days, 3, Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("350"))

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert result["baseline_windows_used"] == 3
        assert result["alert_level"] == "very_high"

    def test_two_windows_never_strong_alert(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        _seed_prior_windows(db_session, uid, today, window_days, 2, Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("350"))

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert result["baseline_windows_used"] == 2
        assert result["alert_level"] == "insufficient_data"

    def test_baseline_windows_capped(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        _seed_prior_windows(db_session, uid, today, window_days, 15, Decimal("100"))
        _add_tx(db_session, uid, today, Decimal("100"))

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert result["baseline_windows_used"] == MAX_BASELINE_WINDOWS

    def test_windows_do_not_overlap_current_window(self, db_session, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        window_days = 3
        current_start = today - timedelta(days=window_days - 1)

        _seed_prior_windows(db_session, uid, today, window_days, 4, Decimal("100"))
        _add_tx(db_session, uid, current_start - timedelta(days=1), Decimal("500"))
        _add_tx(db_session, uid, today, Decimal("100"))

        result = get_spending_velocity(db_session, uid, window_days=window_days, today=today)
        assert Decimal(str(result["current_window_spend"])) == Decimal("100.00")
        # baseline window0 = 100+500=600; others 100 → mean = (600+100+100+100)/4 = 225
        assert Decimal(str(result["baseline_window_spend"])) == Decimal("225.00")
        assert result["alert_level"] == "normal"

    def test_min_baseline_windows_constant(self):
        assert MIN_BASELINE_WINDOWS == 3
        assert MAX_BASELINE_WINDOWS >= MIN_BASELINE_WINDOWS
