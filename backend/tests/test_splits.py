import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.database.db import Base, get_db, Transaction, TransactionSplit

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


@pytest.fixture
def db_session():
    return TestingSessionLocal()


def _register_and_login(client, email, password, name):
    client.post("/api/auth/register", json={"email": email, "password": password, "full_name": name})
    res = client.post("/api/auth/login", data={"username": email, "password": password})
    return res.json()["access_token"]


@pytest.fixture
def auth_token(client):
    return _register_and_login(client, "testuser@example.com", "TestPass123", "Test User")


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def second_auth_token(client):
    return _register_and_login(client, "other@example.com", "OtherPass123", "Other User")


@pytest.fixture
def second_auth_headers(second_auth_token):
    return {"Authorization": f"Bearer {second_auth_token}"}


def _add_tx(user_id, description, amount, category, tx_date=None, tx_type="debit"):
    db = TestingSessionLocal()
    try:
        if tx_date is None:
            tx_date = date.today()
        db.add(Transaction(
            user_id=user_id,
            date=tx_date,
            description=description,
            amount=Decimal(str(amount)),
            transaction_type=tx_type,
            category=category,
        ))
        db.commit()
        # Return the transaction
        tx = db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.description == description,
        ).first()
        return tx
    finally:
        db.close()


# ── Authentication Tests ──

def test_unauthenticated_list_splits(client):
    tx = _add_tx(1, "Lunch", "50.00", "food")
    res = client.get(f"/api/transactions/{tx.id}/splits")
    assert res.status_code in (401, 403)


def test_unauthenticated_create_splits(client):
    tx = _add_tx(1, "Lunch", "50.00", "food")
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "50.00"}
    ])
    assert res.status_code in (401, 403)


# ── Create Valid Split Tests ──

def test_create_single_split(client, auth_headers):
    tx = _add_tx(1, "Groceries", "100.00", "shopping")
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "60.00"},
        {"category": "household", "amount": "40.00"},
    ], headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert len(data) == 2
    assert Decimal(data[0]['amount']) + Decimal(data[1]['amount']) == Decimal('100.00')


def test_create_split_all_amount(client, auth_headers):
    tx = _add_tx(1, "Cafe", "50.00", "food")
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "50.00"},
    ], headers=auth_headers)
    assert res.status_code == 201
    assert len(res.json()) == 1


# ── Exact Total Matching Tests ──

def test_split_total_matches_transaction(client, auth_headers):
    tx = _add_tx(1, "Big Purchase", "250.00", "shopping")
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "electronics", "amount": "100.00"},
        {"category": "clothing", "amount": "75.00"},
        {"category": "books", "amount": "75.00"},
    ], headers=auth_headers)
    assert res.status_code == 201
    total = sum(Decimal(s['amount']) for s in res.json())
    assert total == Decimal('250.00')


# ── Under/Over Total Rejection Tests ──

def test_split_under_total_rejected(client, auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "40.00"},
        {"category": "drinks", "amount": "30.00"},
    ], headers=auth_headers)
    assert res.status_code == 422
    assert "does not match" in res.json()['detail']


def test_split_over_total_rejected(client, auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "60.00"},
        {"category": "drinks", "amount": "60.00"},
    ], headers=auth_headers)
    assert res.status_code == 422
    assert "does not match" in res.json()['detail']


# ── Zero/Negative Amounts Tests ──

def test_split_zero_amount_rejected(client, auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "0"},
    ], headers=auth_headers)
    assert res.status_code == 422


def test_split_negative_amount_rejected(client, auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "-100.00"},
    ], headers=auth_headers)
    assert res.status_code == 422


# ── Update Splits Tests ──

def test_update_split_category(client, auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    create_res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "100.00"},
    ], headers=auth_headers)
    split_id = create_res.json()[0]['id']

    res = client.put(f"/api/splits/{split_id}", json={
        "category": "dining",
    }, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()['category'] == 'dining'


def test_update_split_amount(client, auth_headers):
    tx = _add_tx(1, "Groceries", "100.00", "shopping")
    create_res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "50.00"},
        {"category": "household", "amount": "50.00"},
    ], headers=auth_headers)
    split_id = create_res.json()[0]['id']

    # Valid update: changing both splits to keep total at 100
    res = client.put(f"/api/splits/{split_id}", json={
        "amount": "30.00",
    }, headers=auth_headers)
    # This should fail because other split is still 50, total would be 80
    assert res.status_code == 422


