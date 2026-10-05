"""Phase 4E: account-aware financial health (backend only).

GET /api/health accepts an optional ``account_id``. When supplied, every
transaction-derived metric (income, expenses, savings rate, budget adherence,
income stability, spending consistency) is computed from that account's
transactions only; NULL-account rows are excluded. Foreign/nonexistent
accounts return 404. Omitting ``account_id`` preserves the existing
health-score formula, weights, thresholds, and recommendations exactly.
"""
import pytest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, Account, Transaction, BudgetGoal
from app.services.health_score import calculate_health_score

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


def _txn(db, uid, yr, mo, amount, tx_type, account_id=None, cat="Food"):
    t = Transaction(
        user_id=uid,
        date=date(yr, mo, 15),
        description="Seed",
        amount=Decimal(str(amount)),
        transaction_type=tx_type,
        category=cat,
        account_id=account_id,
    )
    db.add(t)
    db.commit()
    return t


def _month(db, uid, yr, mo, income, expense, account_id=None, expense_cat="Food"):
    if income:
        _txn(db, uid, yr, mo, income, "credit", account_id=account_id, cat="Salary/Income")
    if expense:
        _txn(db, uid, yr, mo, expense, "debit", account_id=account_id, cat=expense_cat)


def _health(client, auth, account_id=None):
    if account_id is None:
        return client.get("/api/health", headers=auth)
    return client.get(f"/api/health?account_id={account_id}", headers=auth)


def _rate(data, component="savings_rate"):
    return Decimal(str(data["components"][component]["raw_value"]))


def _score(data, component="savings_rate"):
    return Decimal(str(data["components"][component]["score"]))


