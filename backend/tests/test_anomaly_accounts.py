"""Phase 4F: account-aware anomaly detection (backend only).

GET /api/anomalies accepts an optional ``account_id``. When supplied, every
detector (large expenses, duplicates, price jumps) runs against that
account's transactions only, including their historical/baseline queries;
NULL-account rows are excluded. Foreign/nonexistent accounts return 404.
Omitting ``account_id`` preserves existing anomaly behavior, thresholds,
scoring, rules, severities, and descriptions exactly. Notification and agent
callers use the unchanged default (no account filter).
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
from app.services.anomalies import generate_anomaly_report

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


def _seed_tx(db, uid, yr, mo, day, amount, desc="Spend", account_id=None, recurring=False):
    tx = Transaction(
        user_id=uid,
        date=date(yr, mo, day),
        description=desc,
        amount=Decimal(str(amount)),
        transaction_type="debit",
        category="Food",
        is_recurring=recurring,
        account_id=account_id,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx.id


def _get(client, auth, account_id=None):
    if account_id is None:
        return client.get("/api/anomalies", headers=auth)
    return client.get(f"/api/anomalies?account_id={account_id}", headers=auth)


def _types(data):
    return [a["type"] for a in data]


class TestAccountAwareAnomalies:
    def test_existing_behavior_without_account_id(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        t1 = _seed_tx(db, uid, 2026, 3, 1, "45", desc="Target")
        t2 = _seed_tx(db, uid, 2026, 3, 2, "45", desc="Target")
        db.close()

        res = _get(client, user_a_auth)
        assert res.status_code == 200
        data = res.json()
        dups = [a for a in data if a["type"] == "duplicate"]
        assert len(dups) == 1
        assert dups[0]["merchant"] == "Target"
        assert dups[0]["severity"] == "critical"
        assert "Possible duplicate" in dups[0]["message"]
        assert sorted(dups[0]["transaction_ids"]) == sorted([t1, t2])
        assert dups[0]["id"] == f"duplicate_{'-'.join(map(str, sorted([t1, t2])))}"

        # Service: omitted account_id and explicit None are identical.
        db = TestingSessionLocal()
        omitted = generate_anomaly_report(db, uid)
        explicit_none = generate_anomaly_report(db, uid, account_id=None)
        assert omitted == explicit_none
        db.close()

    def test_account_filtered_anomalies(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        acc_b = _add_account(db, uid, "B")
        a1 = _seed_tx(db, uid, 2026, 3, 1, "45", desc="Target", account_id=acc_a)
        a2 = _seed_tx(db, uid, 2026, 3, 2, "45", desc="Target", account_id=acc_a)
        b1 = _seed_tx(db, uid, 2026, 3, 1, "80", desc="Myntra", account_id=acc_b)
        b2 = _seed_tx(db, uid, 2026, 3, 2, "80", desc="Myntra", account_id=acc_b)
        db.close()

        data_a = _get(client, user_a_auth, account_id=acc_a).json()
        data_b = _get(client, user_a_auth, account_id=acc_b).json()
        data_all = _get(client, user_a_auth).json()

        dup_a = [a for a in data_a if a["type"] == "duplicate"]
        dup_b = [a for a in data_b if a["type"] == "duplicate"]
        dup_all = [a for a in data_all if a["type"] == "duplicate"]

        assert len(dup_a) == 1 and dup_a[0]["merchant"] == "Target"
        assert len(dup_b) == 1 and dup_b[0]["merchant"] == "Myntra"
        assert sorted(dup_a[0]["transaction_ids"]) == sorted([a1, a2])
        assert sorted(dup_b[0]["transaction_ids"]) == sorted([b1, b2])
        assert len(dup_all) == 2
        assert dup_a[0]["id"] != dup_b[0]["id"]

    def test_large_expense_detection_filtered(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc = _add_account(db, uid, "A")
        for i in range(1, 12):
            _seed_tx(db, uid, 2026, 3, i, "100", desc="Kirana Store", account_id=acc)
        big = _seed_tx(db, uid, 2026, 3, 12, "1000", desc="Big Bazaar", account_id=acc)
        db.close()

        data = _get(client, user_a_auth, account_id=acc).json()
        large = [a for a in data if a["type"] == "unfamiliar_merchant"]
        assert len(large) == 1
        assert large[0]["merchant"] == "Big Bazaar"
        assert Decimal(str(large[0]["amount"])) == Decimal("1000")
        assert large[0]["transaction_ids"] == [big]
        assert large[0]["severity"] in ("info", "warning", "critical")
        assert "Unusually large new expense" in large[0]["message"]

    def test_duplicate_detection_filtered(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc = _add_account(db, uid, "A")
        t1 = _seed_tx(db, uid, 2026, 3, 1, "45", desc="Target", account_id=acc)
        t2 = _seed_tx(db, uid, 2026, 3, 2, "45", desc="Target", account_id=acc)
        db.close()

        data = _get(client, user_a_auth, account_id=acc).json()
        dups = [a for a in data if a["type"] == "duplicate"]
        assert len(dups) == 1
        assert dups[0]["id"] == f"duplicate_{'-'.join(map(str, sorted([t1, t2])))}"
        assert Decimal(str(dups[0]["amount"])) == Decimal("45")
        assert dups[0]["severity"] == "critical"

    def test_price_jump_detection_filtered(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc = _add_account(db, uid, "A")
        _seed_tx(db, uid, 2026, 1, 1, "100", desc="Netflix", account_id=acc, recurring=True)
        _seed_tx(db, uid, 2026, 2, 1, "100", desc="Netflix", account_id=acc, recurring=True)
        jump = _seed_tx(db, uid, 2026, 3, 1, "150", desc="Netflix", account_id=acc, recurring=True)
        db.close()

        data = _get(client, user_a_auth, account_id=acc).json()
        jumps = [a for a in data if a["type"] == "price_jump"]
        assert len(jumps) == 1
        assert jumps[0]["merchant"] == "Netflix"
        assert jumps[0]["percent_increase"] == 50.0
        assert jumps[0]["transaction_ids"] == [jump]
        assert jumps[0]["severity"] == "warning"   # >50% would be critical
        assert "Price jump" in jumps[0]["message"]

    def test_historical_baseline_filtering(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        acc_b = _add_account(db, uid, "B")
        # A: 11 small regular expenses + one 1000 outlier -> flagged for A.
        for i in range(1, 12):
            _seed_tx(db, uid, 2026, 3, i, "100", desc="Kirana Store", account_id=acc_a)
        _seed_tx(db, uid, 2026, 3, 12, "1000", desc="Big Bazaar", account_id=acc_a)
        # B: 9 regular expenses + one 99999 outlier (>= 10 txns for the
        # detector) that also skews the unfiltered baseline.
        for i in range(1, 10):
            _seed_tx(db, uid, 2026, 4, i, "100", desc="Local Mart", account_id=acc_b)
        _seed_tx(db, uid, 2026, 4, 10, "99999", desc="Mall", account_id=acc_b)
        db.close()

        # Filtered to A: baseline/stats from A's 12 txns only -> Big Bazaar flagged.
        data_a = _get(client, user_a_auth, account_id=acc_a).json()
        large_a = [a for a in data_a if a["type"] == "unfamiliar_merchant"]
        assert [a["merchant"] for a in large_a] == ["Big Bazaar"]

        # Filtered to B: only B's outlier exists in the baseline population.
        data_b = _get(client, user_a_auth, account_id=acc_b).json()
        large_b = [a for a in data_b if a["type"] == "unfamiliar_merchant"]
        assert [a["merchant"] for a in large_b] == ["Mall"]

        # Unfiltered: B's 99999 inflates mean/stddev above A's 1000 outlier,
        # so only Mall is flagged — the baseline population differs.
        data_all = _get(client, user_a_auth).json()
        large_all = [a for a in data_all if a["type"] == "unfamiliar_merchant"]
        assert [a["merchant"] for a in large_all] == ["Mall"]

    def test_foreign_account_returns_404(self, client, user_a_auth, user_b_auth):
        uid_b = _user_id(user_b_auth)
        db = TestingSessionLocal()
        foreign = _add_account(db, uid_b, "User B account")
        db.close()

        own = _get(client, user_b_auth, account_id=foreign)
        assert own.status_code == 200

        stolen = _get(client, user_a_auth, account_id=foreign)
        assert stolen.status_code == 404
        assert stolen.json()["detail"] == "Account not found."

    def test_nonexistent_account_returns_404(self, client, user_a_auth):
        resp = _get(client, user_a_auth, account_id=999999)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Account not found."

    def test_null_account_transactions_excluded(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc = _add_account(db, uid, "Scoped")
        t1 = _seed_tx(db, uid, 2026, 3, 1, "45", desc="Target", account_id=acc)
        t2 = _seed_tx(db, uid, 2026, 3, 2, "45", desc="Target", account_id=acc)
        n1 = _seed_tx(db, uid, 2026, 3, 3, "45", desc="Target")  # NULL account
        db.close()

        filtered = _get(client, user_a_auth, account_id=acc).json()
        unfiltered = _get(client, user_a_auth).json()

        dup_f = [a for a in filtered if a["type"] == "duplicate"]
        dup_u = [a for a in unfiltered if a["type"] == "duplicate"]

        # Filtered sees only the two on-account rows -> exactly one pair.
        assert len(dup_f) == 1
        assert sorted(dup_f[0]["transaction_ids"]) == sorted([t1, t2])
        # Unfiltered groups all three -> two adjacent pairs including the NULL row.
        assert len(dup_u) == 2
        all_ids = sorted({i for a in dup_u for i in a["transaction_ids"]})
        assert all_ids == sorted([t1, t2, n1])
        assert n1 not in dup_f[0]["transaction_ids"]

    def test_multiple_accounts(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        acc_b = _add_account(db, uid, "B")
        _seed_tx(db, uid, 2026, 3, 1, "45", desc="Target", account_id=acc_a)
        _seed_tx(db, uid, 2026, 3, 2, "45", desc="Target", account_id=acc_a)
        _seed_tx(db, uid, 2026, 4, 1, "80", desc="Myntra", account_id=acc_b)
        _seed_tx(db, uid, 2026, 4, 2, "80", desc="Myntra", account_id=acc_b)
        db.close()

        data_a = _get(client, user_a_auth, account_id=acc_a).json()
        data_b = _get(client, user_a_auth, account_id=acc_b).json()
        data_all = _get(client, user_a_auth).json()

        assert [a["merchant"] for a in data_a if a["type"] == "duplicate"] == ["Target"]
        assert [a["merchant"] for a in data_b if a["type"] == "duplicate"] == ["Myntra"]
        assert sorted(
            a["merchant"] for a in data_all if a["type"] == "duplicate"
        ) == ["Myntra", "Target"]
        assert {a["id"] for a in data_a}.isdisjoint({a["id"] for a in data_b})

    def test_no_false_cross_account_duplicates(self, client, user_a_auth):
        uid = _user_id(user_a_auth)
        db = TestingSessionLocal()
        acc_a = _add_account(db, uid, "A")
        acc_b = _add_account(db, uid, "B")
        t_a = _seed_tx(db, uid, 2026, 3, 1, "45", desc="Target", account_id=acc_a)
        t_b = _seed_tx(db, uid, 2026, 3, 2, "45", desc="Target", account_id=acc_b)
        db.close()

        # Unfiltered groups the two accounts together (existing behavior).
        data_all = _get(client, user_a_auth).json()
        dup_all = [a for a in data_all if a["type"] == "duplicate"]
        assert len(dup_all) == 1
        assert sorted(dup_all[0]["transaction_ids"]) == sorted([t_a, t_b])

        # Per-account views never pair transactions across accounts.
        data_a = _get(client, user_a_auth, account_id=acc_a).json()
        data_b = _get(client, user_a_auth, account_id=acc_b).json()
        assert [a for a in data_a if a["type"] == "duplicate"] == []
        assert [a for a in data_b if a["type"] == "duplicate"] == []
