"""Phase 5D-2: mixed-scope budget adherence in financial health.

Budget caps are user-level, so budget adherence always compares user-level
spending across ALL accounts against those caps, regardless of which
account is selected. Income, expenses, savings rate, income stability and
spending consistency remain account-scoped when account_id is provided.
The tests pin exact expected scores for the unfiltered, account-selected
and cross-user cases.
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
def user_auth(client):
    token = _register_and_login(client, "scope1@test.com", "Pass123456789", "Scope User")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_auth(client):
    token = _register_and_login(client, "scope2@test.com", "Pass123456789", "Other User")
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


def _month(db, uid, yr, mo, income, expense, account_id=None, expense_cat="Food"):
    if income:
        db.add(Transaction(
            user_id=uid, date=date(yr, mo, 15), description="Seed income",
            amount=Decimal(str(income)), transaction_type="credit",
            category="Salary/Income", account_id=account_id,
        ))
    if expense:
        db.add(Transaction(
            user_id=uid, date=date(yr, mo, 15), description="Seed expense",
            amount=Decimal(str(expense)), transaction_type="debit",
            category=expense_cat, account_id=account_id,
        ))
    db.commit()


def _budget(db, uid, category, cap):
    db.add(BudgetGoal(user_id=uid, category=category, monthly_cap=Decimal(str(cap))))
    db.commit()


def _health(client, auth, account_id=None):
    if account_id is None:
        return client.get("/api/health", headers=auth)
    return client.get(f"/api/health?account_id={account_id}", headers=auth)


def _rate(data, component):
    return Decimal(str(data["components"][component]["raw_value"]))


def _score(data, component):
    return Decimal(str(data["components"][component]["score"]))


def _overall(data):
    return Decimal(str(data["overall_score"]))


def _seed_two_accounts(db, uid):
    """A: income 600 / Food 500 per month. B: income 400 / Transport 300.

    Budgets: Food cap 600 (A's 500 is under), Transport cap 150 (B's 300 is
    over). User-level adherence for the latest month is therefore 1/2 = 50%
    in every view; an account-scoped adherence would wrongly report 100%
    when only account A is selected.
    """
    acc_a = _add_account(db, uid, "A")
    acc_b = _add_account(db, uid, "B")
    _month(db, uid, 2026, 8, 600, 500, account_id=acc_a, expense_cat="Food")
    _month(db, uid, 2026, 9, 600, 500, account_id=acc_a, expense_cat="Food")
    _month(db, uid, 2026, 8, 400, 300, account_id=acc_b, expense_cat="Transport")
    _month(db, uid, 2026, 9, 400, 300, account_id=acc_b, expense_cat="Transport")
    _budget(db, uid, "Food", 600)
    _budget(db, uid, "Transport", 150)
    return acc_a, acc_b


class TestBudgetAdherenceIsUserLevel:
    def test_unfiltered_adherence_and_exact_score(self, client, user_auth):
        uid = _user_id(user_auth)
        db = TestingSessionLocal()
        _seed_two_accounts(db, uid)
        db.close()

        data = _health(client, user_auth).json()

        # Food 500 <= 600 on track; Transport 300 > 150 over -> 1 of 2.
        assert _rate(data, "budget_adherence") == Decimal("50")
        assert _score(data, "budget_adherence") == Decimal("50.00")
        assert data["components"]["budget_adherence"]["weight"] == "25.00%"
        # savings (2000-1600)/2000 = 20% -> 75; income/spending stable at 100.
        assert _rate(data, "savings_rate") == Decimal("20.00")
        assert _score(data, "savings_rate") == Decimal("75")
        assert _rate(data, "income_stability") == Decimal("100.00")
        assert _rate(data, "spending_consistency") == Decimal("100.00")
        # 75*0.40 + 50*0.25 + 100*0.20 + 100*0.15 = 77.50
        assert _overall(data) == Decimal("77.5")
        assert data["months_analyzed"] == 2
        assert data["insufficient_data"] is False

    def test_account_scoped_adherence_is_user_level_with_exact_scores(self, client, user_auth):
        uid = _user_id(user_auth)
        db = TestingSessionLocal()
        acc_a, acc_b = _seed_two_accounts(db, uid)
        db.close()

        data_a = _health(client, user_auth, account_id=acc_a).json()
        data_b = _health(client, user_auth, account_id=acc_b).json()
        data_all = _health(client, user_auth).json()

        # The core regression: adherence stays user-level under ANY account
        # selection (an account-scoped implementation would report 100% for
        # A, because B's over-budget Transport spend would be invisible).
        assert _rate(data_a, "budget_adherence") == Decimal("50")
        assert _rate(data_b, "budget_adherence") == Decimal("50")
        assert _rate(data_all, "budget_adherence") == Decimal("50")
        assert _rate(data_a, "budget_adherence") == _rate(data_all, "budget_adherence")
        assert _rate(data_b, "budget_adherence") == _rate(data_all, "budget_adherence")

        # Account A: savings (1200-1000)/1200 = 16.67% -> score 66.675.
        assert _rate(data_a, "savings_rate") == Decimal("16.67")
        assert _score(data_a, "savings_rate") == Decimal("66.675")
        # 66.675*0.40 + 50*0.25 + 100*0.20 + 100*0.15 = 74.17
        assert _overall(data_a) == Decimal("74.17")
        assert data_a["months_analyzed"] == 2
        assert data_a["insufficient_data"] is False

        # Account B: savings (800-600)/800 = 25% -> score 87.5.
        assert _rate(data_b, "savings_rate") == Decimal("25.00")
        assert _score(data_b, "savings_rate") == Decimal("87.5")
        # 87.5*0.40 + 50*0.25 + 100*0.20 + 100*0.15 = 82.50
        assert _overall(data_b) == Decimal("82.5")
        assert data_b["months_analyzed"] == 2

        # All four components scored -> base weights intact, no redistribution.
        assert data_a["formula"]["weights"] == (
            "savings=40.00%, budget=25.00%, income_stability=20.00%, spending_consistency=15.00%"
        )

    def test_transaction_derived_metrics_stay_account_scoped(self, client, user_auth):
        uid = _user_id(user_auth)
        db = TestingSessionLocal()
        acc_a, acc_b = _seed_two_accounts(db, uid)
        db.close()

        data_a = _health(client, user_auth, account_id=acc_a).json()
        data_b = _health(client, user_auth, account_id=acc_b).json()
        data_all = _health(client, user_auth).json()

        # Savings rates differ per scope: income/expense metrics stay filtered.
        assert _rate(data_a, "savings_rate") == Decimal("16.67")
        assert _rate(data_b, "savings_rate") == Decimal("25.00")
        assert _rate(data_all, "savings_rate") == Decimal("20.00")
        # Within each scope income and expenses are constant -> perfect
        # stability/consistency, computed from that scope's transactions only.
        assert _rate(data_a, "income_stability") == Decimal("100.00")
        assert _rate(data_b, "income_stability") == Decimal("100.00")
        assert _rate(data_all, "income_stability") == Decimal("100.00")
        assert _rate(data_a, "spending_consistency") == Decimal("100.00")
        assert _rate(data_b, "spending_consistency") == Decimal("100.00")
        assert _rate(data_all, "spending_consistency") == Decimal("100.00")
        assert _overall(data_a) != _overall(data_all)
        assert _overall(data_b) != _overall(data_all)

    def test_no_budgets_adherence_null_in_both_views(self, client, user_auth):
        uid = _user_id(user_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        _month(db, uid, 2026, 8, 600, 500, account_id=acc_a, expense_cat="Food")
        _month(db, uid, 2026, 9, 600, 500, account_id=acc_a, expense_cat="Food")
        db.close()

        filtered = _health(client, user_auth, account_id=acc_a).json()
        unfiltered = _health(client, user_auth).json()

        for data in (filtered, unfiltered):
            assert data["components"]["budget_adherence"]["score"] is None
            assert data["components"]["budget_adherence"]["raw_value"] is None
            assert data["components"]["budget_adherence"]["weight"] == "0% (no budgets)"

        # Without the budget weight the remaining weights sum to 0.75 and are
        # redistributed: (66.675*0.40 + 100*0.20 + 100*0.15) / 0.75 = 82.23
        assert _overall(filtered) == Decimal("82.23")
        assert filtered == unfiltered


class TestUserIsolation:
    def test_budget_adherence_uses_only_the_requesting_users_data(self, client, user_auth, other_auth):
        uid = _user_id(user_auth)
        db = TestingSessionLocal()
        acc_a, acc_b = _seed_two_accounts(db, uid)
        db.close()

        # Second user: one account, Food 100 per month, cap 200 -> 100% on track.
        uid_other = _user_id(other_auth)
        db = TestingSessionLocal()
        acc_other = _add_account(db, uid_other, "OtherA")
        _month(db, uid_other, 2026, 8, 1000, 100, account_id=acc_other, expense_cat="Food")
        _month(db, uid_other, 2026, 9, 1000, 100, account_id=acc_other, expense_cat="Food")
        _budget(db, uid_other, "Food", 200)
        db.close()

        first = _health(client, user_auth).json()
        first_a = _health(client, user_auth, account_id=acc_a).json()
        second = _health(client, other_auth).json()

        # User 1 is unaffected by user 2's transactions and budgets.
        assert _rate(first, "budget_adherence") == Decimal("50")
        assert _overall(first) == Decimal("77.5")
        assert _rate(first_a, "budget_adherence") == Decimal("50")
        assert _overall(first_a) == Decimal("74.17")

        # User 2 sees only their own spend and budget: Food 100 <= 200.
        assert _rate(second, "budget_adherence") == Decimal("100")
        # savings (2000-200)/2000 = 90% -> 100; all components 100.
        assert _rate(second, "savings_rate") == Decimal("90.00")
        assert _overall(second) == Decimal("100")
        assert second["months_analyzed"] == 2