class TestAccountAwareHealth:
    def test_existing_behavior_without_account_id(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        for mo in (7, 8, 9):
            _month(db, uid, 2026, mo, 50000, 15000)  # NULL-account txns
        db.close()

        res = _health(client, user_a_auth)
        assert res.status_code == 200
        data = res.json()
        assert data["insufficient_data"] is False
        assert data["months_analyzed"] == 3
        assert _rate(data) == Decimal("70.00")   # (150000-45000)/150000
        assert "formula" in data
        assert set(data["components"].keys()) == {
            "savings_rate", "budget_adherence", "income_stability", "spending_consistency"
        }

        # Service: omitted account_id and explicit None are identical.
        db = TestingSessionLocal()
        omitted = calculate_health_score(db, uid)
        explicit_none = calculate_health_score(db, uid, account_id=None)
        assert omitted == explicit_none
        db.close()

    def test_account_filtered_health(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        acc_b = _add_account(db, uid, "B")
        _month(db, uid, 2026, 8, 10000, 8000, account_id=acc_a)
        _month(db, uid, 2026, 9, 10000, 8000, account_id=acc_a)
        _month(db, uid, 2026, 8, 40000, 1000, account_id=acc_b)
        _month(db, uid, 2026, 9, 40000, 1000, account_id=acc_b)
        _month(db, uid, 2026, 7, 7000, 7000)     # NULL account
        _month(db, uid, 2026, 9, 99999, 99999)   # NULL account
        db.close()

        filtered = _health(client, user_a_auth, account_id=acc_a).json()
        unfiltered = _health(client, user_a_auth).json()

        assert filtered["months_analyzed"] == 2
        assert _rate(filtered) == Decimal("20.00")     # (20000-16000)/20000
        assert unfiltered["months_analyzed"] == 3
        assert _rate(unfiltered) == Decimal("39.61")   # NULL + B rows included
        assert _rate(filtered) != _rate(unfiltered)
        assert filtered["insufficient_data"] is False

    def test_income_filtering(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        acc_b = _add_account(db, uid, "B")
        # A: steady income. B: wildly varying income (expenses identical).
        _month(db, uid, 2026, 8, 10000, 5000, account_id=acc_a)
        _month(db, uid, 2026, 9, 10000, 5000, account_id=acc_a)
        _month(db, uid, 2026, 8, 1000000, 5000, account_id=acc_b)
        _month(db, uid, 2026, 9, 1000, 5000, account_id=acc_b)
        db.close()

        filtered = _health(client, user_a_auth, account_id=acc_a).json()
        unfiltered = _health(client, user_a_auth).json()

        # Income stability is computed from A's income only: perfect stability.
        assert _rate(filtered, "income_stability") == Decimal("100.00")
        assert _rate(unfiltered, "income_stability") < Decimal("100.00")
        # Savings rate uses A's income only (B's 1M income excluded).
        assert _rate(filtered) == Decimal("50.00")     # (20000-10000)/20000
        assert _rate(filtered) != _rate(unfiltered)
        # Expenses are identical across accounts, so this stays at 100 everywhere:
        # the difference above comes from income filtering alone.
        assert _rate(filtered, "spending_consistency") == Decimal("100.00")
        assert _rate(unfiltered, "spending_consistency") == Decimal("100.00")

    def test_expense_filtering(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        acc_b = _add_account(db, uid, "B")
        budget = BudgetGoal(user_id=uid, category="Food", monthly_cap=Decimal("6000"))
        db.add(budget)
        db.commit()
        # A: steady spending within budget. B: erratic spending over budget.
        _month(db, uid, 2026, 8, 10000, 5000, account_id=acc_a)
        _month(db, uid, 2026, 9, 10000, 5000, account_id=acc_a)
        _month(db, uid, 2026, 8, 10000, 999999, account_id=acc_b)
        _month(db, uid, 2026, 9, 10000, 50000, account_id=acc_b)
        db.close()

        filtered = _health(client, user_a_auth, account_id=acc_a).json()
        unfiltered = _health(client, user_a_auth).json()

        # Spending consistency from A's expenses only: perfect consistency.
        assert _rate(filtered, "spending_consistency") == Decimal("100.00")
        assert _rate(unfiltered, "spending_consistency") < Decimal("100.00")
        # Budget adherence compares A's spend against the cap, not B's.
        assert _rate(filtered, "budget_adherence") == Decimal("100")
        assert _rate(unfiltered, "budget_adherence") == Decimal("0")
        # Income identical across accounts -> stability unaffected by filtering.
        assert _rate(filtered, "income_stability") == Decimal("100.00")

    def test_savings_rate_filtering(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        acc_b = _add_account(db, uid, "B")
        _month(db, uid, 2026, 8, 10000, 8000, account_id=acc_a)
        _month(db, uid, 2026, 9, 10000, 8000, account_id=acc_a)
        _month(db, uid, 2026, 8, 10000, 5000, account_id=acc_b)
        _month(db, uid, 2026, 9, 10000, 5000, account_id=acc_b)
        db.close()

        data_a = _health(client, user_a_auth, account_id=acc_a).json()
        data_b = _health(client, user_a_auth, account_id=acc_b).json()
        data_all = _health(client, user_a_auth).json()

        assert _rate(data_a) == Decimal("20.00")    # (20000-16000)/20000
        assert _score(data_a) == Decimal("75")      # 20% -> 75 boundary
        assert _rate(data_b) == Decimal("50.00")    # (20000-10000)/20000
        assert _score(data_b) == Decimal("100")
        assert _rate(data_all) == Decimal("35.00")  # (40000-26000)/40000

    def test_foreign_account_returns_404(self, client, user_a_auth, user_b_auth):
        uid_b = _user_id(user_b_auth)
        db = TestingSessionLocal()
        foreign = _add_account(db, uid_b, "User B account")
        db.close()

        own = _health(client, user_b_auth, account_id=foreign)
        assert own.status_code == 200

        stolen = _health(client, user_a_auth, account_id=foreign)
        assert stolen.status_code == 404
        assert stolen.json()["detail"] == "Account not found."

    def test_nonexistent_account_returns_404(self, client, user_a_auth):
        resp = _health(client, user_a_auth, account_id=999999)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Account not found."

    def test_null_account_transactions_excluded(self, client, user_a_auth, user_b_auth):
        uid_a = _user_id(user_a_auth)
        uid_b = _user_id(user_b_auth)
        db = TestingSessionLocal()
        acc = _add_account(db, uid_a, "Scoped")
        _month(db, uid_a, 2026, 8, 10000, 8000, account_id=acc)
        _month(db, uid_a, 2026, 9, 10000, 8000, account_id=acc)
        _month(db, uid_a, 2026, 9, 50000, 50000)  # NULL account, same month

        # Reference user with only the equivalent on-account data, nothing NULL.
        _month(db, uid_b, 2026, 8, 10000, 8000)
        _month(db, uid_b, 2026, 9, 10000, 8000)
        db.close()

        filtered = _health(client, user_a_auth, account_id=acc).json()
        unfiltered = _health(client, user_a_auth).json()
        reference = _health(client, user_b_auth).json()

        assert _rate(filtered) == Decimal("20.00")
        assert _rate(unfiltered) == Decimal("5.71")  # (70000-66000)/70000 includes NULL
        assert _rate(unfiltered) != _rate(filtered)
        # Filtered result matches a user who has no NULL-account rows at all.
        assert _rate(filtered) == _rate(reference)
        assert filtered["overall_score"] == reference["overall_score"]
        assert filtered["months_analyzed"] == reference["months_analyzed"]

    def test_multiple_accounts(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        acc_b = _add_account(db, uid, "B")
        _month(db, uid, 2026, 8, 10000, 8000, account_id=acc_a)
        _month(db, uid, 2026, 9, 10000, 8000, account_id=acc_a)
        _month(db, uid, 2026, 8, 10000, 10000, account_id=acc_b)
        _month(db, uid, 2026, 9, 10000, 10000, account_id=acc_b)
        db.close()

        data_a = _health(client, user_a_auth, account_id=acc_a).json()
        data_b = _health(client, user_a_auth, account_id=acc_b).json()
        data_all = _health(client, user_a_auth).json()

        assert _rate(data_a) == Decimal("20.00")
        assert _rate(data_b) == Decimal("0.00")
        assert _rate(data_all) == Decimal("10.00")
        assert data_a["overall_score"] != data_b["overall_score"]
        assert data_a["overall_score"] != data_all["overall_score"]
        assert data_b["overall_score"] != data_all["overall_score"]

    def test_insufficient_data_for_empty_and_single_month_account(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_empty = _add_account(db, uid, "Empty")
        acc_single = _add_account(db, uid, "Single")
        _month(db, uid, 2026, 8, 10000, 8000, account_id=acc_single)
        _month(db, uid, 2026, 9, 10000, 8000, account_id=acc_single)
        _month(db, uid, 2026, 7, 30000, 9000)  # scored for the unfiltered case
        db.close()

        empty = _health(client, user_a_auth, account_id=acc_empty).json()
        assert empty["insufficient_data"] is True
        assert empty["overall_score"] is None
        assert empty["months_analyzed"] == 0

        # Only one month on this account -> still insufficient (< 2 months).
        single_month_acc = acc_single
        db = TestingSessionLocal()
        db.query(Transaction).filter(
            Transaction.account_id == single_month_acc,
            Transaction.date >= date(2026, 9, 1),
            Transaction.date <= date(2026, 9, 30),
        ).delete()
        db.commit()
        db.close()
        single = _health(client, user_a_auth, account_id=single_month_acc).json()
        assert single["insufficient_data"] is True
        assert single["overall_score"] is None
        assert single["months_analyzed"] == 1

        # Unfiltered view still has enough data from the NULL-account rows.
        unfiltered = _health(client, user_a_auth).json()
        assert unfiltered["insufficient_data"] is False

    def test_formula_and_score_unchanged(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc = _add_account(db, uid, "A")
        _month(db, uid, 2026, 8, 10000, 9000, account_id=acc)
        _month(db, uid, 2026, 9, 10000, 9000, account_id=acc)
        db.close()

        filtered = _health(client, user_a_auth, account_id=acc).json()
        unfiltered = _health(client, user_a_auth).json()

        # Piecewise boundary unchanged: 10% savings rate -> score 50.
        assert _rate(filtered) == Decimal("10.00")
        assert _score(filtered) == Decimal("50")
        # Weighted average with redistributed budget weight unchanged:
        # (50*0.40 + 100*0.20 + 100*0.15) / 0.75 = 73.33
        assert Decimal(str(filtered["overall_score"])) == Decimal("73.33")

        # Formula strings / base weights are untouched. Without budgets the
        # 25% budget weight is redistributed to the remaining components.
        formula = filtered["formula"]
        assert formula["weights"] == (
            "savings=53.33%, budget=25%, income_stability=26.67%, spending_consistency=20.00%"
        )
        assert formula["savings_rate_score"] == (
            "piecewise_linear: 0%->0, 5%->25, 10%->50, 20%->75, 30%+->100"
        )
        assert formula["overall"] == (
            "weighted_average(score_savings * w_savings + score_budget * w_budget"
            " + score_income * w_income + score_spending * w_spending) / sum(active_weights)"
        )
        assert filtered["components"]["budget_adherence"]["weight"] == "0% (no budgets)"

        # All data lives on one account, so filtered and unfiltered are identical.
        assert filtered == unfiltered

        # Service level: identical dict whether account_id is omitted or given.
        db = TestingSessionLocal()
        omitted = calculate_health_score(db, uid)
        given = calculate_health_score(db, uid, account_id=acc)
        assert omitted == given

        # With a budget in place the 0.25 budget weight is intact: base weights
        # show through unchanged and the weighted average uses them.
        db.add(BudgetGoal(user_id=uid, category="Food", monthly_cap=Decimal("9000")))
        db.commit()
        db.close()

        with_budget = _health(client, user_a_auth, account_id=acc).json()
        assert _rate(with_budget, "budget_adherence") == Decimal("100")
        assert Decimal(str(with_budget["overall_score"])) == Decimal("80.00")
        # 50*0.40 + 100*0.25 + 100*0.20 + 100*0.15 = 80
        assert with_budget["formula"]["weights"] == (
            "savings=40.00%, budget=25.00%, income_stability=20.00%, spending_consistency=15.00%"
        )
        assert with_budget["components"]["budget_adherence"]["weight"] == "25.00%"
