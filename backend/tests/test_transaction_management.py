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
    from app.dependencies import _rate_store
    _rate_store.clear()
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

MOCK_CATEGORIZED = [
    {'date': date(2026, 7, 1), 'description': 'Amazon', 'amount': 49.99, 'transaction_type': 'debit', 'raw_text': '', 'category': 'Shopping', 'subcategory': None, 'is_recurring': False},
    {'date': date(2026, 7, 2), 'description': 'Salary', 'amount': 2500.00, 'transaction_type': 'credit', 'raw_text': '', 'category': 'Salary/Income', 'subcategory': None, 'is_recurring': True},
    {'date': date(2026, 7, 3), 'description': 'Starbucks Coffee', 'amount': 5.50, 'transaction_type': 'debit', 'raw_text': '', 'category': 'Food & Dining', 'subcategory': None, 'is_recurring': False},
    {'date': date(2026, 7, 5), 'description': 'Starbucks Reserve', 'amount': 12.00, 'transaction_type': 'debit', 'raw_text': '', 'category': 'Food & Dining', 'subcategory': None, 'is_recurring': False},
    {'date': date(2026, 7, 10), 'description': 'Uber Ride', 'amount': 15.00, 'transaction_type': 'debit', 'raw_text': '', 'category': 'Transport', 'subcategory': None, 'is_recurring': False},
]

def _seed_transactions(client, auth_headers):
    res = client.post(
        "/api/upload-statement",
        files={"file": ("tx.csv", io.BytesIO(b"Date,Description,Debit,Credit\n2026-07-01,Amazon,49.99,\n"), "text/csv")},
        headers=auth_headers
    )
    assert res.status_code == 200

def _seed_5_transactions(client, auth_headers):
    with patch('app.routers.transactions.categorize_transactions') as mock:
        mock.return_value = MOCK_CATEGORIZED
        res = client.post(
            "/api/upload-statement",
            files={"file": ("tx.csv", io.BytesIO(b"Date,Description,Debit,Credit\n2026-07-01,Amazon,49.99,\n"), "text/csv")},
            headers=auth_headers
        )
    assert res.status_code == 200

# --- CRUD Tests ---

