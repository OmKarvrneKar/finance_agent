"""Phase 5D-3: account-scoped recurring bills calendar and subscriptions.

GET /recurring/calendar and GET /subscriptions accept an optional
``account_id``. When supplied, every historical query used to derive bills
or subscriptions (grouping, averages, frequency, last seen) is filtered to
that account and NULL-account transactions are excluded; 404 is returned
for foreign/nonexistent accounts. Omitting the parameter preserves the
existing all-account behavior exactly.
"""
import pytest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, Transaction, User, Account

engine = create_engine(
    'sqlite:///:memory:',
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

WINDOW = {"start_date": "2026-09-20", "end_date": "2026-10-31"}


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
    account = Account(user_id=user_id, name=name, account_type=account_type)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account.id


def _tx(db, uid, description, amount, tx_date, account_id=None,
        recurring=True, confirmed=False, tx_type="debit", category="Subscriptions"):
    db.add(Transaction(
        user_id=uid,
        date=tx_date,
        description=description,
        amount=Decimal(str(amount)),
        transaction_type=tx_type,
        category=category,
        is_recurring=recurring,
        is_user_confirmed_recurring=confirmed,
        account_id=account_id,
    ))
    db.commit()


def _seed(db, uid):
    """Shared fixture data across three accounts (A, B, NULL).

    - acc_a: Netflix 15.99 monthly (Aug confirmed + Sep), a NON-recurring
      one-off debit, and a recurring CREDIT (must never appear).
    - acc_b: Netflix 19.99 monthly + Spotify 9.99 monthly.
    - NULL account: Gym 40 monthly.
    """
    acc_a = _add_account(db, uid, "A")
    acc_b = _add_account(db, uid, "B")
    _tx(db, uid, "Netflix", 15.99, date(2026, 8, 1), acc_a, confirmed=True)
    _tx(db, uid, "Netflix", 15.99, date(2026, 9, 1), acc_a)
    _tx(db, uid, "One-off Purchase", 999, date(2026, 9, 5), acc_a, recurring=False, category="Shopping")
    _tx(db, uid, "Salary", 5000, date(2026, 8, 31), acc_a, tx_type="credit", category="Income")
    _tx(db, uid, "Salary", 5000, date(2026, 9, 30), acc_a, tx_type="credit", category="Income")
    _tx(db, uid, "Netflix", 19.99, date(2026, 8, 1), acc_b)
    _tx(db, uid, "Netflix", 19.99, date(2026, 9, 1), acc_b)
    _tx(db, uid, "Spotify", 9.99, date(2026, 8, 15), acc_b)
    _tx(db, uid, "Spotify", 9.99, date(2026, 9, 15), acc_b)
    _tx(db, uid, "Gym", 40, date(2026, 8, 10), None)
    _tx(db, uid, "Gym", 40, date(2026, 9, 10), None)
    return acc_a, acc_b


def _cal(client, auth, account_id=None, **extra):
    params = {**WINDOW, **extra}
    if account_id is not None:
        params["account_id"] = account_id
    return client.get("/api/recurring/calendar", params=params, headers=auth)


def _subs(client, auth, account_id=None):
    params = {}
    if account_id is not None:
        params["account_id"] = account_id
    return client.get("/api/subscriptions", params=params, headers=auth)


def _bill(data, description):
    for bill in data["bills"]:
        if bill["description"] == description:
            return bill
    return None


def _sub(data, description):
    for sub in data:
        if sub["description"] == description:
            return sub
    return None


def _d(value):
    return Decimal(str(value))


class TestRecurringCalendarAccountFilter:
    def test_unfiltered_includes_all_accounts_and_null(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        _seed(db, uid)
        db.close()

        res = _cal(client, user_a_auth)
        assert res.status_code == 200
        data = res.json()

        assert data["count"] == 3
        # Sorted by projected date: Netflix 2026-09-29, Gym 2026-10-10, Spotify 2026-10-15.
        assert [b["description"] for b in data["bills"]] == ["Netflix", "Gym", "Spotify"]
        assert _d(data["total_expected_amount"]) == _d("67.98")  # 17.99 + 40 + 9.99

        netflix = _bill(data, "Netflix")
        # Avg over ALL accounts (15.99*2 + 19.99*2)/4; four hits over two
        # months -> 10.33d average gap -> Bi-weekly, next step 2026-09-29.
        assert _d(netflix["expected_amount"]) == _d("17.99")
        assert netflix["occurrences"] == 4
        assert netflix["frequency"] == "Bi-weekly"
        assert netflix["expected_date"] == "2026-09-29"
        assert netflix["is_user_confirmed"] is True  # A's Aug charge confirmed
        # Non-recurring and credit rows never appear (existing behavior).
        assert _bill(data, "One-off Purchase") is None
        assert _bill(data, "Salary") is None

    def test_account_scope_excludes_other_and_null_accounts(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a, _ = _seed(db, uid)
        db.close()

        res = _cal(client, user_a_auth, account_id=acc_a)
        assert res.status_code == 200
        data = res.json()

        # Only A's Netflix: B's Spotify/Netflix and the NULL-account Gym are gone.
        assert data["count"] == 1
        assert [b["description"] for b in data["bills"]] == ["Netflix"]
        assert _d(data["total_expected_amount"]) == _d("15.99")

        netflix = _bill(data, "Netflix")
        # History scoped to A: avg 15.99 (not 17.99), 2 hits, monthly
        # projection from A's last_seen 2026-09-01 -> 2026-10-01.
        assert _d(netflix["expected_amount"]) == _d("15.99")
        assert netflix["occurrences"] == 2
        assert netflix["frequency"] == "Monthly"
        assert netflix["expected_date"] == "2026-10-01"
        assert netflix["last_seen"] == "2026-09-01"
        assert netflix["is_user_confirmed"] is True
        assert _bill(data, "Gym") is None
        assert _bill(data, "One-off Purchase") is None
        assert _bill(data, "Salary") is None

    def test_account_scope_derives_bills_from_selected_accounts_history(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        _, acc_b = _seed(db, uid)
        db.close()

        data = _cal(client, user_a_auth, account_id=acc_b).json()

        assert data["count"] == 2
        assert [b["description"] for b in data["bills"]] == ["Netflix", "Spotify"]
        assert _d(data["total_expected_amount"]) == _d("29.98")  # 19.99 + 9.99
        # B's own Netflix history is 19.99/charge -> Monthly (not the
        # mixed 17.99 Bi-weekly of the unfiltered view).
        netflix = _bill(data, "Netflix")
        assert _d(netflix["expected_amount"]) == _d("19.99")
        assert netflix["occurrences"] == 2
        assert netflix["frequency"] == "Monthly"
        assert netflix["expected_date"] == "2026-10-01"
        assert _bill(data, "Gym") is None

    def test_foreign_account_returns_404(self, client, user_a_auth, user_b_auth):
        uid_b = _user_id(user_b_auth)
        db = TestingSessionLocal()
        foreign = _add_account(db, uid_b, "User B account")
        db.close()

        res = _cal(client, user_a_auth, account_id=foreign)
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."

    def test_nonexistent_account_returns_404(self, client, user_a_auth):
        res = _cal(client, user_a_auth, account_id=999999)
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."

    def test_user_isolation_with_account_filter(self, client, user_a_auth, user_b_auth):
        uid_a = _user_id(user_a_auth)
        uid_b = _user_id(user_b_auth)
        db = TestingSessionLocal()
        acc_a, _ = _seed(db, uid_a)
        own = _add_account(db, uid_b, "B-only")
        _tx(db, uid_b, "Netflix", 5, date(2026, 8, 20), own)
        _tx(db, uid_b, "Netflix", 5, date(2026, 9, 20), own)
        db.close()

        scoped_a = _cal(client, user_a_auth, account_id=acc_a).json()
        unfiltered_a = _cal(client, user_a_auth).json()
        scoped_b = _cal(client, user_b_auth, account_id=own).json()
        unfiltered_b = _cal(client, user_b_auth).json()

        # User A unchanged by user B's rows (scoped and unfiltered).
        assert scoped_a["count"] == 1
        assert _d(_bill(scoped_a, "Netflix")["expected_amount"]) == _d("15.99")
        assert unfiltered_a["count"] == 3
        assert _d(unfiltered_a["total_expected_amount"]) == _d("67.98")

        # User B sees only their own data.
        assert scoped_b["count"] == 1
        assert _d(_bill(scoped_b, "Netflix")["expected_amount"]) == _d("5")
        assert unfiltered_b["count"] == 1
        assert _d(unfiltered_b["total_expected_amount"]) == _d("5")


class TestSubscriptionsAccountFilter:
    def test_unfiltered_subscriptions_preserved(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        _seed(db, uid)
        db.close()

        res = _subs(client, user_a_auth)
        assert res.status_code == 200
        data = res.json()

        # Sorted by estimated monthly cost descending (existing behavior).
        assert [s["description"] for s in data] == ["Gym", "Netflix", "Spotify"]

        netflix = _sub(data, "Netflix")
        assert netflix["occurrences"] == 4
        assert _d(netflix["average_amount"]) == _d("17.99")
        assert netflix["frequency"] == "Bi-weekly"  # 4 charges / 2 months = 2.0
        assert _d(netflix["estimated_monthly_cost"]) == _d("38.8584")  # 17.99 * 2.16
        assert _d(netflix["estimated_annual_cost"]) == _d("466.3008")
        assert netflix["last_seen"] == "2026-09-01"
        assert netflix["is_user_confirmed"] is True

        gym = _sub(data, "Gym")
        assert gym["occurrences"] == 2
        assert _d(gym["estimated_monthly_cost"]) == _d("40")
        assert gym["frequency"] == "Monthly"

        # Non-recurring and credit rows never appear.
        assert _sub(data, "One-off Purchase") is None
        assert _sub(data, "Salary") is None

    def test_account_scope_excludes_other_and_null_accounts(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a, _ = _seed(db, uid)
        db.close()

        res = _subs(client, user_a_auth, account_id=acc_a)
        assert res.status_code == 200
        data = res.json()

        # Only A's Netflix: no B rows, no NULL-account Gym.
        assert len(data) == 1
        sub = data[0]
        assert sub["description"] == "Netflix"
        assert sub["occurrences"] == 2
        assert _d(sub["average_amount"]) == _d("15.99")  # A's history only
        assert sub["frequency"] == "Monthly"  # 2 charges / 2 months = 1.0
        assert _d(sub["estimated_monthly_cost"]) == _d("15.99")
        assert _d(sub["estimated_annual_cost"]) == _d("191.88")
        assert sub["last_seen"] == "2026-09-01"
        assert sub["is_user_confirmed"] is True

    def test_account_scope_derives_from_selected_accounts_history(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        _, acc_b = _seed(db, uid)
        db.close()

        data = _subs(client, user_a_auth, account_id=acc_b).json()

        assert [s["description"] for s in data] == ["Netflix", "Spotify"]
        netflix = _sub(data, "Netflix")
        assert netflix["occurrences"] == 2
        assert _d(netflix["average_amount"]) == _d("19.99")  # B's history only
        assert netflix["frequency"] == "Monthly"
        assert _d(netflix["estimated_monthly_cost"]) == _d("19.99")
        assert _d(netflix["estimated_annual_cost"]) == _d("239.88")
        # Confirmed flag comes from A's confirmed charge -> absent for B.
        assert netflix["is_user_confirmed"] is False
        spotify = _sub(data, "Spotify")
        assert _d(spotify["estimated_monthly_cost"]) == _d("9.99")

    def test_foreign_and_nonexistent_accounts_return_404(self, client, user_a_auth, user_b_auth):
        uid_b = _user_id(user_b_auth)
        db = TestingSessionLocal()
        foreign = _add_account(db, uid_b, "User B account")
        db.close()

        stolen = _subs(client, user_a_auth, account_id=foreign)
        assert stolen.status_code == 404
        assert stolen.json()["detail"] == "Account not found."

        missing = _subs(client, user_a_auth, account_id=999999)
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Account not found."

    def test_user_isolation_with_account_filter(self, client, user_a_auth, user_b_auth):
        uid_a = _user_id(user_a_auth)
        uid_b = _user_id(user_b_auth)
        db = TestingSessionLocal()
        acc_a, _ = _seed(db, uid_a)
        own = _add_account(db, uid_b, "B-only")
        _tx(db, uid_b, "Netflix", 5, date(2026, 8, 20), own)
        _tx(db, uid_b, "Netflix", 5, date(2026, 9, 20), own)
        db.close()

        scoped_a = _subs(client, user_a_auth, account_id=acc_a).json()
        unfiltered_a = _subs(client, user_a_auth).json()
        scoped_b = _subs(client, user_b_auth, account_id=own).json()

        assert len(scoped_a) == 1
        assert _d(scoped_a[0]["average_amount"]) == _d("15.99")
        assert len(unfiltered_a) == 3
        assert [s["description"] for s in unfiltered_a] == ["Gym", "Netflix", "Spotify"]
        assert len(scoped_b) == 1
        assert _d(scoped_b[0]["average_amount"]) == _d("5")
        # User A's ids are invisible to user B.
        stolen = _subs(client, user_b_auth, account_id=acc_a)
        assert stolen.status_code == 404
