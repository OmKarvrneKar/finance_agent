import pytest
from datetime import date, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, Transaction, User

engine = create_engine(
    'sqlite:///:memory:',
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db(client):
    from app.dependencies import _rate_store
    _rate_store.clear()
    client.cookies.clear()
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def _register_and_login(client, email, password, name):
    client.post("/api/auth/register", json={"email": email, "password": password, "full_name": name})
    res = client.post("/api/auth/login", data={"username": email, "password": password})
    return res.json()["access_token"]


@pytest.fixture
def user_a_auth(client):
    token = _register_and_login(client, "usera@test.com", "Pass123456789", "User A")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_b_auth(client):
    token = _register_and_login(client, "userb@test.com", "Pass123456789", "User B")
    return {"Authorization": f"Bearer {token}"}


def _add_tx(user_id, description, amount, category, tx_date, tx_type="debit",
            is_recurring=True, is_user_confirmed=False):
    db = TestingSessionLocal()
    try:
        tx = Transaction(
            user_id=user_id,
            date=tx_date,
            description=description,
            amount=Decimal(str(amount)),
            transaction_type=tx_type,
            category=category,
            is_recurring=is_recurring,
            is_user_confirmed_recurring=is_user_confirmed,
        )
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return tx.id
    finally:
        db.close()


def _get_user_id_by_email(email):
    db = TestingSessionLocal()
    try:
        return db.query(User).filter_by(email=email).first().id
    finally:
        db.close()


def _get_bill(data, description):
    for bill in data["bills"]:
        if bill["description"] == description:
            return bill
    return None


# --- Authentication ---

def test_calendar_requires_authentication(client):
    res = client.get("/api/recurring/calendar")
    assert res.status_code == 401


def test_calendar_rejects_invalid_token(client):
    res = client.get(
        "/api/recurring/calendar",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert res.status_code == 401


# --- User isolation ---

def test_user_isolation(client, user_a_auth, user_b_auth):
    user_a_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_a_id, "Netflix", "15.99", "Subscriptions", date(2026, 8, 1))
    _add_tx(user_a_id, "Netflix", "15.99", "Subscriptions", date(2026, 9, 1))

    res_a = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-15", "end_date": "2026-10-15"},
        headers=user_a_auth,
    )
    res_b = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-15", "end_date": "2026-10-15"},
        headers=user_b_auth,
    )

    assert res_a.status_code == 200
    assert res_b.status_code == 200
    assert res_a.json()["count"] >= 1
    assert res_b.json()["count"] == 0
    assert res_b.json()["bills"] == []


# --- Empty result ---

def test_empty_result_when_no_recurring_transactions(client, user_a_auth):
    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-01", "end_date": "2026-09-30"},
        headers=user_a_auth,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["bills"] == []
    assert data["count"] == 0
    assert data["total_expected_amount"] == "0.00"


# --- Upcoming recurring bills + date-range filtering ---

def test_upcoming_monthly_bill_projected_in_range(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 8, 1))
    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 9, 1))

    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-15", "end_date": "2026-10-15"},
        headers=user_a_auth,
    )
    assert res.status_code == 200
    data = res.json()
    bill = _get_bill(data, "Netflix")
    assert bill is not None
    assert bill["expected_date"] == "2026-10-01"
    assert bill["date_status"] == "projected"
    assert bill["frequency"] == "Monthly"
    assert data["start_date"] == "2026-09-15"
    assert data["end_date"] == "2026-10-15"


def test_date_range_excludes_bill_outside_window(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 8, 1))
    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 9, 1))

    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-02", "end_date": "2026-09-30"},
        headers=user_a_auth,
    )
    assert res.status_code == 200
    data = res.json()
    assert _get_bill(data, "Netflix") is None


def test_weekly_bill_frequency_and_date(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_id, "Gym", "40.00", "Healthcare", date(2026, 9, 1))
    _add_tx(user_id, "Gym", "40.00", "Healthcare", date(2026, 9, 8))
    _add_tx(user_id, "Gym", "40.00", "Healthcare", date(2026, 9, 15))

    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-16", "end_date": "2026-09-30"},
        headers=user_a_auth,
    )
    assert res.status_code == 200
    bill = _get_bill(res.json(), "Gym")
    assert bill is not None
    assert bill["frequency"] == "Weekly"
    assert bill["expected_date"] == "2026-09-22"


