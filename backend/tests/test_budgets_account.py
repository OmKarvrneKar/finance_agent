"""Phase 5D-5: account-scoped budget spending.

GET /budgets accepts an optional ``account_id``. Budget caps and goal
definitions stay user-level; only the current-spend calculation is filtered
to the given account (NULL-account rows excluded). Foreign and nonexistent
accounts return 404. Omitting the parameter preserves the existing
all-account behavior. Thresholds and formulas are unchanged.
"""
import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.database.db import Base, get_db, Transaction, BudgetGoal, User

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


def _add_account(db, user_id, name, account_type="bank"):
    from app.database.db import Account
    account = Account(user_id=user_id, name=name, account_type=account_type)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account.id


def _tx(db, uid, description, amount, category, tx_date, account_id=None):
    db.add(Transaction(
        user_id=uid,
        date=tx_date,
        description=description,
        amount=Decimal(str(amount)),
        transaction_type="debit",
        category=category,
        account_id=account_id,
    ))
    db.commit()


MONTH = "2026-09"


def _seed(db, uid):
    """September 2026. Budgets user-level: Food cap 1000, Housing cap 2500.
    Food: A 800+100, B 300, NULL 200 -> unfiltered 1400, A 900, B 300.
    Housing: B 2100 only.
    """
    db.add(BudgetGoal(user_id=uid, category="Food", monthly_cap=Decimal("1000.00")))
    db.add(BudgetGoal(user_id=uid, category="Housing", monthly_cap=Decimal("2500.00")))
    db.commit()

    acc_a = _add_account(db, uid, "A")
    acc_b = _add_account(db, uid, "B")

    _tx(db, uid, "Grocery Store", 800, "Food", date(2026, 9, 10), acc_a)
    _tx(db, uid, "Cafe", 100, "Food", date(2026, 9, 20), acc_a)
    _tx(db, uid, "Diner", 300, "Food", date(2026, 9, 5), acc_b)
    _tx(db, uid, "Landlord", 2100, "Housing", date(2026, 9, 1), acc_b)
    _tx(db, uid, "Mystery", 200, "Food", date(2026, 9, 12), None)
    return acc_a, acc_b


def _get(client, auth, **params):
    return client.get("/api/budgets", params={"month": MONTH, **params}, headers=auth)


def _by_category(budgets):
    return {b["category"]: b for b in budgets}


def _d(value):
    return Decimal(str(value))


