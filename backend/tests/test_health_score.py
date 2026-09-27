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
        assert budget["score"] is None
        assert "0% (no budgets)" in budget["weight"]
        # Other weights should be redistributed
        savings_weight = data["components"]["savings_rate"]["weight"]
        assert float(savings_weight.replace("%", "")) > 40  # Should be higher than base 40%


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
        uid = 1
        _seed_budget(db, uid, "Food", 30000)
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
        assert "40.00%" in formula["weights"]
        assert "25.00%" in formula["weights"]
        assert "20.00%" in formula["weights"]
        assert "15.00%" in formula["weights"]

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


class TestSavingsRateThresholds:
    """Test all savings rate thresholds and interpolation."""

    def test_savings_rate_0_percent(self, client, user_a_auth):
        """0% savings: income == expenses -> score = 0."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 50000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) == Decimal("0")
        assert Decimal(str(savings["score"])) == Decimal("0")

    def test_savings_rate_5_percent(self, client, user_a_auth):
        """5% savings -> score = 25."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 47500, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) == Decimal("5.00")
        assert Decimal(str(savings["score"])) == Decimal("25")

    def test_savings_rate_10_percent(self, client, user_a_auth):
        """10% savings -> score = 50."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 45000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) == Decimal("10.00")
        assert Decimal(str(savings["score"])) == Decimal("50")

    def test_savings_rate_20_percent(self, client, user_a_auth):
        """20% savings -> score = 75."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 40000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) == Decimal("20.00")
        assert Decimal(str(savings["score"])) == Decimal("75")

    def test_savings_rate_30_percent(self, client, user_a_auth):
        """30% savings -> score = 100."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 35000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) == Decimal("30.00")
        assert Decimal(str(savings["score"])) == Decimal("100")

    def test_savings_rate_above_30_percent(self, client, user_a_auth):
        """40% savings -> score = 100 (capped)."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 30000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) == Decimal("40.00")
        assert Decimal(str(savings["score"])) == Decimal("100")


class TestSavingsRateInterpolation:
    """Test linear interpolation between thresholds."""

    def test_interpolation_2_5_percent(self, client, user_a_auth):
        """2.5% savings: between 0% (0) and 5% (25) -> score = 12.5."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 48750, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) == Decimal("2.50")
        assert Decimal(str(savings["score"])) == Decimal("12.50")

    def test_interpolation_7_5_percent(self, client, user_a_auth):
        """7.5% savings: between 5% (25) and 10% (50) -> score = 37.5."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 46250, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) == Decimal("7.50")
        assert Decimal(str(savings["score"])) == Decimal("37.50")

    def test_interpolation_15_percent(self, client, user_a_auth):
        """15% savings: between 10% (50) and 20% (75) -> score = 62.5."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 42500, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) == Decimal("15.00")
        assert Decimal(str(savings["score"])) == Decimal("62.50")

    def test_interpolation_25_percent(self, client, user_a_auth):
        """25% savings: between 20% (75) and 30% (100) -> score = 87.5."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 37500, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) == Decimal("25.00")
        assert Decimal(str(savings["score"])) == Decimal("87.50")