def test_biweekly_bill_frequency_and_date(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_id, "Insurance", "120.00", "Bills & Utilities", date(2026, 8, 1))
    _add_tx(user_id, "Insurance", "120.00", "Bills & Utilities", date(2026, 8, 15))
    _add_tx(user_id, "Insurance", "120.00", "Bills & Utilities", date(2026, 8, 29))

    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-01", "end_date": "2026-09-15"},
        headers=user_a_auth,
    )
    assert res.status_code == 200
    bill = _get_bill(res.json(), "Insurance")
    assert bill is not None
    assert bill["frequency"] == "Bi-weekly"
    assert bill["expected_date"] == "2026-09-12"


# --- Amount accuracy + Decimal precision ---

def test_amount_accuracy_uses_historical_average(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 8, 1))
    _add_tx(user_id, "Netflix", "17.99", "Subscriptions", date(2026, 9, 1))

    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-15", "end_date": "2026-10-15"},
        headers=user_a_auth,
    )
    bill = _get_bill(res.json(), "Netflix")
    assert bill is not None
    assert bill["expected_amount"] == "16.99"


def test_decimal_precision_exact_string(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_id, "Spotify", "9.99", "Subscriptions", date(2026, 8, 10))
    _add_tx(user_id, "Spotify", "9.99", "Subscriptions", date(2026, 9, 10))

    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-15", "end_date": "2026-10-15"},
        headers=user_a_auth,
    )
    bill = _get_bill(res.json(), "Spotify")
    assert bill is not None
    assert bill["expected_amount"] == "9.99"
    assert isinstance(bill["expected_amount"], str)


# --- Category ---

def test_category_included_when_available(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 8, 1))
    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 9, 1))

    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-15", "end_date": "2026-10-15"},
        headers=user_a_auth,
    )
    bill = _get_bill(res.json(), "Netflix")
    assert bill is not None
    assert bill["category"] == "Subscriptions"


# --- No fabricated dates ---

def test_no_fabricated_dates_for_single_occurrence(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 9, 1))

    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-15", "end_date": "2026-10-15"},
        headers=user_a_auth,
    )
    assert res.status_code == 200
    bill = _get_bill(res.json(), "Netflix")
    assert bill is not None
    assert bill["expected_date"] is None
    assert bill["date_status"] == "uncertain"
    assert bill["frequency"] == "Monthly (Assumed)"
    assert bill["occurrences"] == 1


def test_no_fabricated_dates_when_all_dates_identical(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_id, "Weird", "5.00", "Other", date(2026, 9, 1))
    _add_tx(user_id, "Weird", "5.00", "Other", date(2026, 9, 1))

    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-15", "end_date": "2026-10-15"},
        headers=user_a_auth,
    )
    bill = _get_bill(res.json(), "Weird")
    assert bill is not None
    assert bill["expected_date"] is None
    assert bill["date_status"] == "uncertain"


# --- Invalid date range ---

def test_invalid_start_date_format(client, user_a_auth):
    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "not-a-date", "end_date": "2026-10-01"},
        headers=user_a_auth,
    )
    assert res.status_code == 400
    assert "start_date" in res.json()["detail"]


def test_invalid_end_date_format(client, user_a_auth):
    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-01", "end_date": "2026-13-01"},
        headers=user_a_auth,
    )
    assert res.status_code == 400
    assert "end_date" in res.json()["detail"]


def test_start_after_end_rejected(client, user_a_auth):
    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-10-01", "end_date": "2026-09-01"},
        headers=user_a_auth,
    )
    assert res.status_code == 400
    assert "start_date" in res.json()["detail"]


# --- Duplicate prevention ---