def test_update_transaction_category(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    tx_id = client.get("/api/transactions", headers=user_a_auth).json()["transactions"][0]["id"]
    res = client.put(f"/api/transactions/{tx_id}", json={"category": "Entertainment"}, headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["category"] == "Entertainment"

def test_update_transaction_description(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    tx_id = client.get("/api/transactions", headers=user_a_auth).json()["transactions"][0]["id"]
    res = client.put(f"/api/transactions/{tx_id}", json={"description": "Updated Desc"}, headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["description"] == "Updated Desc"

def test_update_transaction_date(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    tx_id = client.get("/api/transactions", headers=user_a_auth).json()["transactions"][0]["id"]
    res = client.put(f"/api/transactions/{tx_id}", json={"date": "2026-08-15"}, headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["date"] == "2026-08-15"

def test_update_transaction_amount(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    tx_id = client.get("/api/transactions", headers=user_a_auth).json()["transactions"][0]["id"]
    res = client.put(f"/api/transactions/{tx_id}", json={"amount": 99.99}, headers=user_a_auth)
    assert res.status_code == 200
    assert float(res.json()["amount"]) == 99.99

def test_update_nonexistent_transaction(client, user_a_auth):
    res = client.put("/api/transactions/99999", json={"category": "X"}, headers=user_a_auth)
    assert res.status_code == 404

def test_update_rejects_invalid_fields(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    tx_id = client.get("/api/transactions", headers=user_a_auth).json()["transactions"][0]["id"]
    res = client.put(f"/api/transactions/{tx_id}", json={"user_id": 999, "category": "OK"}, headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["category"] == "OK"

def test_delete_transaction(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    total_before = client.get("/api/transactions", headers=user_a_auth).json()["total"]
    assert total_before == 5
    tx_id = client.get("/api/transactions?limit=1", headers=user_a_auth).json()["transactions"][0]["id"]
    res = client.delete(f"/api/transactions/{tx_id}", headers=user_a_auth)
    assert res.status_code == 200
    assert "deleted" in res.json()["message"].lower()
    total_after = client.get("/api/transactions", headers=user_a_auth).json()["total"]
    assert total_after == 4

def test_delete_nonexistent_transaction(client, user_a_auth):
    res = client.delete("/api/transactions/99999", headers=user_a_auth)
    assert res.status_code == 404

# --- Search / Filter Tests ---

def test_search_by_merchant(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    res = client.get("/api/transactions?search=Starbucks", headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    for tx in data["transactions"]:
        assert "starbucks" in tx["description"].lower()

def test_filter_by_category(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    res = client.get("/api/transactions?category=Transport", headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert res.json()["transactions"][0]["category"] == "Transport"

def test_filter_by_date_range(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    res = client.get("/api/transactions?start_date=2026-07-03&end_date=2026-07-05", headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["total"] == 2

def test_filter_by_amount_min(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    res = client.get("/api/transactions?amount_min=10", headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    for tx in data["transactions"]:
        assert float(tx["amount"]) >= 10.0

def test_filter_by_amount_max(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    res = client.get("/api/transactions?amount_max=10", headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    for tx in data["transactions"]:
        assert float(tx["amount"]) <= 10.0

def test_filter_by_amount_range(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    res = client.get("/api/transactions?amount_min=10&amount_max=20", headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    for tx in data["transactions"]:
        assert 10.0 <= float(tx["amount"]) <= 20.0

def test_combined_filters(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    res = client.get("/api/transactions?search=Starbucks&amount_min=10", headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert "Reserve" in res.json()["transactions"][0]["description"]

# --- Pagination Tests ---

def test_pagination_default(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    res = client.get("/api/transactions", headers=user_a_auth)
    data = res.json()
    assert data["page"] == 1
    assert data["limit"] == 20
    assert data["total"] == 5
    assert data["pages"] == 1

def test_pagination_page_size(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    res = client.get("/api/transactions?page=1&limit=2", headers=user_a_auth)
    data = res.json()
    assert len(data["transactions"]) == 2
    assert data["total"] == 5
    assert data["pages"] == 3

def test_pagination_page_2(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    res = client.get("/api/transactions?page=2&limit=2", headers=user_a_auth)
    data = res.json()
    assert len(data["transactions"]) == 2

def test_pagination_empty_page(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    res = client.get("/api/transactions?page=100&limit=2", headers=user_a_auth)
    assert res.json()["transactions"] == []

# --- Cross-User Authorization Tests ---

def test_user_cannot_update_other_users_transaction(client, user_a_auth, user_b_auth):
    _seed_5_transactions(client, user_a_auth)
    tx_id = client.get("/api/transactions", headers=user_a_auth).json()["transactions"][0]["id"]
    res = client.put(f"/api/transactions/{tx_id}", json={"category": "Hacked"}, headers=user_b_auth)
    assert res.status_code == 404

def test_user_cannot_delete_other_users_transaction(client, user_a_auth, user_b_auth):
    _seed_5_transactions(client, user_a_auth)
    tx_id = client.get("/api/transactions", headers=user_a_auth).json()["transactions"][0]["id"]
    res = client.delete(f"/api/transactions/{tx_id}", headers=user_b_auth)
    assert res.status_code == 404

def test_search_isolation_between_users(client, user_a_auth, user_b_auth):
    _seed_5_transactions(client, user_a_auth)
    res_a = client.get("/api/transactions?search=Starbucks", headers=user_a_auth)
    res_b = client.get("/api/transactions?search=Starbucks", headers=user_b_auth)
    assert res_a.json()["total"] == 2
    assert res_b.json()["total"] == 0

# --- Agent Search Tool Tests ---

def test_agent_search_transactions_by_merchant(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "usera@test.com").first()
    from app.services.agent_tools import search_transactions
    result = search_transactions(db, user.id, merchant="Starbucks")
    assert result["count"] == 2
    assert result["total_amount"] == Decimal("17.50")
    db.close()

def test_agent_search_transactions_by_category(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "usera@test.com").first()
    from app.services.agent_tools import search_transactions
    result = search_transactions(db, user.id, category="Transport")
    assert result["count"] == 1
    assert result["total_amount"] == Decimal("15.00")
    db.close()

def test_agent_search_transactions_with_amount_filter(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "usera@test.com").first()
    from app.services.agent_tools import search_transactions
    result = search_transactions(db, user.id, merchant="Starbucks", amount_min=10)
    assert result["count"] == 1
    assert result["total_amount"] == Decimal("12.00")
    db.close()

def test_agent_search_transactions_isolation(client, user_a_auth, user_b_auth):
    _seed_5_transactions(client, user_a_auth)
    db = TestingSessionLocal()
    user_b = db.query(User).filter(User.email == "userb@test.com").first()
    from app.services.agent_tools import search_transactions
    result = search_transactions(db, user_b.id, merchant="Starbucks")
    assert result["count"] == 0
    assert result["total_amount"] == Decimal("0")
    db.close()

def test_agent_search_transactions_no_results(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "usera@test.com").first()
    from app.services.agent_tools import search_transactions
    result = search_transactions(db, user.id, merchant="NonexistentStore")
    assert result["count"] == 0
    db.close()

# --- Categories Endpoint Tests ---

def test_categories_returns_user_scoped(client, user_a_auth, user_b_auth):
    _seed_5_transactions(client, user_a_auth)
    res_a = client.get("/api/categories", headers=user_a_auth)
    res_b = client.get("/api/categories", headers=user_b_auth)
    assert len(res_a.json()["categories"]) > 0
    assert res_b.json()["categories"] == []

# --- Regression Tests ---

def test_get_single_transaction(client, user_a_auth):
    _seed_5_transactions(client, user_a_auth)
    txs = client.get("/api/transactions", headers=user_a_auth).json()["transactions"]
    assert len(txs) == 5
    for tx in txs:
        assert "id" in tx
        assert "date" in tx
        assert "amount" in tx
        assert "category" in tx

def test_upload_still_works(client, user_a_auth):
    with patch('app.routers.transactions.categorize_transactions') as mock:
        mock.return_value = MOCK_CATEGORIZED[:1]
        res = client.post(
            "/api/upload-statement",
            files={"file": ("tx.csv", io.BytesIO(b"Date,Description,Debit,Credit\n2026-07-01,Test,10,\n"), "text/csv")},
            headers=user_a_auth
        )
    assert res.status_code == 200
    assert res.json()["total_transactions"] == 1
