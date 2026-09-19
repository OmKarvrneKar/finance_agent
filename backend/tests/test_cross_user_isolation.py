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
from app.database.db import Base, get_db, User, Transaction, BudgetGoal, SavingsGoal, AnomalyReview

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
    client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "full_name": name
    })
    res = client.post("/api/auth/login", data={
        "username": email,
        "password": password
    })
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
]

@patch('app.routers.transactions.categorize_transactions')
def test_transactions_are_isolated_between_users(mock_categorize, client, user_a_auth, user_b_auth):
    mock_categorize.return_value = MOCK_CATEGORIZED
    client.post(
        "/api/upload-statement",
        files={"file": ("tx.csv", io.BytesIO(b"Date,Description,Debit,Credit\n2026-07-01,Amazon,49.99,\n"), "text/csv")},
        headers=user_a_auth
    )
    
    res_a = client.get("/api/transactions", headers=user_a_auth)
    assert res_a.json()["total"] == 1
    
    res_b = client.get("/api/transactions", headers=user_b_auth)
    assert res_b.json()["total"] == 0

def test_budgets_are_isolated_between_users(client, user_a_auth, user_b_auth):
    client.post("/api/budgets", json={"category": "Food", "monthly_cap": 500}, headers=user_a_auth)
    
    res_a = client.get("/api/budgets", headers=user_a_auth)
    assert len(res_a.json()) == 1
    
    res_b = client.get("/api/budgets", headers=user_b_auth)
    assert len(res_b.json()) == 0

def test_savings_goals_are_isolated_between_users(client, user_a_auth, user_b_auth):
    client.post("/api/goals", json={"name": "Vacation", "target_amount": 5000}, headers=user_a_auth)
    
    res_a = client.get("/api/goals", headers=user_a_auth)
    assert len(res_a.json()) == 1
    
    res_b = client.get("/api/goals", headers=user_b_auth)
    assert len(res_b.json()) == 0

def test_user_cannot_access_other_users_transaction(client, user_a_auth, user_b_auth):
    with patch('app.routers.transactions.categorize_transactions') as mock:
        mock.return_value = MOCK_CATEGORIZED
        client.post(
            "/api/upload-statement",
            files={"file": ("tx.csv", io.BytesIO(b"Date,Description,Debit,Credit\n2026-07-01,Amazon,49.99,\n"), "text/csv")},
            headers=user_a_auth
        )
    
    res = client.get("/api/transactions", headers=user_a_auth)
    tx_id = res.json()["transactions"][0]["id"]
    
    update_res = client.put(f"/api/transactions/{tx_id}", json={"category": "Hacked"}, headers=user_b_auth)
    assert update_res.status_code == 404
    
    delete_res = client.delete(f"/api/transactions/{tx_id}", headers=user_b_auth)
    assert delete_res.status_code == 404

def test_user_cannot_access_other_users_budget(client, user_a_auth, user_b_auth):
    client.post("/api/budgets", json={"category": "Food", "monthly_cap": 500}, headers=user_a_auth)
    
    res = client.delete("/api/budgets/Food", headers=user_b_auth)
    assert res.status_code == 404

def test_anomalies_are_isolated_between_users(client, user_a_auth, user_b_auth):
    db = TestingSessionLocal()
    user_a = db.query(User).filter(User.email == "usera@test.com").first()
    t1 = Transaction(user_id=user_a.id, date=date(2026, 3, 1), description="Target", amount=45.0, transaction_type="debit", category="Shop", is_recurring=False)
    t2 = Transaction(user_id=user_a.id, date=date(2026, 3, 2), description="Target", amount=45.0, transaction_type="debit", category="Shop", is_recurring=False)
    db.add_all([t1, t2])
    db.commit()
    db.close()
    
    res_a = client.get("/api/anomalies", headers=user_a_auth)
    assert len(res_a.json()) > 0
    
    res_b = client.get("/api/anomalies", headers=user_b_auth)
    assert len(res_b.json()) == 0

def test_cross_user_cannot_dismiss_other_users_anomaly(client, user_a_auth, user_b_auth):
    db = TestingSessionLocal()
    user_a = db.query(User).filter(User.email == "usera@test.com").first()
    t1 = Transaction(user_id=user_a.id, date=date(2026, 3, 1), description="Target", amount=45.0, transaction_type="debit", category="Shop", is_recurring=False)
    t2 = Transaction(user_id=user_a.id, date=date(2026, 3, 2), description="Target", amount=45.0, transaction_type="debit", category="Shop", is_recurring=False)
    db.add_all([t1, t2])
    db.commit()
    db.close()
    
    res_a = client.get("/api/anomalies", headers=user_a_auth)
    sig = res_a.json()[0]["id"]
    
    res_b = client.post(f"/api/anomalies/{sig}/dismiss", headers=user_b_auth)
    assert res_b.status_code == 200
    
    res_a2 = client.get("/api/anomalies", headers=user_a_auth)
    assert len(res_a2.json()) > 0

def test_no_auth_returns_401(client):
    endpoints = [
        ("GET", "/api/transactions"),
        ("GET", "/api/budgets"),
        ("GET", "/api/goals"),
        ("GET", "/api/anomalies"),
        ("GET", "/api/auth/me"),
        ("POST", "/api/agent/ask"),
    ]
    for method, url in endpoints:
        if method == "GET":
            res = client.get(url)
        else:
            res = client.post(url, json={"question": "test"})
        assert res.status_code == 401, f"{method} {url} should return 401"