def test_duplicate_prevention_no_db_mutation_and_single_entry(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 8, 1))
    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 9, 1))

    params = {"start_date": "2026-09-15", "end_date": "2026-10-15"}
    res1 = client.get("/api/recurring/calendar", params=params, headers=user_a_auth)
    res2 = client.get("/api/recurring/calendar", params=params, headers=user_a_auth)

    assert res1.status_code == 200
    assert res2.status_code == 200

    netflix_entries_1 = [b for b in res1.json()["bills"] if b["description"] == "Netflix"]
    netflix_entries_2 = [b for b in res2.json()["bills"] if b["description"] == "Netflix"]
    assert len(netflix_entries_1) == 1
    assert len(netflix_entries_2) == 1

    db = TestingSessionLocal()
    try:
        tx_count = (
            db.query(Transaction)
            .filter(Transaction.user_id == user_id, Transaction.description == "Netflix")
            .count()
        )
    finally:
        db.close()
    assert tx_count == 2


# --- Default window when dates omitted ---

def test_default_window_when_dates_omitted(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    yesterday = date.today() - timedelta(days=1)
    _add_tx(user_id, "Internet", "60.00", "Bills & Utilities", yesterday - timedelta(days=14))
    _add_tx(user_id, "Internet", "60.00", "Bills & Utilities", yesterday - timedelta(days=7))
    _add_tx(user_id, "Internet", "60.00", "Bills & Utilities", yesterday)

    res = client.get("/api/recurring/calendar", headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    today = date.today()
    assert data["start_date"] == today.isoformat()
    assert data["end_date"] == (today + timedelta(days=30)).isoformat()
    bill = _get_bill(data, "Internet")
    assert bill is not None
    assert bill["expected_date"] == (yesterday + timedelta(days=7)).isoformat()


# --- Excludes credits and non-recurring ---

def test_excludes_credits_and_non_recurring(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_id, "Salary", "2500.00", "Salary/Income", date(2026, 8, 1), tx_type="credit")
    _add_tx(user_id, "Salary", "2500.00", "Salary/Income", date(2026, 9, 1), tx_type="credit")
    _add_tx(user_id, "Amazon", "49.99", "Shopping", date(2026, 8, 15), is_recurring=False)
    _add_tx(user_id, "Amazon", "49.99", "Shopping", date(2026, 9, 15), is_recurring=False)
    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 8, 1))
    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 9, 1))

    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-15", "end_date": "2026-10-15"},
        headers=user_a_auth,
    )
    data = res.json()
    descriptions = [b["description"] for b in data["bills"]]
    assert "Netflix" in descriptions
    assert "Salary" not in descriptions
    assert "Amazon" not in descriptions


# --- is_user_confirmed status ---

def test_is_user_confirmed_reflected(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    amazon_id = _add_tx(user_id, "Amazon Prime", "14.99", "Subscriptions", date(2026, 8, 5))
    _add_tx(user_id, "Amazon Prime", "14.99", "Subscriptions", date(2026, 9, 5))

    client.post(f"/api/transactions/{amazon_id}/recurring", headers=user_a_auth)

    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-15", "end_date": "2026-10-15"},
        headers=user_a_auth,
    )
    bill = _get_bill(res.json(), "Amazon Prime")
    assert bill is not None
    assert bill["is_user_confirmed"] is True
    assert bill["expected_date"] == "2026-10-05"


# --- Response schema ---

def test_response_schema_fields(client, user_a_auth):
    user_id = _get_user_id_by_email("usera@test.com")

    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 8, 1))
    _add_tx(user_id, "Netflix", "15.99", "Subscriptions", date(2026, 9, 1))

    res = client.get(
        "/api/recurring/calendar",
        params={"start_date": "2026-09-15", "end_date": "2026-10-15"},
        headers=user_a_auth,
    )
    data = res.json()
    assert set(data.keys()) == {
        "bills",
        "start_date",
        "end_date",
        "total_expected_amount",
        "count",
    }
    bill = data["bills"][0]
    assert set(bill.keys()) == {
        "description",
        "category",
        "expected_amount",
        "expected_date",
        "date_status",
        "frequency",
        "is_user_confirmed",
        "occurrences",
        "last_seen",
    }
    assert data["total_expected_amount"] == "15.99"
    assert bill["last_seen"] == "2026-09-01"
