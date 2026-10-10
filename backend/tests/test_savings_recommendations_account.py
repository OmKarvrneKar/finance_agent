"""Phase 5D-4: account-scoped savings recommendations.

GET /savings-recommendations accepts an optional ``account_id``. Both the
monthly-spending and merchant-level queries used to derive recommendations
are filtered to that account (NULL-account rows excluded); foreign and
nonexistent accounts return 404. Omitting the parameter preserves the
existing all-account behavior exactly. Algorithms, thresholds and
explanation logic are unchanged.
"""
import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.database.db import Base, get_db, Transaction, User, Account

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


def _seed(db, uid):
    """A: Food 1200/mo + Dining 300/mo (Coffee Shop x3) + Transport 300/mo.
    B: Housing 2100/mo + Entertainment 500/mo + Dining 400/mo (Bar x2).
    NULL: Entertainment 9999/mo (Casino x1).
    """
    acc_a = _add_account(db, uid, "A")
    acc_b = _add_account(db, uid, "B")

    _tx(db, uid, "Grocery Store", 1200, "Food", date(2026, 8, 10), acc_a)
    _tx(db, uid, "Grocery Store", 1200, "Food", date(2026, 9, 10), acc_a)
    for d in (date(2026, 8, 5), date(2026, 8, 15), date(2026, 8, 25),
              date(2026, 9, 5), date(2026, 9, 15), date(2026, 9, 25)):
        _tx(db, uid, "Coffee Shop", 100, "Dining", d, acc_a)
    _tx(db, uid, "Bus Pass", 300, "Transport", date(2026, 8, 15), acc_a)
    _tx(db, uid, "Bus Pass", 300, "Transport", date(2026, 9, 15), acc_a)

    _tx(db, uid, "Rent", 2100, "Housing", date(2026, 8, 1), acc_b)
    _tx(db, uid, "Rent", 2100, "Housing", date(2026, 9, 1), acc_b)
    _tx(db, uid, "Movie Theater", 500, "Entertainment", date(2026, 8, 5), acc_b)
    _tx(db, uid, "Movie Theater", 500, "Entertainment", date(2026, 9, 5), acc_b)
    for d in (date(2026, 8, 3), date(2026, 8, 17), date(2026, 9, 3), date(2026, 9, 17)):
        _tx(db, uid, "Bar", 200, "Dining", d, acc_b)

    _tx(db, uid, "Casino", 9999, "Entertainment", date(2026, 8, 20), None)
    _tx(db, uid, "Casino", 9999, "Entertainment", date(2026, 9, 20), None)
    return acc_a, acc_b


def _recs(client, auth, account_id=None):
    params = {}
    if account_id is not None:
        params["account_id"] = account_id
    return client.get("/api/savings-recommendations", params=params, headers=auth)


def _find(data, title):
    for rec in data["recommendations"]:
        if rec["title"] == title:
            return rec
    return None


def _d(value):
    return Decimal(str(value))


