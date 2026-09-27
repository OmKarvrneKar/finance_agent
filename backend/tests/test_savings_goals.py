import pytest
import io
from datetime import date, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database.db import Base, get_db, User, SavingsGoal

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


# --- CRUD Tests ---

def test_create_goal(client, user_a_auth):
    res = client.post("/api/goals", json={
        "name": "Emergency Fund",
        "target_amount": "100000",
        "target_date": "2027-01-01",
        "description": "6 months of expenses"
    }, headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Emergency Fund"
    assert data["target_amount"] == "100000.00"
    assert data["current_amount"] == "0.00"
    assert data["status"] == "active"
    assert data["description"] == "6 months of expenses"
    assert data["progress_percent"] == 0

def test_create_goal_minimal(client, user_a_auth):
    res = client.post("/api/goals", json={
        "name": "New Laptop",
        "target_amount": "80000",
    }, headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "New Laptop"
    assert data["target_date"] is None
    assert data["description"] is None

def test_list_goals(client, user_a_auth):
    client.post("/api/goals", json={"name": "Goal A", "target_amount": "5000"}, headers=user_a_auth)
    client.post("/api/goals", json={"name": "Goal B", "target_amount": "10000"}, headers=user_a_auth)
    res = client.get("/api/goals", headers=user_a_auth)
    assert res.status_code == 200
    assert len(res.json()) == 2

def test_list_goals_filter_status(client, user_a_auth):
    client.post("/api/goals", json={"name": "Active Goal", "target_amount": "5000"}, headers=user_a_auth)
    client.post("/api/goals", json={"name": "Another Active", "target_amount": "3000"}, headers=user_a_auth)
    res = client.get("/api/goals?status=active", headers=user_a_auth)
    assert res.status_code == 200
    assert len(res.json()) == 2
    res = client.get("/api/goals?status=completed", headers=user_a_auth)
    assert len(res.json()) == 0

def test_get_goal_by_id(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Vacation", "target_amount": "50000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.get(f"/api/goals/{goal_id}", headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["name"] == "Vacation"

def test_get_goal_not_found(client, user_a_auth):
    res = client.get("/api/goals/99999", headers=user_a_auth)
    assert res.status_code == 404

def test_update_goal(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Old Name", "target_amount": "5000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.put(f"/api/goals/{goal_id}", json={"name": "New Name", "target_amount": "7500"}, headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "New Name"
    assert data["target_amount"] == "7500.00"

def test_update_goal_status(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Test", "target_amount": "1000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.put(f"/api/goals/{goal_id}", json={"status": "abandoned"}, headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["status"] == "abandoned"

def test_update_goal_not_found(client, user_a_auth):
    res = client.put("/api/goals/99999", json={"name": "X"}, headers=user_a_auth)
    assert res.status_code == 404

def test_delete_goal(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "To Delete", "target_amount": "1000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.delete(f"/api/goals/{goal_id}", headers=user_a_auth)
    assert res.status_code == 200
    res = client.get(f"/api/goals/{goal_id}", headers=user_a_auth)
    assert res.status_code == 404

def test_delete_goal_not_found(client, user_a_auth):
    res = client.delete("/api/goals/99999", headers=user_a_auth)
    assert res.status_code == 404


# --- Validation Tests ---

def test_create_goal_negative_target(client, user_a_auth):
    res = client.post("/api/goals", json={"name": "Bad", "target_amount": "-100"}, headers=user_a_auth)
    assert res.status_code == 400

def test_create_goal_zero_target(client, user_a_auth):
    res = client.post("/api/goals", json={"name": "Bad", "target_amount": "0"}, headers=user_a_auth)
    assert res.status_code == 400

def test_create_goal_past_date(client, user_a_auth):
    res = client.post("/api/goals", json={
        "name": "Past", "target_amount": "1000",
        "target_date": "2020-01-01"
    }, headers=user_a_auth)
    assert res.status_code == 400

def test_update_goal_invalid_status(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Test", "target_amount": "1000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.put(f"/api/goals/{goal_id}", json={"status": "invalid_status"}, headers=user_a_auth)
    assert res.status_code == 400


# --- Contribution Tests ---

def test_contribute_to_goal(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Fund", "target_amount": "10000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "2500"}, headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    assert data["current_amount"] == "2500.00"
    assert data["progress_percent"] == 25.0

def test_contribute_multiple_times(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Fund", "target_amount": "10000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "3000"}, headers=user_a_auth)
    res = client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "2000"}, headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    assert data["current_amount"] == "5000.00"
    assert data["progress_percent"] == 50.0

def test_contribute_completes_goal(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Small", "target_amount": "1000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "1000"}, headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert data["progress_percent"] == 100.0

def test_contribute_exceeds_target(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Small", "target_amount": "500"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "750"}, headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert data["progress_percent"] == 100.0

def test_contribute_negative_amount(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Fund", "target_amount": "1000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "-100"}, headers=user_a_auth)
    assert res.status_code == 400

def test_contribute_zero_amount(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Fund", "target_amount": "1000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "0"}, headers=user_a_auth)
    assert res.status_code == 400

def test_contribute_nonexistent_goal(client, user_a_auth):
    res = client.post("/api/goals/99999/contribute", json={"amount": "100"}, headers=user_a_auth)
    assert res.status_code == 404


# --- User Isolation Tests ---

def test_user_isolation_list(client, user_a_auth, user_b_auth):
    client.post("/api/goals", json={"name": "A's Goal", "target_amount": "5000"}, headers=user_a_auth)
    client.post("/api/goals", json={"name": "B's Goal", "target_amount": "8000"}, headers=user_b_auth)
    res_a = client.get("/api/goals", headers=user_a_auth)
    res_b = client.get("/api/goals", headers=user_b_auth)
    assert len(res_a.json()) == 1
    assert res_a.json()[0]["name"] == "A's Goal"
    assert len(res_b.json()) == 1
    assert res_b.json()[0]["name"] == "B's Goal"

def test_user_isolation_get(client, user_a_auth, user_b_auth):
    create_res = client.post("/api/goals", json={"name": "Private", "target_amount": "1000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.get(f"/api/goals/{goal_id}", headers=user_b_auth)
    assert res.status_code == 404

def test_user_isolation_update(client, user_a_auth, user_b_auth):
    create_res = client.post("/api/goals", json={"name": "Private", "target_amount": "1000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.put(f"/api/goals/{goal_id}", json={"name": "Hacked"}, headers=user_b_auth)
    assert res.status_code == 404

def test_user_isolation_delete(client, user_a_auth, user_b_auth):
    create_res = client.post("/api/goals", json={"name": "Private", "target_amount": "1000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.delete(f"/api/goals/{goal_id}", headers=user_b_auth)
    assert res.status_code == 404

def test_user_isolation_contribute(client, user_a_auth, user_b_auth):
    create_res = client.post("/api/goals", json={"name": "Private", "target_amount": "1000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "100"}, headers=user_b_auth)
    assert res.status_code == 404


# --- Decimal Calculation Tests ---

def test_decimal_target_amount(client, user_a_auth):
    res = client.post("/api/goals", json={"name": "Decimal", "target_amount": "99999.99"}, headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["target_amount"] == "99999.99"

def test_decimal_contribution(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Decimal", "target_amount": "1000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "333.33"}, headers=user_a_auth)
    assert res.status_code == 200
    assert res.json()["current_amount"] == "333.33"
    assert res.json()["progress_percent"] == 33.33

def test_progress_percentage_calculation(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Progress", "target_amount": "3000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "1000"}, headers=user_a_auth)
    res = client.get(f"/api/goals/{goal_id}", headers=user_a_auth)
    assert res.json()["progress_percent"] == 33.33


# --- Summary Tests ---

def test_goals_summary(client, user_a_auth):
    client.post("/api/goals", json={"name": "Goal A", "target_amount": "10000"}, headers=user_a_auth)
    client.post("/api/goals", json={"name": "Goal B", "target_amount": "20000"}, headers=user_a_auth)
    res = client.get("/api/goals/summary", headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    assert data["total_goals"] == 2
    assert data["active_goals"] == 2
    assert data["completed_goals"] == 0
    assert float(data["total_target"]) == 30000.0
    assert float(data["total_saved"]) == 0.0

def test_goals_summary_empty(client, user_a_auth):
    res = client.get("/api/goals/summary", headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    assert data["total_goals"] == 0
    assert data["overall_progress"] == 0

def test_goals_summary_with_contributions(client, user_a_auth):
    create_res = client.post("/api/goals", json={"name": "Fund", "target_amount": "10000"}, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "2500"}, headers=user_a_auth)
    res = client.get("/api/goals/summary", headers=user_a_auth)
    data = res.json()
    assert float(data["total_saved"]) == 2500.0
    assert data["overall_progress"] == 25.0


# --- Projected Completion Tests ---

def test_projected_completion_with_enough_data(client, user_a_auth):
    create_res = client.post("/api/goals", json={
        "name": "Projected",
        "target_amount": "36500",
        "target_date": (date.today() + timedelta(days=365)).isoformat()
    }, headers=user_a_auth)
    goal_id = create_res.json()["id"]
    res = client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "100"}, headers=user_a_auth)
    data = res.json()
    assert data["projected_completion"] is not None

def test_projected_completion_no_contributions(client, user_a_auth):
    res = client.post("/api/goals", json={
        "name": "Empty",
        "target_amount": "10000",
        "target_date": (date.today() + timedelta(days=365)).isoformat()
    }, headers=user_a_auth)
    data = res.json()
    assert data["projected_completion"] is None


# --- Unauthenticated Tests ---

def test_unauthenticated_create(client):
    res = client.post("/api/goals", json={"name": "X", "target_amount": "1000"})
    assert res.status_code == 401

def test_unauthenticated_list(client):
    res = client.get("/api/goals")
    assert res.status_code == 401

def test_unauthenticated_contribute(client):
    res = client.post("/api/goals/1/contribute", json={"amount": "100"})
    assert res.status_code == 401


# --- Regression Tests (existing simulate_what_if) ---

def test_simulate_what_if_still_works(client, user_a_auth):
    from unittest.mock import patch
    from datetime import date
    from app.database.db import Transaction

    db = TestingSessionLocal()
    txs = [
        Transaction(user_id=1, date=date(2025, 1, 10), description="Food", amount=Decimal('100'), transaction_type="debit", category="Food"),
        Transaction(user_id=1, date=date(2025, 2, 10), description="Food", amount=Decimal('100'), transaction_type="debit", category="Food"),
        Transaction(user_id=1, date=date(2025, 3, 10), description="Food", amount=Decimal('100'), transaction_type="debit", category="Food"),
    ]
    sg = SavingsGoal(user_id=1, name="Car", target_amount=Decimal('240'))
    db.add_all(txs)
    db.add(sg)
    db.commit()
    db.close()

    res = client.post("/api/simulate", json={
        "category": "Food",
        "percent_change": -20,
        "months": 12,
        "goal_name": "Car"
    }, headers=user_a_auth)
    assert res.status_code == 200
    data = res.json()
    assert "months_to_goal" in data
