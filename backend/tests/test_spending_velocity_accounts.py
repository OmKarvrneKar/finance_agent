"""Phase 4C: account-aware spending velocity (backend only).

GET /api/analytics/spending-velocity accepts an optional ``account_id``.
When supplied, only transactions belonging to that account participate in
the current window, the baseline windows, and history coverage. Foreign or
nonexistent accounts return 404. Omitting ``account_id`` preserves the
existing algorithm, thresholds, baseline methodology, window calculations,
and notification behaviour exactly.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, Account, Transaction, TransactionSplit
from app.services.spending_velocity import get_spending_velocity


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def user1_token(client):
    client.post("/api/auth/register", json={"email": "sva@test.com", "password": "Password123", "full_name": "SVA"})
    resp = client.post("/api/auth/login", data={"username": "sva@test.com", "password": "Password123"})
    return resp.json()["access_token"]


@pytest.fixture()
def user2_token(client):
    client.post("/api/auth/register", json={"email": "svb@test.com", "password": "Password123", "full_name": "SVB"})
    resp = client.post("/api/auth/login", data={"username": "svb@test.com", "password": "Password123"})
    return resp.json()["access_token"]


def _get_user_id(token: str) -> int:
    import jwt
    from app.auth import JWT_SECRET_KEY
    return int(jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])["sub"])


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _add_account(db, user_id, name="Account", account_type="bank"):
    account = Account(user_id=user_id, name=name, account_type=account_type)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account.id


def _add_tx(db, user_id, tx_date, amount, tx_type="debit", description="Spend", account_id=None):
    db.add(Transaction(
        user_id=user_id,
        date=tx_date,
        description=description,
        amount=Decimal(str(amount)),
        transaction_type=tx_type,
        category="Other",
        account_id=account_id,
    ))
    db.commit()


def _seed_prior_windows(
    db,
    user_id,
    today,
    window_days=3,
    num_windows=5,
    spend_per_window=Decimal("100"),
    account_id=None,
):
    """Seed one transaction per prior non-overlapping window before today's window."""
    current_start = today - timedelta(days=window_days - 1)
    cursor_end = current_start - timedelta(days=1)
    for _ in range(num_windows):
        w_end = cursor_end
        w_start = w_end - timedelta(days=window_days - 1)
        _add_tx(db, user_id, w_start, spend_per_window, description="hist", account_id=account_id)
        cursor_end = w_start - timedelta(days=1)


def _velocity(client, token, account_id=None, window_days=3):
    params = [f"window_days={window_days}"]
    if account_id is not None:
        params.append(f"account_id={account_id}")
    return client.get(
        f"/api/analytics/spending-velocity?{'&'.join(params)}",
        headers=_auth(token),
    )


def _notifications(client, token):
    return client.get("/api/notifications", headers=_auth(token)).json()["notifications"]


