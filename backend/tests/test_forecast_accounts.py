"""Phase 4D: account-aware forecasting (backend only).

GET /api/forecast/{summary,improved,alerts,category/...} accept an optional
``account_id``. When supplied, both the current-period spend AND the
historical data driving the forecast are restricted to that account;
NULL-account transactions are excluded. Foreign/nonexistent accounts return
404. Omitting ``account_id`` preserves the existing forecasting behaviour,
formulas, and date handling exactly.
"""
import pytest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, Account, Transaction
from app.services.forecasting import get_improved_forecast

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
def user_a_auth(client):
    token = _register_and_login(client, "usera@test.com", "Pass123456789", "User A")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_b_auth(client):
    token = _register_and_login(client, "userb@test.com", "Pass123456789", "User B")
    return {"Authorization": f"Bearer {token}"}


def _user_id(auth) -> int:
    import jwt
    from app.auth import JWT_SECRET_KEY
    token = auth["Authorization"].split(" ", 1)[1]
    return int(jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])["sub"])


def _add_account(db, user_id, name="Account", account_type="bank"):
    account = Account(user_id=user_id, name=name, account_type=account_type)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account.id


def _seed_tx(db, user_id, yr, mo, day, amount, cat="Food", account_id=None):
    tx = Transaction(
        user_id=user_id,
        date=date(yr, mo, day),
        description="Spend",
        amount=Decimal(str(amount)),
        transaction_type="debit",
        category=cat,
        account_id=account_id,
    )
    db.add(tx)
    db.commit()
    return tx


def _improved(client, auth, month, account_id=None, category=None):
    params = [f"month={month}"]
    if account_id is not None:
        params.append(f"account_id={account_id}")
    if category is not None:
        params.append(f"category={category}")
    return client.get(f"/api/forecast/improved?{'&'.join(params)}", headers=auth)


