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
def auth(client):
    token = _register_and_login(client, "test@test.com", "Pass123456789", "Test User")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_b_auth(client):
    token = _register_and_login(client, "userb@test.com", "Pass123456789", "User B")
    return {"Authorization": f"Bearer {token}"}


MOCK_CATEGORIZED = [
    {'date': date(2026, 7, 1), 'description': 'Amazon', 'amount': 49.99, 'transaction_type': 'debit', 'raw_text': '', 'category': 'Shopping', 'subcategory': None, 'is_recurring': False},
    {'date': date(2026, 7, 2), 'description': 'Salary', 'amount': 2500.00, 'transaction_type': 'credit', 'raw_text': '', 'category': 'Salary/Income', 'subcategory': None, 'is_recurring': False},
]


def _seed_transactions(client, auth_headers):
    with patch('app.routers.transactions.categorize_transactions') as mock:
        mock.return_value = MOCK_CATEGORIZED
        res = client.post(
            "/api/upload-statement",
            files={"file": ("tx.csv", io.BytesIO(b"Date,Description,Debit,Credit\n2026-07-01,Amazon,49.99,\n"), "text/csv")},
            headers=auth_headers
        )
    assert res.status_code == 200
    return res.json()["new_transactions"]


def _get_first_transaction(client, auth_headers):
    res = client.get("/api/transactions?limit=1", headers=auth_headers)
    assert res.status_code == 200
    return res.json()["transactions"][0]


# --- transaction_type validation ---

def test_invalid_transaction_type_rejected(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"transaction_type": "invalid"}, headers=auth)
    assert res.status_code == 422


def test_invalid_transaction_type_credit_lowercase(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"transaction_type": "credit"}, headers=auth)
    assert res.status_code == 200
    assert res.json()["transaction_type"] == "credit"


def test_invalid_transaction_type_debit_lowercase(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"transaction_type": "debit"}, headers=auth)
    assert res.status_code == 200
    assert res.json()["transaction_type"] == "debit"


def test_transaction_type_case_sensitive(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"transaction_type": "Debit"}, headers=auth)
    assert res.status_code == 422


# --- amount validation ---

def test_invalid_amount_zero_rejected(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"amount": 0}, headers=auth)
    assert res.status_code == 422


def test_invalid_amount_negative_rejected(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"amount": -100}, headers=auth)
    assert res.status_code == 422


def test_valid_amount_accepted(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"amount": 99.99}, headers=auth)
    assert res.status_code == 200
    assert float(res.json()["amount"]) == 99.99


def test_amount_decimal_precision_preserved(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"amount": 123.45}, headers=auth)
    assert res.status_code == 200
    assert float(res.json()["amount"]) == 123.45


# --- date validation ---

def test_invalid_date_format_rejected(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"date": "not-a-date"}, headers=auth)
    assert res.status_code == 422


def test_invalid_date_format_mm_dd_yyyy_rejected(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"date": "07/01/2026"}, headers=auth)
    assert res.status_code == 422


def test_valid_date_accepted(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"date": "2026-08-15"}, headers=auth)
    assert res.status_code == 200
    assert res.json()["date"] == "2026-08-15"


# --- unknown fields ---

def test_unknown_fields_rejected(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"category": "ok", "fake_field": "value"}, headers=auth)
    assert res.status_code == 422


def test_multiple_unknown_fields_rejected(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"category": "ok", "foo": 1, "bar": 2}, headers=auth)
    assert res.status_code == 422


# --- empty update ---

def test_empty_update_rejected(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={}, headers=auth)
    assert res.status_code == 400
    assert "No valid fields" in res.json()["detail"]


# --- valid update regression ---

def test_valid_category_update(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"category": "Updated Category"}, headers=auth)
    assert res.status_code == 200
    assert res.json()["category"] == "Updated Category"


def test_valid_description_update(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"description": "Updated Desc"}, headers=auth)
    assert res.status_code == 200
    assert res.json()["description"] == "Updated Desc"


def test_valid_is_recurring_update(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"is_recurring": True}, headers=auth)
    assert res.status_code == 200
    assert res.json()["is_recurring"] is True


def test_valid_multi_field_update(client, auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={
        "category": "Multi",
        "description": "Multi Update",
        "amount": 77.77,
    }, headers=auth)
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "Multi"
    assert data["description"] == "Multi Update"
    assert float(data["amount"]) == 77.77


# --- user isolation regression ---

def test_user_cannot_update_other_users_transaction(client, auth, user_b_auth):
    _seed_transactions(client, auth)
    tx = _get_first_transaction(client, auth)
    res = client.put(f"/api/transactions/{tx['id']}", json={"category": "Hacked"}, headers=user_b_auth)
    assert res.status_code == 404


def test_unauthenticated_update_rejected(client):
    res = client.put("/api/transactions/1", json={"category": "X"})
    assert res.status_code == 401


# --- transaction not found ---

def test_update_nonexistent_transaction(client, auth):
    res = client.put("/api/transactions/999999", json={"category": "X"}, headers=auth)
    assert res.status_code == 404
