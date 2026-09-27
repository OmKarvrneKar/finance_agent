import pytest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database.db import Base, get_db, Transaction, BudgetGoal

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

def _seed_tx(db, uid, yr, mo, day, desc, amount, cat="Food", tx_type="debit"):
    t = Transaction(user_id=uid, date=date(yr, mo, day), description=desc,
                    amount=Decimal(str(amount)), transaction_type=tx_type, category=cat)
    db.add(t)
    db.commit()
    return t

def _seed_budget(db, uid, cat, cap):
    b = BudgetGoal(user_id=uid, category=cat, monthly_cap=Decimal(str(cap)))
    db.add(b)
    db.commit()
    return b


class TestNormalUserSufficientData:
    def test_with_6_months_data(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 7):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Salary/Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Rent", 15000, "Housing", "debit")
            _seed_tx(db, uid, 2026, mo, 20, "Food", 5000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        assert res.status_code == 200
        data = res.json()
        assert data["overall_score"] is not None
        assert Decimal(str(data["overall_score"])) >= 0
        assert Decimal(str(data["overall_score"])) <= 100
        assert data["insufficient_data"] is False
        assert data["months_analyzed"] == 6
        assert "savings_rate" in data["components"]
        assert "budget_adherence" in data["components"]
        assert "income_stability" in data["components"]
        assert "spending_consistency" in data["components"]
        assert "formula" in data

    def test_savings_rate_positive(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 30000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert savings["raw_value"] is not None
        assert Decimal(str(savings["raw_value"])) == Decimal("40.00")
        assert savings["score"] is not None
        assert Decimal(str(savings["score"])) == Decimal("100")

    def test_with_budgets(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        _seed_budget(db, uid, "Food", 10000)
        _seed_budget(db, uid, "Transport", 5000)
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 8000, "Food", "debit")
            _seed_tx(db, uid, 2026, mo, 20, "Transport", 3000, "Transport", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        budget = data["components"]["budget_adherence"]
        assert budget["raw_value"] is not None
        assert Decimal(str(budget["raw_value"])) == Decimal("100")


class TestInsufficientData:
    def test_empty_database(self, client, user_a_auth):
        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert data["insufficient_data"] is True
        assert data["overall_score"] is None
        assert data["months_analyzed"] == 0

    def test_only_one_month(self, client, user_a_auth):
        db = TestingSessionLocal()
        _seed_tx(db, 1, 2026, 7, 10, "Salary", 50000, "Income", "credit")
        _seed_tx(db, 1, 2026, 7, 15, "Food", 10000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert data["insufficient_data"] is True
        assert data["overall_score"] is None

    def test_only_income_no_expense(self, client, user_a_auth):
        db = TestingSessionLocal()
        for mo in range(1, 4):
            _seed_tx(db, 1, 2026, mo, 10, "Salary", 50000, "Income", "credit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert data["insufficient_data"] is True


class TestZeroNegativeSavings:
    def test_zero_savings(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 50000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert data["insufficient_data"] is False
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) == Decimal("0")
        assert Decimal(str(savings["score"])) == Decimal("0")

    def test_negative_savings_clamped_to_zero(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 30000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 40000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) < 0
        assert Decimal(str(savings["score"])) == Decimal("0")


class TestBudgetOverUnder:
    def test_all_budgets_on_track(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        _seed_budget(db, uid, "Food", 20000)
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 10000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert data["insufficient_data"] is False
        budget = data["components"]["budget_adherence"]
        assert Decimal(str(budget["raw_value"])) == Decimal("100")

    def test_all_budgets_over(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        _seed_budget(db, uid, "Food", 5000)
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 15000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        budget = data["components"]["budget_adherence"]
        assert Decimal(str(budget["raw_value"])) == Decimal("0")

    def test_mixed_budgets(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        _seed_budget(db, uid, "Food", 10000)
        _seed_budget(db, uid, "Transport", 20000)
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 8000, "Food", "debit")
            _seed_tx(db, uid, 2026, mo, 20, "Transport", 15000, "Transport", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        budget = data["components"]["budget_adherence"]
        assert Decimal(str(budget["raw_value"])) == Decimal("100")

    def test_no_budgets_returns_none(self, client, user_a_auth):
        db = TestingSessionLocal()
        for mo in range(1, 4):
            _seed_tx(db, 1, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, 1, 2026, mo, 15, "Food", 10000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        budget = data["components"]["budget_adherence"]
        assert budget["raw_value"] is None


class TestIncomeVariability:
    def test_stable_income(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 7):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 20000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        stability = data["components"]["income_stability"]
        assert Decimal(str(stability["raw_value"])) == Decimal("100")
        assert Decimal(str(stability["score"])) == Decimal("100")

    def test_volatile_income(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        incomes = [30000, 60000, 20000, 70000, 25000, 65000]
        for i, inc in enumerate(incomes):
            mo = i + 1
            _seed_tx(db, uid, 2026, mo, 10, "Salary", inc, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 15000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        stability = data["components"]["income_stability"]
        assert stability["raw_value"] is not None
        assert Decimal(str(stability["raw_value"])) < Decimal("100")


class TestUserIsolation:
    def test_users_separate_scores(self, client, user_a_auth, user_b_auth):
        db = TestingSessionLocal()
        for mo in range(1, 4):
            _seed_tx(db, 1, 2026, mo, 10, "A Salary", 50000, "Income", "credit")
            _seed_tx(db, 1, 2026, mo, 15, "A Food", 30000, "Food", "debit")
            _seed_tx(db, 2, 2026, mo, 10, "B Salary", 50000, "Income", "credit")
            _seed_tx(db, 2, 2026, mo, 15, "B Food", 10000, "Food", "debit")
        db.close()

        res_a = client.get("/api/health", headers=user_a_auth)
        res_b = client.get("/api/health", headers=user_b_auth)
        data_a = res_a.json()
        data_b = res_b.json()
        assert data_a["insufficient_data"] is False
        assert data_b["insufficient_data"] is False
        assert data_a["components"]["savings_rate"]["raw_value"] != data_b["components"]["savings_rate"]["raw_value"]

    def test_unauthenticated_returns_401(self, client):
        res = client.get("/api/health")
        assert res.status_code == 401


class TestDecimalAccuracy:
    def test_decimal_preserved_in_scores(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 33333.33, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert data["insufficient_data"] is False
        savings = data["components"]["savings_rate"]
        assert savings["raw_value"] is not None
        assert isinstance(savings["raw_value"], (str, float, int))
        assert isinstance(savings["score"], (str, float, int))
        overall = data["overall_score"]
        assert isinstance(overall, (str, float, int))

    def test_savings_rate_decimal_calculation(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 35000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) == Decimal("30.00")


class TestFormulaTransparency:
    def test_formula_in_response(self, client, user_a_auth):
        db = TestingSessionLocal()
        for mo in range(1, 4):
            _seed_tx(db, 1, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, 1, 2026, mo, 15, "Food", 20000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        formula = data["formula"]
        assert "overall" in formula
        assert "savings_rate_score" in formula
        assert "budget_adherence_score" in formula
        assert "income_stability_score" in formula
        assert "spending_consistency_score" in formula
        assert "weights" in formula
        assert "40%" in formula["weights"]
        assert "25%" in formula["weights"]
        assert "20%" in formula["weights"]
        assert "15%" in formula["weights"]

    def test_component_descriptions_present(self, client, user_a_auth):
        db = TestingSessionLocal()
        for mo in range(1, 4):
            _seed_tx(db, 1, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, 1, 2026, mo, 15, "Food", 20000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        for key, comp in data["components"].items():
            assert "description" in comp
            assert "weight" in comp
            assert "score" in comp
            assert "raw_value" in comp