class TestAccountAwareForecast:
    def test_existing_forecast_unchanged(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc = _add_account(db, uid, "A")
        _seed_tx(db, uid, 2026, 7, 5, "100", account_id=acc)
        _seed_tx(db, uid, 2026, 7, 6, "50")   # NULL account
        _seed_tx(db, uid, 2026, 7, 7, "25")   # NULL account (>=3 txns for run rate)

        resp = _improved(client, user_a_auth, "2026-07")
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(str(data["actual_spend"])) == Decimal("175")
        assert data["num_transactions"] == 3

        # Service: omitted account_id and explicit None are identical.
        omitted = get_improved_forecast(None, "2026-07", db, uid)
        explicit_none = get_improved_forecast(None, "2026-07", db, uid, account_id=None)
        assert omitted == explicit_none
        db.close()

        # /summary is unchanged too: it includes every account plus NULL rows.
        summary = client.get("/api/forecast/summary?month=2026-07", headers=user_a_auth)
        assert summary.status_code == 200
        assert Decimal(str(summary.json()["forecast"]["spend_so_far"])) == Decimal("175")

    def test_account_filtered_forecast(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        acc_b = _add_account(db, uid, "B")
        _seed_tx(db, uid, 2026, 7, 5, "50", account_id=acc_a)
        _seed_tx(db, uid, 2026, 7, 6, "30", account_id=acc_a)
        _seed_tx(db, uid, 2026, 7, 7, "20", account_id=acc_a)     # A total 100 (3 txns)
        _seed_tx(db, uid, 2026, 7, 5, "100", account_id=acc_b)
        _seed_tx(db, uid, 2026, 7, 6, "60", account_id=acc_b)
        _seed_tx(db, uid, 2026, 7, 7, "40", account_id=acc_b)     # B total 200 (3 txns)
        db.close()

        data_a = _improved(client, user_a_auth, "2026-07", account_id=acc_a).json()
        assert Decimal(str(data_a["actual_spend"])) == Decimal("100")
        assert data_a["num_transactions"] == 3

        data_b = _improved(client, user_a_auth, "2026-07", account_id=acc_b).json()
        assert Decimal(str(data_b["actual_spend"])) == Decimal("200")
        assert data_b["num_transactions"] == 3

        # /summary (run-rate + historical path) honours the same filter.
        summary = client.get(
            f"/api/forecast/summary?month=2026-07&account_id={acc_a}", headers=user_a_auth
        ).json()
        assert Decimal(str(summary["forecast"]["spend_so_far"])) == Decimal("100")

    def test_historical_account_filtering(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        acc_b = _add_account(db, uid, "B")
        _seed_tx(db, uid, 2026, 6, 10, "300", account_id=acc_a)   # A's history
        _seed_tx(db, uid, 2026, 6, 12, "900", account_id=acc_b)   # B's history
        db.close()

        # Current month with no spending -> moving average of HISTORY only.
        data_a = _improved(client, user_a_auth, "2026-10", account_id=acc_a).json()
        assert data_a["method"] == "moving_average"
        assert Decimal(str(data_a["projected_month_end"])) == Decimal("300")
        assert data_a["months_of_history"] == 1

        data_b = _improved(client, user_a_auth, "2026-10", account_id=acc_b).json()
        assert Decimal(str(data_b["projected_month_end"])) == Decimal("900")

        # Unfiltered history averages both accounts.
        data_all = _improved(client, user_a_auth, "2026-10").json()
        assert Decimal(str(data_all["projected_month_end"])) == Decimal("1200")

        # /summary's historical block uses the same account filter.
        summary = client.get(
            f"/api/forecast/summary?month=2026-10&account_id={acc_a}", headers=user_a_auth
        ).json()
        assert Decimal(str(summary["historical"]["historical_average"])) == Decimal("300")
        assert summary["historical"]["months_used"] == 1

    def test_foreign_account_returns_404(self, client, user_a_auth, user_b_auth):
        uid_b = _user_id(user_b_auth)
        db = TestingSessionLocal()
        foreign = _add_account(db, uid_b, "User B account")
        db.close()

        own = _improved(client, user_b_auth, "2026-07", account_id=foreign)
        assert own.status_code == 200

        stolen = _improved(client, user_a_auth, "2026-07", account_id=foreign)
        assert stolen.status_code == 404
        assert stolen.json()["detail"] == "Account not found."

        stolen_summary = client.get(
            f"/api/forecast/summary?month=2026-07&account_id={foreign}", headers=user_a_auth
        )
        assert stolen_summary.status_code == 404

    def test_nonexistent_account_returns_404(self, client, user_a_auth):
        resp = _improved(client, user_a_auth, "2026-07", account_id=999999)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Account not found."

    def test_null_account_transactions_excluded(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc = _add_account(db, uid, "Scoped")
        _seed_tx(db, uid, 2026, 10, 2, "100", account_id=acc)
        _seed_tx(db, uid, 2026, 10, 3, "50")  # NULL account
        db.close()

        filtered = _improved(client, user_a_auth, "2026-10", account_id=acc).json()
        assert Decimal(str(filtered["actual_spend"])) == Decimal("100")
        assert filtered["num_transactions"] == 1

        unfiltered = _improved(client, user_a_auth, "2026-10").json()
        assert Decimal(str(unfiltered["actual_spend"])) == Decimal("150")

    def test_multiple_accounts(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        acc_b = _add_account(db, uid, "B")
        _seed_tx(db, uid, 2026, 10, 2, "100.50", account_id=acc_a)
        _seed_tx(db, uid, 2026, 10, 3, "200.25", account_id=acc_b)
        _seed_tx(db, uid, 2026, 10, 4, "49.25")  # NULL account
        db.close()

        all_spend = Decimal(str(_improved(client, user_a_auth, "2026-10").json()["actual_spend"]))
        a_spend = Decimal(str(_improved(client, user_a_auth, "2026-10", account_id=acc_a).json()["actual_spend"]))
        b_spend = Decimal(str(_improved(client, user_a_auth, "2026-10", account_id=acc_b).json()["actual_spend"]))

        assert a_spend == Decimal("100.50")
        assert b_spend == Decimal("200.25")
        assert a_spend + b_spend + Decimal("49.25") == all_spend

    def test_insufficient_data_for_account_without_transactions(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        _seed_tx(db, uid, 2026, 6, 10, "500")  # history that belongs to no account
        empty_acc = _add_account(db, uid, "Empty")
        db.close()

        data = _improved(client, user_a_auth, "2026-10", account_id=empty_acc).json()
        assert data["method"] == "insufficient_data"
        assert data["insufficient_data"] is True
        assert data["projected_month_end"] is None
        assert data["confidence"] == "none"
        assert data["months_of_history"] == 0

    def test_decimal_and_rounding_correctness(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc = _add_account(db, uid, "A")
        _seed_tx(db, uid, 2026, 7, 5, "33.33", account_id=acc)
        _seed_tx(db, uid, 2026, 7, 6, "66.67", account_id=acc)

        # Service level: exact Decimal arithmetic, no float drift.
        result = get_improved_forecast(None, "2026-07", db, uid, account_id=acc)
        assert result["actual_spend"] == Decimal("100.00")
        assert isinstance(result["actual_spend"], Decimal)
        # daily_run_rate * days_passed reconstructs the exact spend.
        days_passed = result["days_passed"]
        assert abs(result["daily_run_rate"] * Decimal(str(days_passed)) - Decimal("100.00")) < Decimal("0.01")
        db.close()

        # API level: values survive JSON round-trip within tolerance.
        data = _improved(client, user_a_auth, "2026-07", account_id=acc).json()
        assert abs(Decimal(str(data["actual_spend"])) - Decimal("100.00")) < Decimal("0.01")
        assert abs(Decimal(str(data["daily_run_rate"])) * Decimal(str(data["days_passed"])) - Decimal("100.00")) < Decimal("0.01")

    def test_date_boundary_behavior(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc = _add_account(db, uid, "A")
        _seed_tx(db, uid, 2026, 9, 30, "999", account_id=acc)   # previous month -> history
        _seed_tx(db, uid, 2026, 10, 1, "10", account_id=acc)    # first day, in range
        _seed_tx(db, uid, 2026, 10, 4, "20", account_id=acc)    # today, in range
        _seed_tx(db, uid, 2026, 10, 20, "500", account_id=acc)  # future, excluded
        _seed_tx(db, uid, 2026, 9, 30, "777")                   # NULL-account, excluded
        db.close()

        data = _improved(client, user_a_auth, "2026-10", account_id=acc).json()
        # Only Oct 1 + Oct 4 count: Sept 30 is history, Oct 20 is future.
        assert Decimal(str(data["actual_spend"])) == Decimal("30")
        assert data["num_transactions"] == 2
        assert data["months_of_history"] == 1  # 2026-09 history for this account
