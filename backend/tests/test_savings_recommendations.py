import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
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


def _calc_month_offset(today, i):
    y, m = today.year, today.month - i
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


# ── High-Spending Category Tests ──

def test_high_spending_category_detection(client, auth_headers):
    today = date.today()
    for i in range(6):
        d = _calc_month_offset(today, i)
        _add_tx(1, "Rent", "1200", "housing", tx_date=d)
        _add_tx(1, "Coffee", "50", "food", tx_date=d)

    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["months_of_data"] >= 2
    assert data["categories_analyzed"] >= 2
    recs = [r for r in data["recommendations"] if r["type"] == "high_spending_category"]
    housing_recs = [
        r for r in recs
        if r.get("category") == "housing"
        or r.get("supporting_data", {}).get("category") == "housing"
    ]
    assert len(housing_recs) >= 1
    rec = housing_recs[0]
    assert Decimal(rec["estimated_monthly_savings"]) > 0
    assert Decimal(rec["estimated_annual_savings"]) == Decimal(rec["estimated_monthly_savings"]) * 12
    assert rec["confidence"] in ("low", "medium", "high")
    assert "current_monthly_avg" in rec["supporting_data"]
    assert "months_analyzed" in rec["supporting_data"]


def test_high_spending_category_no_recommendations_for_low_variance(client, auth_headers):
    today = date.today()
    for i in range(4):
        d = _calc_month_offset(today, i)
        _add_tx(1, "Food A", "100", "food", tx_date=d)
        _add_tx(1, "Food B", "100", "food", tx_date=d)

    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    recs = [r for r in data["recommendations"] if r["type"] == "high_spending_category"]
    assert len(recs) == 0


# ── High-Frequency Merchant Tests ──

def test_high_frequency_merchant_detection(client, auth_headers):
    today = date.today()
    for i in range(6):
        d = _calc_month_offset(today, i)
        for day in [1, 5, 10, 15, 20]:
            tx_date = date(d.year, d.month, min(day, 28))
            _add_tx(1, "Starbucks Coffee", "7.50", "coffee", tx_date=tx_date)

    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    recs = [r for r in data["recommendations"] if r["type"] == "high_frequency_merchant"]
    assert len(recs) >= 1
    rec = recs[0]
    assert Decimal(rec["estimated_monthly_savings"]) > 0
    assert rec["supporting_data"]["merchant"] == "Starbucks Coffee"
    assert Decimal(rec["supporting_data"]["monthly_frequency"]) >= 2


def test_high_frequency_merchant_ignores_non_discretionary(client, auth_headers):
    today = date.today()
    for i in range(4):
        d = _calc_month_offset(today, i)
        for day in [1, 5, 10, 15, 20, 25]:
            tx_date = date(d.year, d.month, min(day, 28))
            _add_tx(1, "Electric Company", "150", "utilities", tx_date=tx_date)

    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    recs = [r for r in data["recommendations"] if r["type"] == "high_frequency_merchant"]
    utility_recs = [
        r for r in recs
        if r.get("merchant") == "Electric Company"
        or r.get("supporting_data", {}).get("merchant") == "Electric Company"
    ]
    assert len(utility_recs) == 0


# ── Spending Increase Tests ──

def test_spending_increase_detection(client, auth_headers):
    today = date.today()
    for i in range(3, 6):
        d = _calc_month_offset(today, i)
        _add_tx(1, "Dining", "200", "food", tx_date=d)

    for i in range(0, 3):
        d = _calc_month_offset(today, i)
        _add_tx(1, "Dining", "350", "food", tx_date=d)

    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    recs = [r for r in data["recommendations"] if r["type"] == "spending_increase"]
    assert len(recs) >= 1
    rec = recs[0]
    assert Decimal(rec["estimated_monthly_savings"]) > 0
    assert float(rec["supporting_data"]["percent_increase"]) >= 15.0
    assert rec["confidence"] == "high"