def test_update_split_invalid_total_rejected(client, auth_headers):
    tx = _add_tx(1, "Groceries", "100.00", "shopping")
    create_res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "50.00"},
        {"category": "household", "amount": "50.00"},
    ], headers=auth_headers)
    split_id = create_res.json()[0]['id']

    res = client.put(f"/api/splits/{split_id}", json={
        "amount": "80.00",
    }, headers=auth_headers)
    assert res.status_code == 422
    assert "would not match" in res.json()['detail']


def test_update_split_not_found(client, auth_headers):
    res = client.put("/api/splits/99999", json={
        "category": "food",
    }, headers=auth_headers)
    assert res.status_code == 404


# ── Delete Splits Tests ──

def test_delete_split(client, auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    create_res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "60.00"},
        {"category": "drinks", "amount": "40.00"},
    ], headers=auth_headers)
    split_id = create_res.json()[0]['id']

    res = client.delete(f"/api/splits/{split_id}", headers=auth_headers)
    assert res.status_code == 200
    assert "deleted" in res.json()['message']

    # Verify only one split remains
    list_res = client.get(f"/api/transactions/{tx.id}/splits", headers=auth_headers)
    assert len(list_res.json()) == 1


def test_delete_split_not_found(client, auth_headers):
    res = client.delete("/api/splits/99999", headers=auth_headers)
    assert res.status_code == 404


# ── User Isolation Tests ──

def test_user_isolation_create_splits(client, auth_headers, second_auth_headers):
    tx1 = _add_tx(1, "MyGroceries", "100.00", "food")
    tx2 = _add_tx(2, "TheirGroceries", "200.00", "food")

    # User 1 creates splits
    res1 = client.post(f"/api/transactions/{tx1.id}/splits", json=[
        {"category": "food", "amount": "100.00"},
    ], headers=auth_headers)
    assert res1.status_code == 201

    # User 2 cannot see user 1's transaction at all (404)
    res2 = client.get(f"/api/transactions/{tx1.id}/splits", headers=second_auth_headers)
    assert res2.status_code == 404


def test_user_isolation_update_split(client, auth_headers, second_auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    create_res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "100.00"},
    ], headers=auth_headers)
    split_id = create_res.json()[0]['id']

    # User 2 cannot update user 1's split
    res = client.put(f"/api/splits/{split_id}", json={
        "category": "hacked",
    }, headers=second_auth_headers)
    assert res.status_code == 404


def test_user_isolation_delete_split(client, auth_headers, second_auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    create_res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "100.00"},
    ], headers=auth_headers)
    split_id = create_res.json()[0]['id']

    # User 2 cannot delete user 1's split
    res = client.delete(f"/api/splits/{split_id}", headers=second_auth_headers)
    assert res.status_code == 404


# ── Transaction Without Splits Still Works Tests ──

def test_transaction_without_splits_still_works(client, auth_headers):
    tx = _add_tx(1, "Coffee", "5.00", "food")
    res = client.get(f"/api/transactions/{tx.id}/splits", headers=auth_headers)
    assert res.status_code == 200
    assert res.json() == []


def test_transaction_list_unchanged_by_splits(client, auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    # Create splits
    client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "100.00"},
    ], headers=auth_headers)

    # Transaction still appears normally
    res = client.get("/api/transactions", headers=auth_headers)
    assert res.status_code == 200
    txs = res.json()['transactions']
    assert len(txs) == 1
    assert float(txs[0]['amount']) == 100.0  # Amount unchanged


def test_delete_transaction_cascades_splits(client, auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "100.00"},
    ], headers=auth_headers)

    res = client.delete(f"/api/transactions/{tx.id}", headers=auth_headers)
    assert res.status_code == 200

    # Transaction gone — listing splits returns 404 (transaction not found)
    list_res = client.get(f"/api/transactions/{tx.id}/splits", headers=auth_headers)
    assert list_res.status_code == 404