class TestBudgetsAccountFilter:
    def test_unfiltered_behavior_preserved(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        _seed(db, uid)
        db.close()

        res = _get(client, user_a_auth)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2

        food = _by_category(data)["Food"]
        assert _d(food["monthly_cap"]) == _d("1000")
        assert _d(food["current_spend"]) == _d("1400")  # A 900 + B 300 + NULL 200
        assert _d(food["percent_used"]) == _d("140")
        assert food["status"] == "over"
        assert food["message"] == "You are over your Food budget by ₹400.00."

        housing = _by_category(data)["Housing"]
        assert _d(housing["monthly_cap"]) == _d("2500")
        assert _d(housing["current_spend"]) == _d("2100")
        assert _d(housing["percent_used"]) == _d("84")
        assert housing["status"] == "approaching"  # 2100 >= 0.8 * 2500
        assert housing["days_left_in_month"] == 0  # 2026-09 is a past month

    def test_account_a_scoped(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a, _ = _seed(db, uid)
        db.close()

        res = _get(client, user_a_auth, account_id=acc_a)
        assert res.status_code == 200
        data = _by_category(res.json())

        food = data["Food"]
        assert _d(food["current_spend"]) == _d("900")  # 800 + 100; NULL/B excluded
        assert _d(food["percent_used"]) == _d("90")
        assert food["status"] == "approaching"  # 900 >= 0.8 * 1000
        assert food["message"] == "You are approaching your Food budget (90.0% used)."

        # Caps stay user-level in a scoped view.
        assert _d(food["monthly_cap"]) == _d("1000")

        housing = data["Housing"]
        assert _d(housing["current_spend"]) == _d("0")  # Housing lives on B only
        assert _d(housing["percent_used"]) == _d("0")
        assert housing["status"] == "on_track"
        assert _d(housing["monthly_cap"]) == _d("2500")

    def test_account_b_scoped(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        _, acc_b = _seed(db, uid)
        db.close()

        res = _get(client, user_a_auth, account_id=acc_b)
        assert res.status_code == 200
        data = _by_category(res.json())

        food = data["Food"]
        assert _d(food["current_spend"]) == _d("300")  # Diner only; A and NULL excluded
        assert _d(food["percent_used"]) == _d("30")
        assert food["status"] == "on_track"

        housing = data["Housing"]
        assert _d(housing["current_spend"]) == _d("2100")
        assert _d(housing["percent_used"]) == _d("84")
        assert housing["status"] == "approaching"
        assert _d(housing["monthly_cap"]) == _d("2500")  # still the user-level cap

    def test_null_account_transactions_excluded_when_scoped(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a, acc_b = _seed(db, uid)
        db.close()

        unfiltered = _by_category(_get(client, user_a_auth).json())["Food"]
        a = _by_category(_get(client, user_a_auth, account_id=acc_a).json())["Food"]
        b = _by_category(_get(client, user_a_auth, account_id=acc_b).json())["Food"]

        # The NULL-account 200 is visible unfiltered...
        assert _d(unfiltered["current_spend"]) == _d("1400")
        # ...and never leaks into a scoped view: A + B = 1200, not 1400.
        assert _d(a["current_spend"]) == _d("900")
        assert _d(b["current_spend"]) == _d("300")
        assert _d(a["current_spend"]) + _d(b["current_spend"]) == _d("1200")
        assert _d(unfiltered["current_spend"]) != _d(a["current_spend"]) + _d(b["current_spend"])

    def test_foreign_account_returns_404(self, client, user_a_auth, user_b_auth):
        uid_b = _user_id(user_b_auth)
        db = TestingSessionLocal()
        foreign = _add_account(db, uid_b, "User B account")
        db.close()

        res = _get(client, user_a_auth, account_id=foreign)
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."

    def test_nonexistent_account_returns_404(self, client, user_a_auth):
        res = _get(client, user_a_auth, account_id=999999)
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."

    def test_user_isolation(self, client, user_a_auth, user_b_auth):
        uid_a = _user_id(user_a_auth)
        uid_b = _user_id(user_b_auth)
        db = TestingSessionLocal()
        acc_a, _ = _seed(db, uid_a)

        # User B: own Food budget cap 500; 400 spent in September on own account.
        db.add(BudgetGoal(user_id=uid_b, category="Food", monthly_cap=Decimal("500.00")))
        db.commit()
        own = _add_account(db, uid_b, "B-only")
        _tx(db, uid_b, "Store2", 400, "Food", date(2026, 9, 12), own)
        db.close()

        first_a = _by_category(_get(client, user_a_auth, account_id=acc_a).json())
        first_all = _by_category(_get(client, user_a_auth).json())
        second = _by_category(_get(client, user_b_auth).json())

        # User A unchanged by user B's budget or transactions.
        assert _d(first_a["Food"]["current_spend"]) == _d("900")
        assert _d(first_all["Food"]["current_spend"]) == _d("1400")
        assert len(first_all) == 2

        # User B sees only their own budget and spend (400 >= 0.8 * 500).
        food_b = second["Food"]
        assert _d(food_b["monthly_cap"]) == _d("500")
        assert _d(food_b["current_spend"]) == _d("400")
        assert _d(food_b["percent_used"]) == _d("80")
        assert food_b["status"] == "approaching"
        assert "Housing" not in second  # user A's budget is invisible

        # User A's account ids are invisible to user B.
        stolen = _get(client, user_b_auth, account_id=acc_a)
        assert stolen.status_code == 404
        assert stolen.json()["detail"] == "Account not found."
