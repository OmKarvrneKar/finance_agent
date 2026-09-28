import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.database.db import Base, get_db, Transaction

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
def auth_token(client):
    return _register_and_login(client, "testuser@example.com", "TestPass123", "Test User")


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def second_auth_token(client):
    return _register_and_login(client, "other@example.com", "OtherPass123", "Other User")


@pytest.fixture
def second_auth_headers(second_auth_token):
    return {"Authorization": f"Bearer {second_auth_token}"}


def _add_tx(user_id, description, amount, category, tx_date=None, tx_type="debit"):
    db = TestingSessionLocal()
    try:
        if tx_date is None:
            tx_date = date.today()
        db.add(Transaction(
            user_id=user_id,
            date=tx_date,
            description=description,
            amount=Decimal(str(amount)),
            transaction_type=tx_type,
            category=category,
        ))
        db.commit()
    finally:
        db.close()


# ── Merchant Aggregation Tests ──

def test_merchant_aggregation(client, auth_headers):
    today = date.today()
    _add_tx(1, "Starbucks", "7.50", "coffee", tx_date=today)
    _add_tx(1, "Starbucks", "12.00", "coffee", tx_date=today)
    _add_tx(1, "Amazon", "50.00", "shopping", tx_date=today)

    res = client.get("/api/analytics/merchants", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_merchants"] == 2
    merchants = {m["merchant"]: m for m in data["merchants"]}
    assert merchants["Starbucks"]["transaction_count"] == 2
    assert Decimal(merchants["Starbucks"]["total_spent"]) == Decimal("19.50")
    assert merchants["Amazon"]["transaction_count"] == 1
    assert Decimal(merchants["Amazon"]["total_spent"]) == Decimal("50.00")


def test_total_count_average_largest(client, auth_headers):
    today = date.today()
    _add_tx(1, "Cafe", "10.00", "food", tx_date=today)
    _add_tx(1, "Cafe", "25.00", "food", tx_date=today)
    _add_tx(1, "Cafe", "5.00", "food", tx_date=today)

    res = client.get("/api/analytics/merchants", headers=auth_headers)
    data = res.json()
    m = data["merchants"][0]
    assert m["transaction_count"] == 3
    assert float(m["total_spent"]) == 40.00
    assert float(m["average_amount"]) == 13.33
    assert float(m["largest_transaction"]) == 25.00


# ── Spending Percentage Tests ──

def test_spending_percent_of_total(client, auth_headers):
    today = date.today()
    _add_tx(1, "Starbucks", "30.00", "coffee", tx_date=today)
    _add_tx(1, "Amazon", "70.00", "shopping", tx_date=today)

    res = client.get("/api/analytics/merchants", headers=auth_headers)
    data = res.json()
    merchants = {m["merchant"]: m for m in data["merchants"]}
    assert Decimal(merchants["Starbucks"]["spending_percent"]) == Decimal("30.00")
    assert Decimal(merchants["Amazon"]["spending_percent"]) == Decimal("70.00")
    assert Decimal(data["total_expenses"]) == Decimal("100.00")


# ── Date Filtering Tests ──

def test_date_filtering(client, auth_headers):
    _add_tx(1, "Cafe", "10.00", "food", tx_date=date(2026, 6, 15))
    _add_tx(1, "Cafe", "20.00", "food", tx_date=date(2026, 7, 15))
    _add_tx(1, "Cafe", "30.00", "food", tx_date=date(2026, 8, 15))

    res = client.get("/api/analytics/merchants?start_date=2026-07-01&end_date=2026-07-31", headers=auth_headers)
    data = res.json()
    assert len(data["merchants"]) == 1
    assert Decimal(data["merchants"][0]["total_spent"]) == Decimal("20.00")


def test_date_filtering_start_only(client, auth_headers):
    _add_tx(1, "Cafe", "10.00", "food", tx_date=date(2026, 6, 15))
    _add_tx(1, "Cafe", "20.00", "food", tx_date=date(2026, 8, 15))

    res = client.get("/api/analytics/merchants?start_date=2026-07-01", headers=auth_headers)
    data = res.json()
    assert len(data["merchants"]) == 1
    assert Decimal(data["merchants"][0]["total_spent"]) == Decimal("20.00")


# ── Search Filtering Tests ──

def test_search_filtering(client, auth_headers):
    today = date.today()
    _add_tx(1, "Starbucks Coffee", "7.50", "coffee", tx_date=today)
    _add_tx(1, "Amazon", "50.00", "shopping", tx_date=today)

    res = client.get("/api/analytics/merchants?search=starbucks", headers=auth_headers)
    data = res.json()
    assert data["total_merchants"] == 1
    assert data["merchants"][0]["merchant"] == "Starbucks Coffee"


def test_search_no_results(client, auth_headers):
    today = date.today()
    _add_tx(1, "Cafe", "10.00", "food", tx_date=today)

    res = client.get("/api/analytics/merchants?search=nonexistent", headers=auth_headers)
    data = res.json()
    assert data["total_merchants"] == 0
    assert data["merchants"] == []


# ── Ordering Tests ──

def test_ordering_by_spending(client, auth_headers):
    today = date.today()
    _add_tx(1, "Cheap", "5.00", "food", tx_date=today)
    _add_tx(1, "Expensive", "100.00", "shopping", tx_date=today)
    _add_tx(1, "Medium", "50.00", "food", tx_date=today)

    res = client.get("/api/analytics/merchants", headers=auth_headers)
    data = res.json()
    names = [m["merchant"] for m in data["merchants"]]
    assert names == ["Expensive", "Medium", "Cheap"]


# ── Limit Tests ──

def test_limit(client, auth_headers):
    today = date.today()
    for i in range(5):
        _add_tx(1, f"Merchant{i}", str(i * 10 + 10), "food", tx_date=today)

    res = client.get("/api/analytics/merchants?limit=2", headers=auth_headers)
    data = res.json()
    assert len(data["merchants"]) == 2
    assert data["total_merchants"] == 2


def test_limit_validation(client, auth_headers):
    res = client.get("/api/analytics/merchants?limit=0", headers=auth_headers)
    assert res.status_code == 422

    res = client.get("/api/analytics/merchants?limit=200", headers=auth_headers)
    assert res.status_code == 422


# ── Empty Results Tests ──

def test_empty_database(client, auth_headers):
    res = client.get("/api/analytics/merchants", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["merchants"] == []
    assert data["total_merchants"] == 0
    assert Decimal(data["total_expenses"]) == Decimal("0")


# ── Decimal Precision Tests ──

def test_decimal_precision(client, auth_headers):
    today = date.today()
    _add_tx(1, "Cafe", "33.33", "food", tx_date=today)
    _add_tx(1, "Cafe", "11.11", "food", tx_date=today)

    res = client.get("/api/analytics/merchants", headers=auth_headers)
    data = res.json()
    m = data["merchants"][0]
    assert str(m["total_spent"]) == "44.44"
    assert str(m["average_amount"]) == "22.22"


# ── Income/Credit Exclusion Tests ──

def test_income_excluded_from_spending(client, auth_headers):
    today = date.today()
    _add_tx(1, "Employer", "5000.00", "income", tx_date=today, tx_type="credit")
    _add_tx(1, "Cafe", "10.00", "food", tx_date=today, tx_type="debit")

    res = client.get("/api/analytics/merchants", headers=auth_headers)
    data = res.json()
    assert data["total_merchants"] == 1
    assert data["merchants"][0]["merchant"] == "Cafe"
    assert Decimal(data["total_expenses"]) == Decimal("10.00")


def test_only_credits_returns_empty(client, auth_headers):
    today = date.today()
    _add_tx(1, "Employer", "5000.00", "income", tx_date=today, tx_type="credit")

    res = client.get("/api/analytics/merchants", headers=auth_headers)
    data = res.json()
    assert data["merchants"] == []
    assert data["total_merchants"] == 0


# ── User Isolation Tests ──

def test_user_isolation(client, auth_headers, second_auth_headers):
    today = date.today()
    _add_tx(1, "MyCafe", "10.00", "food", tx_date=today)
    _add_tx(2, "TheirCafe", "20.00", "food", tx_date=today)

    res1 = client.get("/api/analytics/merchants", headers=auth_headers)
    res2 = client.get("/api/analytics/merchants", headers=second_auth_headers)

    assert res1.status_code == 200
    assert res2.status_code == 200
    d1 = res1.json()
    d2 = res2.json()
    assert d1["total_merchants"] == 1
    assert d2["total_merchants"] == 1
    assert d1["merchants"][0]["merchant"] == "MyCafe"
    assert d2["merchants"][0]["merchant"] == "TheirCafe"


def test_unauthenticated_returns_401(client):
    res = client.get("/api/analytics/merchants")
    assert res.status_code in (401, 403)


# ── Response Structure Tests ──

def test_response_structure(client, auth_headers):
    today = date.today()
    _add_tx(1, "Cafe", "10.00", "food", tx_date=today)

    res = client.get("/api/analytics/merchants", headers=auth_headers)
    data = res.json()
    assert "merchants" in data
    assert "total_merchants" in data
    assert "total_expenses" in data
    assert "date_range" in data
    assert isinstance(data["merchants"], list)
    assert isinstance(data["total_merchants"], int)

    m = data["merchants"][0]
    assert "merchant" in m
    assert "total_spent" in m
    assert "transaction_count" in m
    assert "average_amount" in m
    assert "largest_transaction" in m
    assert "spending_percent" in m
    assert "first_seen" in m
    assert "last_seen" in m
    assert "category" in m


def test_date_range_in_response(client, auth_headers):
    res = client.get("/api/analytics/merchants?start_date=2026-01-01&end_date=2026-12-31", headers=auth_headers)
    data = res.json()
    assert data["date_range"]["start_date"] == "2026-01-01"
    assert data["date_range"]["end_date"] == "2026-12-31"


# ── Duplicate Merchant Descriptions Tests ──

def test_duplicate_merchant_descriptions(client, auth_headers):
    today = date.today()
    _add_tx(1, "Starbucks", "7.50", "coffee", tx_date=today)
    _add_tx(1, "Starbucks", "12.00", "coffee", tx_date=today)
    _add_tx(1, "Starbucks", "5.00", "food", tx_date=today)

    res = client.get("/api/analytics/merchants", headers=auth_headers)
    data = res.json()
    assert data["total_merchants"] == 1
    m = data["merchants"][0]
    assert m["transaction_count"] == 3
    assert Decimal(m["total_spent"]) == Decimal("24.50")


# ── Unknown Merchant Search ──

def test_unknown_merchant_search(client, auth_headers):
    today = date.today()
    _add_tx(1, "Cafe", "10.00", "food", tx_date=today)

    res = client.get("/api/analytics/merchants?search=Starbucks", headers=auth_headers)
    data = res.json()
    assert data["total_merchants"] == 0
    assert data["merchants"] == []