class TestAccountAwareVelocity:
    def test_existing_behavior_without_account_id(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        acc_a = _add_account(db_session, uid, "A")
        acc_b = _add_account(db_session, uid, "B")
        _seed_prior_windows(db_session, uid, today, account_id=acc_a)
        _seed_prior_windows(db_session, uid, today, account_id=acc_b)
        _add_tx(db_session, uid, today, Decimal("100"), account_id=acc_a)
        _add_tx(db_session, uid, today, Decimal("200"), account_id=acc_b)
        _add_tx(db_session, uid, today, Decimal("50"))  # NULL account

        resp = _velocity(client, user1_token)
        assert resp.status_code == 200
        data = resp.json()
        # Without account_id every debit counts: A + B + NULL.
        assert Decimal(str(data["current_window_spend"])) == Decimal("350.00")
        assert data["alert_level"] == "elevated"  # 350 vs 200 baseline
        assert data["baseline_windows_used"] == 5

        # Service level: omitting account_id and passing None are identical.
        omitted = get_spending_velocity(db_session, uid, window_days=3)
        explicit_none = get_spending_velocity(db_session, uid, window_days=3, account_id=None)
        assert omitted == explicit_none

    def test_account_filtered_velocity(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        acc_a = _add_account(db_session, uid, "A")
        acc_b = _add_account(db_session, uid, "B")
        _seed_prior_windows(db_session, uid, today, account_id=acc_a)
        _seed_prior_windows(db_session, uid, today, account_id=acc_b)
        _add_tx(db_session, uid, today, Decimal("100"), account_id=acc_a)
        _add_tx(db_session, uid, today, Decimal("250"), account_id=acc_b)
        _add_tx(db_session, uid, today, Decimal("50"))  # NULL account

        resp_a = _velocity(client, user1_token, account_id=acc_a)
        assert resp_a.status_code == 200
        data_a = resp_a.json()
        assert Decimal(str(data_a["current_window_spend"])) == Decimal("100.00")
        assert Decimal(str(data_a["baseline_window_spend"])) == Decimal("100.00")
        assert data_a["velocity_ratio"] == 1.0
        assert data_a["alert_level"] == "normal"

        resp_b = _velocity(client, user1_token, account_id=acc_b)
        data_b = resp_b.json()
        assert Decimal(str(data_b["current_window_spend"])) == Decimal("250.00")
        assert data_b["velocity_ratio"] == 2.5
        assert data_b["alert_level"] == "high"

    def test_foreign_account_returns_404(self, db_session, client, user1_token, user2_token):
        uid2 = _get_user_id(user2_token)
        foreign = _add_account(db_session, uid2, "User 2 account")

        # The account exists and works for its owner...
        own = _velocity(client, user2_token, account_id=foreign)
        assert own.status_code == 200

        # ...but another user requesting it gets 404.
        stolen = _velocity(client, user1_token, account_id=foreign)
        assert stolen.status_code == 404
        assert stolen.json()["detail"] == "Account not found."

    def test_nonexistent_account_returns_404(self, db_session, client, user1_token):
        resp = _velocity(client, user1_token, account_id=999999)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Account not found."

    def test_null_account_transactions_excluded(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        acc = _add_account(db_session, uid, "Scoped")
        _seed_prior_windows(db_session, uid, today, account_id=acc)
        _add_tx(db_session, uid, today, Decimal("70"))            # NULL account
        _add_tx(db_session, uid, today, Decimal("30"), account_id=acc)

        unfiltered = _velocity(client, user1_token)
        assert Decimal(str(unfiltered.json()["current_window_spend"])) == Decimal("100.00")

        filtered = _velocity(client, user1_token, account_id=acc)
        assert Decimal(str(filtered.json()["current_window_spend"])) == Decimal("30.00")
        assert Decimal(str(filtered.json()["baseline_window_spend"])) == Decimal("100.00")

    def test_multiple_accounts(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        acc_a = _add_account(db_session, uid, "A")
        acc_b = _add_account(db_session, uid, "B")
        _add_tx(db_session, uid, today, Decimal("100"), account_id=acc_a)
        _add_tx(db_session, uid, today, Decimal("200"), account_id=acc_b)
        _add_tx(db_session, uid, today, Decimal("50"))  # NULL account

        all_spend = Decimal(str(_velocity(client, user1_token).json()["current_window_spend"]))
        a_spend = Decimal(str(_velocity(client, user1_token, account_id=acc_a).json()["current_window_spend"]))
        b_spend = Decimal(str(_velocity(client, user1_token, account_id=acc_b).json()["current_window_spend"]))

        assert all_spend == Decimal("350.00")
        assert a_spend == Decimal("100.00")
        assert b_spend == Decimal("200.00")
        # Per-account slices plus NULL-account spend reconstruct the total.
        assert a_spend + b_spend + Decimal("50.00") == all_spend

    def test_split_transaction_correctness(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        acc = _add_account(db_session, uid, "A")
        _seed_prior_windows(db_session, uid, today, account_id=acc)

        db_session.add(Transaction(
            user_id=uid,
            date=today,
            description="split parent",
            amount=Decimal("300"),
            transaction_type="debit",
            category="Other",
            account_id=acc,
        ))
        db_session.commit()
        parent = (
            db_session.query(Transaction)
            .filter(Transaction.description == "split parent")
            .one()
        )
        db_session.add(TransactionSplit(
            transaction_id=parent.id, user_id=uid, category="Food", amount=Decimal("200"),
        ))
        db_session.add(TransactionSplit(
            transaction_id=parent.id, user_id=uid, category="Transport", amount=Decimal("100"),
        ))
        db_session.commit()

        # Original amount counted exactly once; split rows never added.
        filtered = _velocity(client, user1_token, account_id=acc)
        assert Decimal(str(filtered.json()["current_window_spend"])) == Decimal("300.00")
        assert filtered.json()["alert_level"] == "very_high"  # 300 / 100 baseline

        unfiltered = _velocity(client, user1_token)
        assert Decimal(str(unfiltered.json()["current_window_spend"])) == Decimal("300.00")

    def test_baseline_correctness_account_scoped(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        acc_a = _add_account(db_session, uid, "A")
        acc_b = _add_account(db_session, uid, "B")
        _seed_prior_windows(db_session, uid, today, spend_per_window=Decimal("100"), account_id=acc_a)
        _seed_prior_windows(db_session, uid, today, spend_per_window=Decimal("1000"), account_id=acc_b)
        _add_tx(db_session, uid, today, Decimal("100"), account_id=acc_a)
        _add_tx(db_session, uid, today, Decimal("1000"), account_id=acc_b)

        resp_a = _velocity(client, user1_token, account_id=acc_a)
        data_a = resp_a.json()
        assert Decimal(str(data_a["baseline_window_spend"])) == Decimal("100.00")
        assert Decimal(str(data_a["current_window_spend"])) == Decimal("100.00")
        assert data_a["baseline_windows_used"] == 5
        assert data_a["velocity_ratio"] == 1.0

        resp_b = _velocity(client, user1_token, account_id=acc_b)
        data_b = resp_b.json()
        assert Decimal(str(data_b["baseline_window_spend"])) == Decimal("1000.00")
        assert Decimal(str(data_b["current_window_spend"])) == Decimal("1000.00")
        assert data_b["velocity_ratio"] == 1.0

        # Unfiltered baseline averages the mixed windows (100 + 1000).
        unfiltered = _velocity(client, user1_token).json()
        assert Decimal(str(unfiltered["baseline_window_spend"])) == Decimal("1100.00")
        assert Decimal(str(unfiltered["current_window_spend"])) == Decimal("1100.00")
        assert unfiltered["baseline_windows_used"] == 5
        assert unfiltered["velocity_ratio"] == 1.0

    def test_notification_behavior_remains_unchanged(self, db_session, client, user1_token):
        uid = _get_user_id(user1_token)
        today = date.today()
        acc_a = _add_account(db_session, uid, "A")
        acc_b = _add_account(db_session, uid, "B")
        _seed_prior_windows(db_session, uid, today, spend_per_window=Decimal("100"), account_id=acc_a)
        _seed_prior_windows(db_session, uid, today, spend_per_window=Decimal("100"), account_id=acc_b)
        _add_tx(db_session, uid, today, Decimal("400"), account_id=acc_a)
        _add_tx(db_session, uid, today, Decimal("100"), account_id=acc_b)

        # Account-scoped view: 400 / 100 baseline = very_high.
        scoped = _velocity(client, user1_token, account_id=acc_a).json()
        assert scoped["alert_level"] == "very_high"
        assert Decimal(str(scoped["current_window_spend"])) == Decimal("400.00")

        # The notification sync endpoint is untouched: it still uses the
        # unfiltered (all-account) velocity — 500 / 200 baseline = high.
        data = client.post(
            "/api/notifications/sync/velocity?window_days=3",
            headers=_auth(user1_token),
        ).json()
        assert data["alert_level"] == "high"
        assert data["created"] == 1

        notes = _notifications(client, user1_token)
        assert len(notes) == 1
        assert notes[0]["type"] == "spending_velocity"
        assert notes[0]["severity"] == "warning"
        assert notes[0]["metadata"]["alert_level"] == "high"
        assert notes[0]["metadata"]["velocity_ratio"] == 2.5
        assert notes[0]["metadata"]["current_window_spend"] == "500.00"

        # Re-syncing stays idempotent, exactly as before.
        again = client.post(
            "/api/notifications/sync/velocity?window_days=3",
            headers=_auth(user1_token),
        ).json()
        assert again["created"] == 0
        assert len(_notifications(client, user1_token)) == 1