class TestSavingsRecommendationsAccountFilter:
    def test_unfiltered_behavior_preserved(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        _seed(db, uid)
        db.close()

        res = _recs(client, user_a_auth)
        assert res.status_code == 200
        data = res.json()

        # Entertainment avg (500 + NULL 9999 = 10499) beats the 0.75
        # percentile of the 5-category overall avg 2959.80 -> 2219.85.
        titles = [r["title"] for r in data["recommendations"]]
        assert titles == [
            "Reduce spending on Entertainment",
            "Reduce visits to Coffee Shop",
            "Reduce visits to Bar",
        ]
        cat = _find(data, "Reduce spending on Entertainment")
        assert _d(cat["estimated_monthly_savings"]) == _d("1507.84")   # (10499-2959.80)*0.20
        assert _d(cat["estimated_annual_savings"]) == _d("18094.08")
        assert cat["confidence"] == "medium"
        assert cat["supporting_data"]["category"] == "Entertainment"
        assert cat["supporting_data"]["current_monthly_avg"] == "10499.00"
        assert cat["supporting_data"]["overall_category_avg"] == "2959.80"
        assert cat["supporting_data"]["percent_above_average"] == "254.72"
        assert cat["supporting_data"]["months_analyzed"] == 2

        coffee = _find(data, "Reduce visits to Coffee Shop")
        assert _d(coffee["estimated_monthly_savings"]) == _d("15.00")  # 100 * 0.15
        assert _d(coffee["estimated_annual_savings"]) == _d("180.00")
        assert coffee["supporting_data"]["visit_count"] == 6
        assert coffee["supporting_data"]["monthly_frequency"] == "3.00"
        assert coffee["supporting_data"]["average_per_visit"] == "100.00"

        bar = _find(data, "Reduce visits to Bar")
        assert _d(bar["estimated_monthly_savings"]) == _d("30.00")     # 200 * 0.15
        assert _d(bar["supporting_data"]["visit_count"]) == 4

        assert _d(data["total_estimated_monthly_savings"]) == _d("1552.84")  # 1507.84+15+30
        assert _d(data["total_estimated_annual_savings"]) == _d("18634.08")
        assert data["categories_analyzed"] == 5   # Food, Dining, Transport, Housing, Entertainment
        assert data["merchants_analyzed"] == 7    # incl. NULL-account Casino
        assert data["months_of_data"] == 2

    def test_account_a_scoped_exact_output(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a, _ = _seed(db, uid)
        db.close()

        data = _recs(client, user_a_auth, account_id=acc_a).json()

        # Category avgs: Food 1200, Dining 300, Transport 300 -> overall 600;
        # only Food clears 600*0.75 = 450.
        titles = [r["title"] for r in data["recommendations"]]
        assert titles == ["Reduce spending on Food", "Reduce visits to Coffee Shop"]

        cat = _find(data, "Reduce spending on Food")
        assert _d(cat["estimated_monthly_savings"]) == _d("120.00")    # (1200-600)*0.20
        assert _d(cat["estimated_annual_savings"]) == _d("1440.00")
        assert cat["supporting_data"]["current_monthly_avg"] == "1200.00"
        assert cat["supporting_data"]["overall_category_avg"] == "600.00"
        assert cat["supporting_data"]["percent_above_average"] == "100.00"
        assert cat["supporting_data"]["months_analyzed"] == 2

        coffee = _find(data, "Reduce visits to Coffee Shop")
        assert _d(coffee["estimated_monthly_savings"]) == _d("15.00")
        assert _d(coffee["estimated_annual_savings"]) == _d("180.00")
        assert coffee["supporting_data"]["visit_count"] == 6
        assert coffee["supporting_data"]["monthly_frequency"] == "3.00"

        assert _d(data["total_estimated_monthly_savings"]) == _d("135.00")
        assert _d(data["total_estimated_annual_savings"]) == _d("1620.00")
        assert data["categories_analyzed"] == 3
        assert data["merchants_analyzed"] == 3
        assert data["months_of_data"] == 2

    def test_account_b_scoped_exact_output(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        _, acc_b = _seed(db, uid)
        db.close()

        data = _recs(client, user_a_auth, account_id=acc_b).json()

        # Category avgs: Housing 2100, Entertainment 500, Dining 400 ->
        # overall 1000; only Housing clears 750.
        titles = [r["title"] for r in data["recommendations"]]
        assert titles == ["Reduce spending on Housing", "Reduce visits to Bar"]

        cat = _find(data, "Reduce spending on Housing")
        assert _d(cat["estimated_monthly_savings"]) == _d("220.00")    # (2100-1000)*0.20
        assert _d(cat["estimated_annual_savings"]) == _d("2640.00")
        assert cat["supporting_data"]["current_monthly_avg"] == "2100.00"
        assert cat["supporting_data"]["overall_category_avg"] == "1000.00"
        assert cat["supporting_data"]["percent_above_average"] == "110.00"

        bar = _find(data, "Reduce visits to Bar")
        assert _d(bar["estimated_monthly_savings"]) == _d("30.00")     # 200 * 0.15
        assert _d(bar["estimated_annual_savings"]) == _d("360.00")
        assert bar["supporting_data"]["visit_count"] == 4
        assert bar["supporting_data"]["monthly_frequency"] == "2.00"
        assert bar["supporting_data"]["average_per_visit"] == "200.00"

        assert _d(data["total_estimated_monthly_savings"]) == _d("250.00")
        assert _d(data["total_estimated_annual_savings"]) == _d("3000.00")
        assert data["categories_analyzed"] == 3
        assert data["merchants_analyzed"] == 3
        assert data["months_of_data"] == 2

    def test_null_account_transactions_excluded_from_scoped_views(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a, acc_b = _seed(db, uid)
        db.close()

        unfiltered = _recs(client, user_a_auth).json()
        scoped_a = _recs(client, user_a_auth, account_id=acc_a).json()
        scoped_b = _recs(client, user_a_auth, account_id=acc_b).json()

        # The NULL-account Casino drives the unfiltered Entertainment rec...
        assert _find(unfiltered, "Reduce spending on Entertainment") is not None
        assert unfiltered["categories_analyzed"] == 5
        assert unfiltered["merchants_analyzed"] == 7  # includes Casino

        # ...but never leaks into a scoped view.
        for scoped in (scoped_a, scoped_b):
            assert _find(scoped, "Reduce spending on Entertainment") is None
            titles = " ".join(r["title"] for r in scoped["recommendations"])
            assert "Casino" not in titles
            assert scoped["merchants_analyzed"] == 3
            assert scoped["categories_analyzed"] == 3
            assert _d(scoped["total_estimated_monthly_savings"]) != _d(unfiltered["total_estimated_monthly_savings"])

    def test_foreign_account_returns_404(self, client, user_a_auth, user_b_auth):
        uid_b = _user_id(user_b_auth)
        db = TestingSessionLocal()
        foreign = _add_account(db, uid_b, "User B account")
        db.close()

        res = _recs(client, user_a_auth, account_id=foreign)
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."

    def test_nonexistent_account_returns_404(self, client, user_a_auth):
        res = _recs(client, user_a_auth, account_id=999999)
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."

    def test_user_isolation(self, client, user_a_auth, user_b_auth):
        uid_a = _user_id(user_a_auth)
        uid_b = _user_id(user_b_auth)
        db = TestingSessionLocal()
        acc_a, _ = _seed(db, uid_a)
        # User B: Housing 1000/mo + Food 500/mo, one tx per month each.
        own = _add_account(db, uid_b, "B-only")
        for d in (date(2026, 8, 12), date(2026, 9, 12)):
            _tx(db, uid_b, "Landlord2", 1000, "Housing", d, own)
            _tx(db, uid_b, "Store2", 500, "Food", d, own)
        db.close()

        first_a = _recs(client, user_a_auth, account_id=acc_a).json()
        first_all = _recs(client, user_a_auth).json()
        second = _recs(client, user_b_auth).json()

        # User A unchanged by user B's data (scoped and unfiltered).
        assert [r["title"] for r in first_a["recommendations"]] == [
            "Reduce spending on Food", "Reduce visits to Coffee Shop",
        ]
        assert _d(first_a["total_estimated_monthly_savings"]) == _d("135.00")
        assert _d(first_all["total_estimated_monthly_savings"]) == _d("1552.84")
        assert first_all["merchants_analyzed"] == 7

        # User B: avgs Food 500 + Housing 1000 -> overall 750; Housing only
        # clears 562.50: (1000-750)*0.20 = 50.00/month. Single txs per month
        # -> no merchant recommendations.
        titles = [r["title"] for r in second["recommendations"]]
        assert titles == ["Reduce spending on Housing"]
        cat = _find(second, "Reduce spending on Housing")
        assert _d(cat["estimated_monthly_savings"]) == _d("50.00")
        assert _d(cat["estimated_annual_savings"]) == _d("600.00")
        assert cat["supporting_data"]["percent_above_average"] == "33.33"
        assert second["categories_analyzed"] == 2
        assert second["merchants_analyzed"] == 2
        assert second["months_of_data"] == 2

        # User A's account ids are invisible to user B.
        stolen = _recs(client, user_b_auth, account_id=acc_a)
        assert stolen.status_code == 404
        assert stolen.json()["detail"] == "Account not found."