class TestNoBudgetWeightRedistribution:
    """Test that no-budget case redistributes weights correctly."""

    def test_no_budgets_redistributes_weights(self, client, user_a_auth):
        """Without budgets, 25% weight is redistributed to other components."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 20000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        
        # Budget should be null
        assert data["components"]["budget_adherence"]["score"] is None
        assert data["components"]["budget_adherence"]["raw_value"] is None
        
        # Other weights should be redistributed (higher than base)
        savings_weight = float(data["components"]["savings_rate"]["weight"].replace("%", ""))
        income_weight = float(data["components"]["income_stability"]["weight"].replace("%", ""))
        spending_weight = float(data["components"]["spending_consistency"]["weight"].replace("%", ""))
        
        # Base weights: savings=40, income=20, spending=15, total=75
        # Redistributed: savings=40/75*100=53.33, income=20/75*100=26.67, spending=15/75*100=20
        assert savings_weight > 40  # Should be ~53.33
        assert income_weight > 20  # Should be ~26.67
        assert spending_weight > 15  # Should be ~20
        assert abs(savings_weight + income_weight + spending_weight - 100) < 0.1

    def test_with_budgets_keeps_base_weights(self, client, user_a_auth):
        """With budgets, base weights are used."""
        db = TestingSessionLocal()
        uid = 1
        _seed_budget(db, uid, "Food", 20000)
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 10000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        
        # Budget should have a score
        assert data["components"]["budget_adherence"]["score"] is not None
        
        # Weights should include budget
        weights_str = data["formula"]["weights"]
        assert "budget" in weights_str


class TestInsufficientDataScenarios:
    """Test various insufficient data scenarios."""

    def test_zero_income_all_months(self, client, user_a_auth):
        """Zero income in all months -> insufficient data."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 15, "Food", 10000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert data["insufficient_data"] is True
        assert data["overall_score"] is None

    def test_only_one_month_of_data(self, client, user_a_auth):
        """Only one month -> insufficient data."""
        db = TestingSessionLocal()
        uid = 1
        _seed_tx(db, uid, 2026, 7, 10, "Salary", 50000, "Income", "credit")
        _seed_tx(db, uid, 2026, 7, 15, "Food", 20000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert data["insufficient_data"] is True
        assert data["overall_score"] is None

    def test_two_months_with_data(self, client, user_a_auth):
        """Two months with data -> sufficient data."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 3):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 20000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert data["insufficient_data"] is False
        assert data["overall_score"] is not None


class TestNegativeSavings:
    """Test negative savings (spending > income)."""

    def test_negative_savings_score_zero(self, client, user_a_auth):
        """Negative savings -> raw_value negative, score = 0."""
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

    def test_deeply_negative_savings(self, client, user_a_auth):
        """Deeply negative savings (100% overspend) -> score = 0."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 20000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Expenses", 40000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        savings = data["components"]["savings_rate"]
        assert Decimal(str(savings["raw_value"])) < 0
        assert Decimal(str(savings["score"])) == Decimal("0")


class TestZeroIncome:
    """Test zero income scenarios."""

    def test_zero_income_savings_rate_none(self, client, user_a_auth):
        """Zero income -> savings_rate = None (division by zero avoided)."""
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 15, "Food", 10000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        # With no income, has_income is False -> insufficient_data
        assert data["insufficient_data"] is True


class TestConcreteExampleCalculations:
    """Verify 5 concrete example calculations manually."""

    def test_example_1_20_percent_savings_with_budgets(self, client, user_a_auth):
        """
        Example 1: 20% savings, all budgets on track, stable income, consistent spending.
        - Income: 50000/month, Expenses: 40000/month -> savings_rate = 20%
        - Budget: Food cap 50000, spent 40000 -> on track
        - Income stability: constant 50000 -> CV=0 -> stability=100
        - Spending consistency: constant 40000 -> CV=0 -> consistency=100
        
        Expected:
        - savings_score = 75 (20% -> 75)
        - budget_score = 100 (100% on track)
        - income_score = 100
        - spending_score = 100
        - overall = (75*0.40 + 100*0.25 + 100*0.20 + 100*0.15) = 30 + 25 + 20 + 15 = 90
        """
        db = TestingSessionLocal()
        uid = 1
        _seed_budget(db, uid, "Food", 50000)
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 40000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert Decimal(str(data["components"]["savings_rate"]["raw_value"])) == Decimal("20.00")
        assert Decimal(str(data["components"]["savings_rate"]["score"])) == Decimal("75")
        assert Decimal(str(data["components"]["budget_adherence"]["raw_value"])) == Decimal("100")
        assert Decimal(str(data["components"]["budget_adherence"]["score"])) == Decimal("100")
        assert Decimal(str(data["components"]["income_stability"]["score"])) == Decimal("100")
        assert Decimal(str(data["components"]["spending_consistency"]["score"])) == Decimal("100")
        assert Decimal(str(data["overall_score"])) == Decimal("90")

    def test_example_2_10_percent_savings_no_budgets(self, client, user_a_auth):
        """
        Example 2: 10% savings, no budgets, stable income, consistent spending.
        - Income: 50000/month, Expenses: 45000/month -> savings_rate = 10%
        - No budgets -> budget_score = None, weights redistributed
        
        Expected weights (redistributed):
        - savings: 40/75 = 53.33%
        - income: 20/75 = 26.67%
        - spending: 15/75 = 20%
        
        Expected:
        - savings_score = 50 (10% -> 50)
        - budget_score = None
        - income_score = 100
        - spending_score = 100
        - overall = (50*53.33 + 100*26.67 + 100*20) / 100 = 26.665 + 26.67 + 20 = 73.335 ≈ 73.34
        """
        db = TestingSessionLocal()
        uid = 1
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 50000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 45000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert Decimal(str(data["components"]["savings_rate"]["raw_value"])) == Decimal("10.00")
        assert Decimal(str(data["components"]["savings_rate"]["score"])) == Decimal("50")
        assert data["components"]["budget_adherence"]["score"] is None
        assert Decimal(str(data["components"]["income_stability"]["score"])) == Decimal("100")
        assert Decimal(str(data["components"]["spending_consistency"]["score"])) == Decimal("100")
        # Overall should be ~73.33
        assert Decimal(str(data["overall_score"])) == Decimal("73.33")

    def test_example_3_5_percent_savings_mixed_budgets(self, client, user_a_auth):
        """
        Example 3: 5% savings, budgets on track, volatile income, volatile spending.
        - Income: alternating 40000/60000 -> mean=50000, CV > 0
        - Expenses: varying -> CV > 0
        - Budget: Food cap 60000, all expenses under cap -> on track
        
        Expected (simplified):
        - savings_score = 25 (5% -> 25)
        - budget_score = 100 (100% on track)
        - income_score < 100 (volatile)
        - spending_score < 100 (volatile)
        """
        db = TestingSessionLocal()
        uid = 1
        _seed_budget(db, uid, "Food", 60000)
        # Month 1: income 40000, expenses 38000 (5% savings)
        _seed_tx(db, uid, 2026, 1, 10, "Salary", 40000, "Income", "credit")
        _seed_tx(db, uid, 2026, 1, 15, "Food", 38000, "Food", "debit")
        # Month 2: income 60000, expenses 57000 (5% savings)
        _seed_tx(db, uid, 2026, 2, 10, "Salary", 60000, "Income", "credit")
        _seed_tx(db, uid, 2026, 2, 15, "Food", 57000, "Food", "debit")
        # Month 3: income 40000, expenses 38000 (5% savings)
        _seed_tx(db, uid, 2026, 3, 10, "Salary", 40000, "Income", "credit")
        _seed_tx(db, uid, 2026, 3, 15, "Food", 38000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert Decimal(str(data["components"]["savings_rate"]["raw_value"])) == Decimal("5.00")
        assert Decimal(str(data["components"]["savings_rate"]["score"])) == Decimal("25")
        assert Decimal(str(data["components"]["budget_adherence"]["raw_value"])) == Decimal("100")
        assert Decimal(str(data["components"]["income_stability"]["raw_value"])) < Decimal("100")
        assert Decimal(str(data["components"]["spending_consistency"]["raw_value"])) < Decimal("100")

    def test_example_4_negative_savings_over_budget(self, client, user_a_auth):
        """
        Example 4: Negative savings, budget over.
        - Income: 30000/month, Expenses: 40000/month -> savings_rate = -33.33%
        - Budget: Food cap 20000, spent 40000 -> over budget
        
        Expected:
        - savings_score = 0 (negative clamped to 0)
        - budget_score = 0 (0% on track)
        - income_score = 100 (stable)
        - spending_score = 100 (consistent)
        - overall = (0*0.40 + 0*0.25 + 100*0.20 + 100*0.15) = 0 + 0 + 20 + 15 = 35
        """
        db = TestingSessionLocal()
        uid = 1
        _seed_budget(db, uid, "Food", 20000)
        for mo in range(1, 4):
            _seed_tx(db, uid, 2026, mo, 10, "Salary", 30000, "Income", "credit")
            _seed_tx(db, uid, 2026, mo, 15, "Food", 40000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert Decimal(str(data["components"]["savings_rate"]["raw_value"])) < 0
        assert Decimal(str(data["components"]["savings_rate"]["score"])) == Decimal("0")
        assert Decimal(str(data["components"]["budget_adherence"]["raw_value"])) == Decimal("0")
        assert Decimal(str(data["components"]["budget_adherence"]["score"])) == Decimal("0")
        assert Decimal(str(data["components"]["income_stability"]["score"])) == Decimal("100")
        assert Decimal(str(data["components"]["spending_consistency"]["score"])) == Decimal("100")
        assert Decimal(str(data["overall_score"])) == Decimal("35")

    def test_example_5_30_percent_savings_no_budgets_volatile(self, client, user_a_auth):
        """
        Example 5: 30% savings, no budgets, volatile income.
        - Income: varying [40000, 60000, 50000] -> mean=50000, CV > 0
        - Expenses: [28000, 42000, 35000] -> 30% savings each month
        - No budgets -> weight redistribution
        
        Expected:
        - savings_score = 100 (30% -> 100)
        - budget_score = None
        - income_score < 100 (volatile)
        - spending_score < 100 (volatile)
        """
        db = TestingSessionLocal()
        uid = 1
        # Month 1: income 40000, expenses 28000 (30% savings)
        _seed_tx(db, uid, 2026, 1, 10, "Salary", 40000, "Income", "credit")
        _seed_tx(db, uid, 2026, 1, 15, "Food", 28000, "Food", "debit")
        # Month 2: income 60000, expenses 42000 (30% savings)
        _seed_tx(db, uid, 2026, 2, 10, "Salary", 60000, "Income", "credit")
        _seed_tx(db, uid, 2026, 2, 15, "Food", 42000, "Food", "debit")
        # Month 3: income 50000, expenses 35000 (30% savings)
        _seed_tx(db, uid, 2026, 3, 10, "Salary", 50000, "Income", "credit")
        _seed_tx(db, uid, 2026, 3, 15, "Food", 35000, "Food", "debit")
        db.close()

        res = client.get("/api/health", headers=user_a_auth)
        data = res.json()
        assert Decimal(str(data["components"]["savings_rate"]["raw_value"])) == Decimal("30.00")
        assert Decimal(str(data["components"]["savings_rate"]["score"])) == Decimal("100")
        assert data["components"]["budget_adherence"]["score"] is None
        assert Decimal(str(data["components"]["income_stability"]["raw_value"])) < Decimal("100")
        assert Decimal(str(data["components"]["spending_consistency"]["raw_value"])) < Decimal("100")
