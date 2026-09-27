import pytest
import io
from unittest.mock import patch
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database.db import Base, get_db, User, Transaction

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
def setup_db():
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

MOCK_RECURRING_CATEGORIZED = [
    {'date': date(2026, 7, 1), 'description': 'Netflix', 'amount': 15.99, 'transaction_type': 'debit', 'raw_text': '', 'category': 'Subscriptions', 'subcategory': None, 'is_recurring': True},
    {'date': date(2026, 7, 1), 'description': 'Spotify', 'amount': 9.99, 'transaction_type': 'debit', 'raw_text': '', 'category': 'Subscriptions', 'subcategory': None, 'is_recurring': True},
    {'date': date(2026, 7, 15), 'description': 'Amazon', 'amount': 49.99, 'transaction_type': 'debit', 'raw_text': '', 'category': 'Shopping', 'subcategory': None, 'is_recurring': False},
    {'date': date(2026, 7, 15), 'description': 'Salary', 'amount': 2500.00, 'transaction_type': 'credit', 'raw_text': '', 'category': 'Salary/Income', 'subcategory': None, 'is_recurring': True},
]

MOCK_NON_RECURRING_CATEGORIZED = [
    {'date': date(2026, 7, 1), 'description': 'Grocery Store', 'amount': 45.00, 'transaction_type': 'debit', 'raw_text': '', 'category': 'Groceries', 'subcategory': None, 'is_recurring': False},
]

def _seed_transactions(client, auth_headers, categorized=None):
    if categorized is None:
        categorized = MOCK_RECURRING_CATEGORIZED
    with patch('app.routers.transactions.categorize_transactions') as mock:
        mock.return_value = categorized
        res = client.post(
            "/api/upload-statement",
            files={"file": ("tx.csv", io.BytesIO(b"Date,Description,Debit,Credit\n2026-07-01,Netflix,15.99,\n"), "text/csv")},
            headers=auth_headers
        )
    assert res.status_code == 200

def _find_tx_by_description(transactions, description):
    for tx in transactions:
        if tx["description"] == description:
            return tx
    return None


# --- GET /subscriptions tests ---

def test_get_subscriptions_empty(client, user_a_auth):
    res = client.get("/api/subscriptions", headers=user_a_auth)
    assert res.status_code == 200
    assert res.json() == []