def test_no_spending_increase_for_stable_spending(client, auth_headers):
    today = date.today()
    for i in range(6):
        d = _calc_month_offset(today, i)
        _add_tx(1, "Groceries", "300", "food", tx_date=d)

    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    recs = [r for r in data["recommendations"] if r["type"] == "spending_increase"]
    assert len(recs) == 0


# ── Insufficient Data Tests ──

def test_insufficient_data_returns_empty(client, auth_headers):
    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["recommendations"] == []
    assert data["total_estimated_monthly_savings"] == 0
    assert data["total_estimated_annual_savings"] == 0
    assert data["months_of_data"] <= 1


def test_single_month_data_no_recommendations(client, auth_headers):
    _add_tx(1, "Lunch", "15", "food")
    _add_tx(1, "Dinner", "25", "food")

    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["months_of_data"] <= 1
    assert data["recommendations"] == []


# ── Decimal Precision Tests ──

def test_decimal_precision_in_recommendations(client, auth_headers):
    today = date.today()
    for i in range(4):
        d = _calc_month_offset(today, i)
        _add_tx(1, "Item", "33.33", "misc", tx_date=d)

    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    for rec in data["recommendations"]:
        monthly = Decimal(rec["estimated_monthly_savings"])
        assert monthly == monthly.quantize(Decimal("0.01"))
        annual = Decimal(rec["estimated_annual_savings"])
        assert annual == annual.quantize(Decimal("0.01"))
        assert annual == monthly * 12


# ── User Isolation Tests ──

def test_user_isolation(client, auth_headers, second_auth_headers):
    today = date.today()
    for i in range(4):
        d = _calc_month_offset(today, i)
        _add_tx(1, "Rent", "2000", "housing", tx_date=d)
        _add_tx(1, "Groceries", "200", "food", tx_date=d)

    for i in range(4):
        d = _calc_month_offset(today, i)
        _add_tx(2, "Snacks", "10", "food", tx_date=d)

    res1 = client.get("/api/savings-recommendations", headers=auth_headers)
    res2 = client.get("/api/savings-recommendations", headers=second_auth_headers)

    assert res1.status_code == 200
    assert res2.status_code == 200
    data1 = res1.json()
    data2 = res2.json()

    cats1 = {r.get("category", r.get("supporting_data", {}).get("category")) for r in data1["recommendations"]}
    cats2 = {r.get("category", r.get("supporting_data", {}).get("category")) for r in data2["recommendations"]}
    assert cats1 != cats2


def test_unauthenticated_returns_401(client):
    res = client.get("/api/savings-recommendations")
    assert res.status_code in (401, 403)


# ── Response Structure Tests ──

def test_response_structure(client, auth_headers):
    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "recommendations" in data
    assert "total_estimated_monthly_savings" in data
    assert "total_estimated_annual_savings" in data
    assert "categories_analyzed" in data
    assert "merchants_analyzed" in data
    assert "months_of_data" in data
    assert "generated_at" in data
    assert isinstance(data["recommendations"], list)
    assert isinstance(data["categories_analyzed"], int)
    assert isinstance(data["merchants_analyzed"], int)
    assert isinstance(data["months_of_data"], int)


def test_totals_match_sum_of_recommendations(client, auth_headers):
    today = date.today()
    for i in range(4):
        d = _calc_month_offset(today, i)
        _add_tx(1, "Expensive", "500", "entertainment", tx_date=d)
        _add_tx(1, "Cheap", "50", "food", tx_date=d)

    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    if data["recommendations"]:
        expected_monthly = sum(Decimal(r["estimated_monthly_savings"]) for r in data["recommendations"])
        expected_annual = sum(Decimal(r["estimated_annual_savings"]) for r in data["recommendations"])
        assert Decimal(str(data["total_estimated_monthly_savings"])) == expected_monthly
        assert Decimal(str(data["total_estimated_annual_savings"])) == expected_annual
