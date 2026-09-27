import pytest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, User, Transaction


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
    client.post("/api/auth/register", json={"email": "u1@test.com", "password": "password123", "full_name": "User 1"})
    resp = client.post("/api/auth/login", data={"username": "u1@test.com", "password": "password123"})
    return resp.json()["access_token"]


@pytest.fixture()
def user2_token(client):
    client.post("/api/auth/register", json={"email": "u2@test.com", "password": "password123", "full_name": "User 2"})
    resp = client.post("/api/auth/login", data={"username": "u2@test.com", "password": "password123"})
    return resp.json()["access_token"]


def _seed(db, user_id, txs):
    for tx in txs:
        db.add(Transaction(
            user_id=user_id,
            date=tx["date"],
            description=tx["description"],
            amount=Decimal(str(tx["amount"])),
            transaction_type=tx["transaction_type"],
            category=tx.get("category", "Other"),
        ))
    db.commit()


def _get_user_id(client, token):
    import jwt
    from app.auth import JWT_SECRET_KEY
    return int(jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])["sub"])


class TestAnalyticsSummary:
    def test_empty_database_returns_zeros(self, client, user1_token):
        resp = client.get("/api/analytics/summary", headers={"Authorization": f"Bearer {user1_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(str(data["total_income"])) == Decimal('0')
        assert Decimal(str(data["total_expenses"])) == Decimal('0')
        assert Decimal(str(data["net_cashflow"])) == Decimal('0')
        assert data["transaction_count"] == 0
        assert data["category_breakdown"] == []
        assert data["spending_trend"] == []

    def test_income_and_expense_totals(self, client, user1_token, db_session):
        uid = _get_user_id(client, user1_token)
        _seed(db_session, uid, [
            {"date": date(2026, 9, 1), "description": "Salary", "amount": 50000, "transaction_type": "credit", "category": "Salary/Income"},
            {"date": date(2026, 9, 5), "description": "Groceries", "amount": 2000, "transaction_type": "debit", "category": "Groceries"},
            {"date": date(2026, 9, 10), "description": "Electricity", "amount": 1500, "transaction_type": "debit", "category": "Bills & Utilities"},
        ])
        resp = client.get("/api/analytics/summary", headers={"Authorization": f"Bearer {user1_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(str(data["total_income"])) == Decimal('50000')
        assert Decimal(str(data["total_expenses"])) == Decimal('3500')
        assert Decimal(str(data["net_cashflow"])) == Decimal('46500')
        assert data["transaction_count"] == 3

    def test_category_breakdown(self, client, user1_token, db_session):
        uid = _get_user_id(client, user1_token)
        _seed(db_session, uid, [
            {"date": date(2026, 9, 1), "description": "Groceries A", "amount": 1000, "transaction_type": "debit", "category": "Groceries"},
            {"date": date(2026, 9, 2), "description": "Groceries B", "amount": 500, "transaction_type": "debit", "category": "Groceries"},
            {"date": date(2026, 9, 3), "description": "Transport", "amount": 200, "transaction_type": "debit", "category": "Transport"},
        ])
        resp = client.get("/api/analytics/summary", headers={"Authorization": f"Bearer {user1_token}"})
        data = resp.json()
        cats = {c["category"]: c["amount"] for c in data["category_breakdown"]}
        assert Decimal(str(cats["Groceries"])) == Decimal('1500')
        assert Decimal(str(cats["Transport"])) == Decimal('200')

    def test_spending_trend(self, client, user1_token, db_session):
        uid = _get_user_id(client, user1_token)
        _seed(db_session, uid, [
            {"date": date(2026, 8, 15), "description": "Aug expense", "amount": 3000, "transaction_type": "debit", "category": "Shopping"},
            {"date": date(2026, 9, 10), "description": "Sep expense", "amount": 2000, "transaction_type": "debit", "category": "Shopping"},
        ])
        resp = client.get("/api/analytics/summary", headers={"Authorization": f"Bearer {user1_token}"})
        data = resp.json()
        trend = {t["month"]: t["amount"] for t in data["spending_trend"]}
        assert Decimal(str(trend["2026-08"])) == Decimal('3000')
        assert Decimal(str(trend["2026-09"])) == Decimal('2000')

    def test_date_range_filtering(self, client, user1_token, db_session):
        uid = _get_user_id(client, user1_token)
        _seed(db_session, uid, [
            {"date": date(2026, 8, 1), "description": "Aug tx", "amount": 500, "transaction_type": "debit", "category": "Shopping"},
            {"date": date(2026, 9, 1), "description": "Sep tx", "amount": 700, "transaction_type": "debit", "category": "Shopping"},
        ])
        resp = client.get(
            "/api/analytics/summary",
            params={"start_date": "2026-09-01", "end_date": "2026-09-30"},
            headers={"Authorization": f"Bearer {user1_token}"}
        )
        data = resp.json()
        assert data["transaction_count"] == 1
        assert Decimal(str(data["total_expenses"])) == Decimal('700')

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/analytics/summary")
        assert resp.status_code == 401

    def test_user_isolation(self, client, user1_token, user2_token, db_session):
        uid1 = _get_user_id(client, user1_token)
        _seed(db_session, uid1, [
            {"date": date(2026, 9, 1), "description": "User1 tx", "amount": 1000, "transaction_type": "debit", "category": "Food"},
        ])
        r1 = client.get("/api/analytics/summary", headers={"Authorization": f"Bearer {user1_token}"})
        r2 = client.get("/api/analytics/summary", headers={"Authorization": f"Bearer {user2_token}"})
        assert r1.json()["transaction_count"] == 1
        assert r2.json()["transaction_count"] == 0

    def test_period_comparison_data(self, client, user1_token, db_session):
        uid = _get_user_id(client, user1_token)
        _seed(db_session, uid, [
            {"date": date(2026, 9, 5), "description": "Sep debit", "amount": 1000, "transaction_type": "debit", "category": "Food"},
            {"date": date(2026, 9, 10), "description": "Sep credit", "amount": 5000, "transaction_type": "credit", "category": "Salary"},
        ])
        resp = client.get(
            "/api/analytics/summary",
            params={"start_date": "2026-09-01", "end_date": "2026-09-30"},
            headers={"Authorization": f"Bearer {user1_token}"}
        )
        data = resp.json()
        assert data["transaction_count"] == 2
        assert Decimal(str(data["total_income"])) == Decimal('5000')
        assert Decimal(str(data["total_expenses"])) == Decimal('1000')

    def test_response_structure(self, client, user1_token):
        resp = client.get("/api/analytics/summary", headers={"Authorization": f"Bearer {user1_token}"})
        data = resp.json()
        assert isinstance(data["total_income"], (int, float, str))
        assert isinstance(data["total_expenses"], (int, float, str))
        assert isinstance(data["net_cashflow"], (int, float, str))
        assert isinstance(data["transaction_count"], int)
        assert isinstance(data["category_breakdown"], list)
        assert isinstance(data["spending_trend"], list)