def test_get_subscriptions_returns_recurring_debits(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    res = client.get("/api/subscriptions", headers=user_a_auth)
    assert res.status_code == 200
    subs = res.json()
    assert len(subs) >= 2
    descriptions = [s["description"] for s in subs]
    assert "Netflix" in descriptions
    assert "Spotify" in descriptions

def test_get_subscriptions_excludes_credits(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    res = client.get("/api/subscriptions", headers=user_a_auth)
    subs = res.json()
    descriptions = [s["description"] for s in subs]
    assert "Salary" not in descriptions

def test_get_subscriptions_excludes_non_recurring(client, user_a_auth):
    _seed_transactions(client, user_a_auth, MOCK_NON_RECURRING_CATEGORIZED)
    res = client.get("/api/subscriptions", headers=user_a_auth)
    subs = res.json()
    assert len(subs) == 0

def test_get_subscriptions_user_isolation(client, user_a_auth, user_b_auth):
    _seed_transactions(client, user_a_auth)
    res_a = client.get("/api/subscriptions", headers=user_a_auth)
    res_b = client.get("/api/subscriptions", headers=user_b_auth)
    assert len(res_a.json()) >= 2
    assert len(res_b.json()) == 0

def test_get_subscriptions_response_schema(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    res = client.get("/api/subscriptions", headers=user_a_auth)
    sub = res.json()[0]
    assert "description" in sub
    assert "category" in sub
    assert "occurrences" in sub
    assert "average_amount" in sub
    assert "frequency" in sub
    assert "estimated_monthly_cost" in sub
    assert "estimated_annual_cost" in sub
    assert "last_seen" in sub
    assert "is_user_confirmed" in sub

def test_get_subscriptions_unauthenticated(client):
    res = client.get("/api/subscriptions")
    assert res.status_code == 401


# --- POST /transactions/{id}/recurring tests ---

def test_mark_recurring(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    tx = _find_tx_by_description(client.get("/api/transactions", headers=user_a_auth).json()["transactions"], "Amazon")
    assert tx is not None, "Amazon transaction not found"
    assert tx["is_recurring"] == False

    res = client.post(f"/api/transactions/{tx['id']}/recurring", headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["is_recurring"] == True
    assert res.json()["is_user_confirmed_recurring"] == True

def test_mark_recurring_already_recurring(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    tx = _find_tx_by_description(client.get("/api/transactions", headers=user_a_auth).json()["transactions"], "Netflix")
    assert tx is not None
    assert tx["is_recurring"] == True

    res = client.post(f"/api/transactions/{tx['id']}/recurring", headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["is_recurring"] == True

def test_mark_recurring_nonexistent(client, user_a_auth):
    res = client.post("/api/transactions/99999/recurring", headers=user_a_auth)
    assert res.status_code == 404

def test_mark_recurring_user_isolation(client, user_a_auth, user_b_auth):
    _seed_transactions(client, user_a_auth)
    tx = _find_tx_by_description(client.get("/api/transactions", headers=user_a_auth).json()["transactions"], "Netflix")
    assert tx is not None
    res = client.post(f"/api/transactions/{tx['id']}/recurring", headers=user_b_auth)
    assert res.status_code == 404

def test_mark_recurring_unauthenticated(client):
    res = client.post("/api/transactions/1/recurring")
    assert res.status_code == 401


# --- DELETE /transactions/{id}/recurring tests ---

def test_unmark_recurring(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    tx = _find_tx_by_description(client.get("/api/transactions", headers=user_a_auth).json()["transactions"], "Netflix")
    assert tx is not None
    assert tx["is_recurring"] == True

    res = client.delete(f"/api/transactions/{tx['id']}/recurring", headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["is_recurring"] == False
    assert res.json()["is_user_confirmed_recurring"] == False

def test_unmark_recurring_not_recurring(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    tx = _find_tx_by_description(client.get("/api/transactions", headers=user_a_auth).json()["transactions"], "Amazon")
    assert tx is not None
    assert tx["is_recurring"] == False

    res = client.delete(f"/api/transactions/{tx['id']}/recurring", headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["is_recurring"] == False

def test_unmark_recurring_nonexistent(client, user_a_auth):
    res = client.delete("/api/transactions/99999/recurring", headers=user_a_auth)
    assert res.status_code == 404

def test_unmark_recurring_user_isolation(client, user_a_auth, user_b_auth):
    _seed_transactions(client, user_a_auth)
    tx = _find_tx_by_description(client.get("/api/transactions", headers=user_a_auth).json()["transactions"], "Netflix")
    assert tx is not None
    client.post(f"/api/transactions/{tx['id']}/recurring", headers=user_a_auth)
    res = client.delete(f"/api/transactions/{tx['id']}/recurring", headers=user_b_auth)
    assert res.status_code == 404

def test_unmark_recurring_unauthenticated(client):
    res = client.delete("/api/transactions/1/recurring")
    assert res.status_code == 401


# --- Manual override behavior tests ---

def test_manual_mark_preserves_user_confirmed(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    tx = _find_tx_by_description(client.get("/api/transactions", headers=user_a_auth).json()["transactions"], "Amazon")
    assert tx is not None

    client.post(f"/api/transactions/{tx['id']}/recurring", headers=user_a_auth)
    res = client.get("/api/transactions", headers=user_a_auth)
    updated_tx = _find_tx_by_description(res.json()["transactions"], "Amazon")
    assert updated_tx is not None
    assert updated_tx["is_recurring"] == True
    assert updated_tx["is_user_confirmed_recurring"] == True

def test_manual_unmark_clears_user_confirmed(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    tx = _find_tx_by_description(client.get("/api/transactions", headers=user_a_auth).json()["transactions"], "Netflix")
    assert tx is not None

    client.delete(f"/api/transactions/{tx['id']}/recurring", headers=user_a_auth)
    res = client.get("/api/transactions", headers=user_a_auth)
    updated_tx = _find_tx_by_description(res.json()["transactions"], "Netflix")
    assert updated_tx is not None
    assert updated_tx["is_recurring"] == False
    assert updated_tx["is_user_confirmed_recurring"] == False

def test_ai_detected_not_user_confirmed(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    res = client.get("/api/transactions", headers=user_a_auth)
    tx = _find_tx_by_description(res.json()["transactions"], "Netflix")
    assert tx is not None
    assert tx["is_recurring"] == True
    assert tx["is_user_confirmed_recurring"] == False

def test_subscriptions_shows_user_confirmed_status(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    tx = _find_tx_by_description(client.get("/api/transactions", headers=user_a_auth).json()["transactions"], "Amazon")
    assert tx is not None
    assert tx["is_recurring"] == False
    client.post(f"/api/transactions/{tx['id']}/recurring", headers=user_a_auth)

    res = client.get("/api/subscriptions", headers=user_a_auth)
    for sub in res.json():
        if sub["description"] == "Amazon":
            assert sub["is_user_confirmed"] == True
            return
    pytest.fail("Amazon subscription not found")


# --- Regression tests for subscription detection ---

def test_subscription_frequency_calculation(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    res = client.get("/api/subscriptions", headers=user_a_auth)
    for sub in res.json():
        if sub["description"] == "Netflix":
            assert sub["occurrences"] == 1
            assert sub["frequency"] in ["Monthly", "Yearly"]
            assert float(sub["estimated_monthly_cost"]) > 0
            assert float(sub["estimated_annual_cost"]) > 0
            return
    pytest.fail("Netflix subscription not found")

def test_subscription_amount_calculation(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    res = client.get("/api/subscriptions", headers=user_a_auth)
    for sub in res.json():
        if sub["description"] == "Netflix":
            assert float(sub["average_amount"]) == 15.99
            return
    pytest.fail("Netflix subscription not found")

def test_subscription_sorted_by_monthly_cost(client, user_a_auth):
    _seed_transactions(client, user_a_auth)
    res = client.get("/api/subscriptions", headers=user_a_auth)
    subs = res.json()
    if len(subs) > 1:
        for i in range(len(subs) - 1):
            assert float(subs[i]["estimated_monthly_cost"]) >= float(subs[i+1]["estimated_monthly_cost"])
