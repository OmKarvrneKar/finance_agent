import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
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

def _seed_tx(db, user_id, yr, mo, day, desc, amount, cat="Food"):
    tx = Transaction(user_id=user_id, date=date(yr, mo, day), description=desc,
                     amount=Decimal(str(amount)), transaction_type="debit", category=cat)
    db.add(tx)
    db.commit()
    return tx


class TestImprovedForecastNormalData:
    def test_with_historical_and_current(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        for mo in range(4, 7):
            _seed_tx(db, uid, 2026, mo, 10, f"Food {mo}", 100, "Food")
        _seed_tx(db, uid, 2026, 7, 5, "Food Jul", 50, "Food")
        _seed_tx(db, uid, 2026, 7, 10, "Food Jul 2", 30, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        assert res.status_code == 200
        data = res.json()
        assert abs(Decimal(str(data["actual_spend"])) - Decimal("80")) < Decimal("0.01")
        assert data["projected_month_end"] is not None
        assert data["method"] != "insufficient_data"
        assert data["confidence"] in ["high", "medium", "low"]
        assert "method_description" in data
        assert data["historical_average"] is not None
        assert data["months_of_history"] >= 1
        assert data["insufficient_data"] is False

    def test_daily_run_rate_calculation(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        for d in [1, 3, 5]:
            _seed_tx(db, uid, 2026, 7, d, "Food", 10, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        data = res.json()
        assert abs(Decimal(str(data["actual_spend"])) - Decimal("30")) < Decimal("0.01")
        assert data["daily_run_rate"] is not None
        assert data["remaining_spend"] is not None

    def test_blended_method_with_history(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        _seed_tx(db, uid, 2026, 5, 10, "Food", 100, "Food")
        _seed_tx(db, uid, 2026, 6, 10, "Food", 120, "Food")
        _seed_tx(db, uid, 2026, 7, 5, "Food", 50, "Food")
        _seed_tx(db, uid, 2026, 7, 10, "Food", 30, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        data = res.json()
        assert data["method"] == "blended_daily_run_rate_and_moving_average"
        assert data["historical_average"] is not None

    def test_no_current_month_uses_moving_average(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        _seed_tx(db, uid, 2026, 5, 10, "Food", 100, "Food")
        _seed_tx(db, uid, 2026, 6, 10, "Food", 120, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        data = res.json()
        assert abs(Decimal(str(data["actual_spend"]))) == Decimal("0")
        assert data["projected_month_end"] is not None
        assert "moving_average" in data["method"]

    def test_zero_spending_no_history(self, client, user_a_auth):
        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        data = res.json()
        assert abs(Decimal(str(data["actual_spend"]))) == Decimal("0")
        assert data["insufficient_data"] is True
        assert data["method"] == "insufficient_data"
        assert data["confidence"] == "none"

    def test_overall_no_category(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        _seed_tx(db, uid, 2026, 7, 1, "Food", 50, "Food")
        _seed_tx(db, uid, 2026, 7, 5, "Transport", 30, "Transport")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07", headers=user_a_auth)
        data = res.json()
        assert abs(Decimal(str(data["actual_spend"])) - Decimal("80")) < Decimal("0.01")


class TestInsufficientData:
    def test_single_transaction_low_confidence(self, client, user_a_auth):
        db = TestingSessionLocal()
        _seed_tx(db, 1, 2026, 7, 5, "Food", 50, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        data = res.json()
        assert abs(Decimal(str(data["actual_spend"])) - Decimal("50")) < Decimal("0.01")
        assert data["confidence"] in ["low", "medium"]
        assert data["method"] != "insufficient_data"

    def test_only_historical_no_current(self, client, user_a_auth):
        db = TestingSessionLocal()
        _seed_tx(db, 1, 2026, 5, 10, "Food", 100, "Food")
        _seed_tx(db, 1, 2026, 6, 10, "Food", 120, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        data = res.json()
        assert abs(Decimal(str(data["actual_spend"]))) == Decimal("0")
        assert data["projected_month_end"] is not None
        assert data["insufficient_data"] is False


class TestRefundsIncome:
    def test_only_debits_counted(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        _seed_tx(db, uid, 2026, 7, 1, "Food debit", 100, "Food")
        refund = Transaction(user_id=uid, date=date(2026, 7, 5), description="Refund",
                             amount=Decimal("50"), transaction_type="credit", category="Food")
        db.add(refund)
        db.commit()
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        data = res.json()
        assert abs(Decimal(str(data["actual_spend"])) - Decimal("100")) < Decimal("0.01")
        assert data["num_transactions"] == 1

    def test_income_excluded_from_forecast(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        salary = Transaction(user_id=uid, date=date(2026, 7, 1), description="Salary",
                             amount=Decimal("50000"), transaction_type="credit", category="Salary/Income")
        db.add(salary)
        _seed_tx(db, uid, 2026, 7, 5, "Food", 100, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07", headers=user_a_auth)
        data = res.json()
        assert abs(Decimal(str(data["actual_spend"])) - Decimal("100")) < Decimal("0.01")


class TestUserIsolation:
    def test_users_separate_forecasts(self, client, user_a_auth, user_b_auth):
        db = TestingSessionLocal()
        _seed_tx(db, 1, 2026, 7, 1, "A Food", 100, "Food")
        _seed_tx(db, 2, 2026, 7, 1, "B Food", 200, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res_a = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
            res_b = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_b_auth)
        assert abs(Decimal(str(res_a.json()["actual_spend"])) - Decimal("100")) < Decimal("0.01")
        assert abs(Decimal(str(res_b.json()["actual_spend"])) - Decimal("200")) < Decimal("0.01")

    def test_user_no_transactions(self, client, user_a_auth, user_b_auth):
        db = TestingSessionLocal()
        _seed_tx(db, 1, 2026, 7, 1, "A Food", 100, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res_b = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_b_auth)
        data = res_b.json()
        assert abs(Decimal(str(data["actual_spend"]))) == Decimal("0")
        assert data["insufficient_data"] is True

    def test_unauthenticated_returns_401(self, client):
        res = client.get("/api/forecast/improved?month=2026-07")
        assert res.status_code == 401


class TestDecimalAccuracy:
    def test_decimal_amounts_preserved(self, client, user_a_auth):
        db = TestingSessionLocal()
        _seed_tx(db, 1, 2026, 7, 1, "Food", "33.33", "Food")
        _seed_tx(db, 1, 2026, 7, 5, "Food", "66.67", "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        data = res.json()
        assert abs(Decimal(str(data["actual_spend"])) - Decimal("100")) < Decimal("0.01")
        assert data["daily_run_rate"] is not None
        assert "." in str(data["daily_run_rate"])

    def test_historical_average_decimal(self, client, user_a_auth):
        db = TestingSessionLocal()
        _seed_tx(db, 1, 2026, 5, 10, "Food", "99.99", "Food")
        _seed_tx(db, 1, 2026, 6, 10, "Food", "100.01", "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        data = res.json()
        assert abs(Decimal(str(data["historical_average"])) - Decimal("100")) < Decimal("0.01")


class TestCurrentMonthProjection:
    def test_projection_greater_than_actual(self, client, user_a_auth):
        db = TestingSessionLocal()
        _seed_tx(db, 1, 2026, 7, 1, "Food", 100, "Food")
        _seed_tx(db, 1, 2026, 7, 5, "Food", 50, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        data = res.json()
        assert Decimal(str(data["projected_month_end"])) >= Decimal(str(data["actual_spend"]))

    def test_remaining_spend_non_negative(self, client, user_a_auth):
        db = TestingSessionLocal()
        _seed_tx(db, 1, 2026, 7, 1, "Food", 100, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        data = res.json()
        assert Decimal(str(data["remaining_spend"])) >= 0

    def test_days_passed_and_remaining_sum_to_total(self, client, user_a_auth):
        db = TestingSessionLocal()
        _seed_tx(db, 1, 2026, 7, 1, "Food", 100, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07&category=Food", headers=user_a_auth)
        data = res.json()
        assert data["days_passed"] + data["days_remaining"] == data["total_days_in_month"]


class TestRegressionExistingBehavior:
    def test_original_forecast_still_works(self, client, user_a_auth):
        db = TestingSessionLocal()
        _seed_tx(db, 1, 2026, 7, 1, "Food", 10, "Food")
        _seed_tx(db, 1, 2026, 7, 3, "Food", 20, "Food")
        _seed_tx(db, 1, 2026, 7, 5, "Food", 20, "Food")
        db.close()

        res = client.get("/api/forecast/summary?month=2026-07", headers=user_a_auth)
        assert res.status_code == 200
        data = res.json()
        assert "forecast" in data
        assert "historical" in data
        assert data["forecast"]["spend_so_far"] == 50.0

    def test_original_alerts_still_work(self, client, user_a_auth):
        db = TestingSessionLocal()
        uid = 1
        _seed_tx(db, uid, 2026, 5, 10, "Food", 100, "Food")
        _seed_tx(db, uid, 2026, 6, 10, "Food", 100, "Food")
        _seed_tx(db, uid, 2026, 7, 1, "Food", 30, "Food")
        _seed_tx(db, uid, 2026, 7, 5, "Food", 30, "Food")
        _seed_tx(db, uid, 2026, 7, 10, "Food", 40, "Food")
        db.close()

        res = client.get("/api/forecast/alerts?month=2026-07", headers=user_a_auth)
        assert res.status_code == 200
        alerts = res.json()
        food_alert = next((a for a in alerts if a["category"] == "Food"), None)
        assert food_alert is not None
        assert food_alert["severity"] == "critical"

    def test_improved_endpoint_also_works(self, client, user_a_auth):
        db = TestingSessionLocal()
        _seed_tx(db, 1, 2026, 7, 1, "Food", 100, "Food")
        db.close()

        with patch("app.services.forecasting.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            res = client.get("/api/forecast/improved?month=2026-07", headers=user_a_auth)
        assert res.status_code == 200
        data = res.json()
        assert "actual_spend" in data
        assert "projected_month_end" in data
        assert "method" in data
        assert "method_description" in data