# ── Decimal Precision Tests ──

def test_decimal_precision_in_splits(client, auth_headers):
    tx = _add_tx(1, "Precision Test", "33.33", "test")
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "a", "amount": "11.11"},
        {"category": "b", "amount": "11.11"},
        {"category": "c", "amount": "11.11"},
    ], headers=auth_headers)
    assert res.status_code == 201
    total = sum(Decimal(s['amount']) for s in res.json())
    assert total == Decimal('33.33')


# ── Rollback/Atomicity Tests ──

def test_create_splits_replaces_existing(client, auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    # First set of splits
    client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "100.00"},
    ], headers=auth_headers)

    # Second set replaces
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "drinks", "amount": "100.00"},
    ], headers=auth_headers)
    assert res.status_code == 201
    assert len(res.json()) == 1
    assert res.json()[0]['category'] == 'drinks'


def test_invalid_split_does_not_corrupt_state(client, auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    # First valid split
    client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "100.00"},
    ], headers=auth_headers)

    # Invalid split (doesn't match)
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "50.00"},
    ], headers=auth_headers)
    assert res.status_code == 422

    # Original splits still intact
    list_res = client.get(f"/api/transactions/{tx.id}/splits", headers=auth_headers)
    assert len(list_res.json()) == 1


# ── Duplicate Category Rejection Tests ──

def test_duplicate_category_rejected(client, auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "50.00"},
        {"category": "food", "amount": "50.00"},
    ], headers=auth_headers)
    assert res.status_code == 422
    assert "duplicate" in res.json()['detail'].lower()


# ── Empty/Invalid Transaction Tests ──

def test_split_nonexistent_transaction(client, auth_headers):
    res = client.post("/api/transactions/99999/splits", json=[
        {"category": "food", "amount": "100.00"},
    ], headers=auth_headers)
    assert res.status_code == 422
    assert "not found" in res.json()['detail'].lower()


def test_split_empty_list_rejected(client, auth_headers):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    res = client.post(f"/api/transactions/{tx.id}/splits", json=[], headers=auth_headers)
    assert res.status_code == 422


# ── Split Summary Tests ──

def test_split_summary(client, auth_headers):
    tx = _add_tx(1, "Groceries", "200.00", "shopping")
    client.post(f"/api/transactions/{tx.id}/splits", json=[
        {"category": "food", "amount": "120.00"},
        {"category": "household", "amount": "80.00"},
    ], headers=auth_headers)

    res = client.get(f"/api/transactions/{tx.id}/split-summary", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data['transaction_amount'] == 200.00
    assert data['split_total'] == 200.00
    assert data['split_count'] == 2
    assert data['is_split'] is True
    assert data['remaining'] == 0


def test_split_summary_no_splits(client, auth_headers):
    tx = _add_tx(1, "Lunch", "50.00", "food")
    res = client.get(f"/api/transactions/{tx.id}/split-summary", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data['is_split'] is False
    assert data['split_count'] == 0
    assert data['remaining'] == 50.00


# ── Unauthenticated Access Tests ──

def test_unauthenticated_update_split(client):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    db = TestingSessionLocal()
    try:
        db.add(TransactionSplit(
            transaction_id=tx.id,
            user_id=1,
            category="food",
            amount=Decimal("100.00"),
        ))
        db.commit()
        split = db.query(TransactionSplit).filter(TransactionSplit.transaction_id == tx.id).first()
        split_id = split.id
    finally:
        db.close()

    res = client.put(f"/api/splits/{split_id}", json={"category": "hacked"})
    assert res.status_code in (401, 403)


def test_unauthenticated_delete_split(client):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    db = TestingSessionLocal()
    try:
        db.add(TransactionSplit(
            transaction_id=tx.id,
            user_id=1,
            category="food",
            amount=Decimal("100.00"),
        ))
        db.commit()
        split = db.query(TransactionSplit).filter(TransactionSplit.transaction_id == tx.id).first()
        split_id = split.id
    finally:
        db.close()

    res = client.delete(f"/api/splits/{split_id}")
    assert res.status_code in (401, 403)
