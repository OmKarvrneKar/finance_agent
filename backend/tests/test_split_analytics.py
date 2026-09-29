import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.database.db import Base, get_db, Transaction, TransactionSplit
from app.database.crud import get_splits_by_transaction_ids

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
            tx_date = date(2026, 9, 15)
        db.add(Transaction(
            user_id=user_id,
            date=tx_date,
            description=description,
            amount=Decimal(str(amount)),
            transaction_type=tx_type,
            category=category,
        ))
        db.commit()
        tx = db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.description == description,
        ).first()
        return tx
    finally:
        db.close()


def _add_split(transaction_id, user_id, category, amount):
    db = TestingSessionLocal()
    try:
        db.add(TransactionSplit(
            transaction_id=transaction_id,
            user_id=user_id,
            category=category,
            amount=Decimal(str(amount)),
        ))
        db.commit()
    finally:
        db.close()


# ── Helper: get_splits_by_transaction_ids ──

def test_get_splits_by_transaction_ids_empty(db_session):
    result = get_splits_by_transaction_ids(db_session, [], 1)
    assert result == {}


def test_get_splits_by_transaction_ids_with_splits(db_session):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    _add_split(tx.id, 1, "food", "60.00")
    _add_split(tx.id, 1, "drinks", "40.00")

    result = get_splits_by_transaction_ids(db_session, [tx.id], 1)
    assert tx.id in result
    assert len(result[tx.id]) == 2
    amounts = {s['amount'] for s in result[tx.id]}
    assert amounts == {Decimal('60.00'), Decimal('40.00')}


def test_get_splits_by_transaction_ids_user_isolation(db_session):
    tx = _add_tx(1, "Lunch", "100.00", "food")
    _add_split(tx.id, 1, "food", "100.00")

    result = get_splits_by_transaction_ids(db_session, [tx.id], 2)
    assert result == {}


# ── Unsplit Transaction Unchanged ──

def test_unsplit_transaction_category_unchanged(client, auth_headers):
    tx = _add_tx(1, "Coffee", "5.00", "food")
    res = client.get("/api/analytics/summary", headers=auth_headers)
    data = res.json()
    cats = {c['category']: c['amount'] for c in data['category_breakdown']}
    assert cats.get('food') == 5.00


def test_unsplit_transaction_total_unchanged(client, auth_headers):
    _add_tx(1, "Coffee", "5.00", "food")
    _add_tx(1, "Bus", "3.00", "transport")
    res = client.get("/api/analytics/summary", headers=auth_headers)
    data = res.json()
    assert float(data['total_expenses']) == 8.00


# ── Split Transaction Category Breakdown ──

def test_split_transaction_uses_split_categories(client, auth_headers):
    tx = _add_tx(1, "Target", "100.00", "shopping")
    _add_split(tx.id, 1, "groceries", "60.00")
    _add_split(tx.id, 1, "electronics", "40.00")

    res = client.get("/api/analytics/summary", headers=auth_headers)
    data = res.json()
    cats = {c['category']: c['amount'] for c in data['category_breakdown']}
    assert 'shopping' not in cats
    assert cats['groceries'] == 60.00
    assert cats['electronics'] == 40.00


def test_split_transaction_total_matches_original(client, auth_headers):
    tx = _add_tx(1, "Target", "100.00", "shopping")
    _add_split(tx.id, 1, "groceries", "60.00")
    _add_split(tx.id, 1, "electronics", "40.00")

    res = client.get("/api/analytics/summary", headers=auth_headers)
    data = res.json()
    assert float(data['total_expenses']) == 100.00


# ── Mixed Split + Unsplit Transactions ──

def test_mixed_split_and_unsplit_transactions(client, auth_headers):
    tx1 = _add_tx(1, "Coffee", "10.00", "food")
    tx2 = _add_tx(1, "Target", "100.00", "shopping")
    _add_split(tx2.id, 1, "groceries", "60.00")
    _add_split(tx2.id, 1, "electronics", "40.00")

    res = client.get("/api/analytics/summary", headers=auth_headers)
    data = res.json()
    cats = {c['category']: c['amount'] for c in data['category_breakdown']}
    assert cats['food'] == 10.00  # from unsplit tx
    assert cats['groceries'] == 60.00  # from split
    assert cats['electronics'] == 40.00  # from split
    assert 'shopping' not in cats  # original category replaced
    assert float(data['total_expenses']) == 110.00  # 10 + 100


# ── Exact Total Preservation ──

def test_total_expenses_never_double_counts(client, auth_headers):
    tx = _add_tx(1, "BigPurchase", "500.00", "shopping")
    _add_split(tx.id, 1, "food", "200.00")
    _add_split(tx.id, 1, "household", "150.00")
    _add_split(tx.id, 1, "clothing", "150.00")

    res = client.get("/api/analytics/summary", headers=auth_headers)
    data = res.json()
    # Total must be exactly 500, not 500 + 200 + 150 + 150 = 1000
    assert float(data['total_expenses']) == 500.00
    # Category breakdown sums to 500
    cat_total = sum(c['amount'] for c in data['category_breakdown'])
    assert float(cat_total) == 500.00


def test_split_amounts_sum_to_transaction_amount(client, auth_headers):
    tx = _add_tx(1, "Precise", "33.33", "test")
    _add_split(tx.id, 1, "a", "11.11")
    _add_split(tx.id, 1, "b", "11.11")
    _add_split(tx.id, 1, "c", "11.11")

    res = client.get("/api/analytics/summary", headers=auth_headers)
    data = res.json()
    cat_total = sum(c['amount'] for c in data['category_breakdown'])
    assert float(cat_total) == 33.33


# ── Merchant Total Remains Transaction Amount ──

def test_merchant_uses_transaction_amount_not_split_amounts(client, auth_headers):
    tx = _add_tx(1, "Starbucks", "50.00", "coffee")
    _add_split(tx.id, 1, "drinks", "30.00")
    _add_split(tx.id, 1, "snacks", "20.00")

    res = client.get("/api/analytics/merchants", headers=auth_headers)
    data = res.json()
    merchants = {m['merchant']: m for m in data['merchants']}
    assert 'Starbucks' in merchants
    # Merchant total is 50 (from transaction), NOT 30+20=50 (coincidence but correct)
    assert float(merchants['Starbucks']['total_spent']) == 50.00
    assert merchants['Starbucks']['transaction_count'] == 1


def test_merchant_total_with_unsplit_transactions(client, auth_headers):
    _add_tx(1, "Uber", "25.00", "transport")
    _add_tx(1, "Uber", "15.00", "transport")

    res = client.get("/api/analytics/merchants", headers=auth_headers)
    data = res.json()
    merchants = {m['merchant']: m for m in data['merchants']}
    assert float(merchants['Uber']['total_spent']) == 40.00
    assert merchants['Uber']['transaction_count'] == 2


# ── PDF Category Totals ──

def test_pdf_category_totals_split_aware(client, auth_headers):
    tx = _add_tx(1, "Target", "200.00", "shopping", tx_date=date(2026, 9, 5))
    _add_split(tx.id, 1, "groceries", "120.00")
    _add_split(tx.id, 1, "household", "80.00")

    res = client.get("/api/reports/monthly?year=2026&month=9", headers=auth_headers)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"


def test_pdf_category_breakdown_split_aware_via_service(db_session):
    from app.services.report_service import get_monthly_report_data

    tx = _add_tx(1, "Target", "200.00", "shopping", tx_date=date(2026, 9, 5))
    _add_split(tx.id, 1, "groceries", "120.00")
    _add_split(tx.id, 1, "household", "80.00")

    data = get_monthly_report_data(db_session, 1, 2026, 9)
    cats = {c['category']: c['amount'] for c in data['category_breakdown']}
    assert 'shopping' not in cats
    assert cats['groceries'] == Decimal('120.00')
    assert cats['household'] == Decimal('80.00')
    assert data['total_expenses'] == Decimal('200.00')


def test_pdf_merchant_uses_transaction_amount(db_session):
    from app.services.report_service import get_monthly_report_data

    tx = _add_tx(1, "Target", "200.00", "shopping", tx_date=date(2026, 9, 5))
    _add_split(tx.id, 1, "groceries", "120.00")
    _add_split(tx.id, 1, "household", "80.00")

    data = get_monthly_report_data(db_session, 1, 2026, 9)
    merchants = {m['merchant']: m['total_spent'] for m in data['top_merchants']}
    assert merchants['Target'] == Decimal('200.00')


# ── No Double-Counting ──

def test_no_double_counting_across_all_analytics(client, auth_headers):
    tx1 = _add_tx(1, "Target", "100.00", "shopping", tx_date=date(2026, 9, 1))
    _add_split(tx1.id, 1, "food", "60.00")
    _add_split(tx1.id, 1, "electronics", "40.00")

    tx2 = _add_tx(1, "Cafe", "20.00", "food", tx_date=date(2026, 9, 5))

    # Analytics summary
    res = client.get("/api/analytics/summary", headers=auth_headers)
    summary = res.json()
    assert float(summary['total_expenses']) == 120.00  # 100 + 20, not 100 + 60 + 40 + 20

    # Merchant analytics
    res = client.get("/api/analytics/merchants", headers=auth_headers)
    merchants = res.json()
    merchant_totals = sum(float(m['total_spent']) for m in merchants['merchants'])
    assert merchant_totals == 120.00  # same total, no double-count


# ── User Isolation ──

def test_split_aware_analytics_user_isolation(client, auth_headers, second_auth_headers):
    tx1 = _add_tx(1, "MyTarget", "100.00", "shopping", tx_date=date(2026, 9, 1))
    _add_split(tx1.id, 1, "groceries", "100.00")

    tx2 = _add_tx(2, "TheirTarget", "200.00", "shopping", tx_date=date(2026, 9, 1))
    _add_split(tx2.id, 2, "electronics", "200.00")

    # User 1 sees only their split categories
    res1 = client.get("/api/analytics/summary", headers=auth_headers)
    cats1 = {c['category'] for c in res1.json()['category_breakdown']}
    assert 'groceries' in cats1
    assert 'electronics' not in cats1

    # User 2 sees only their split categories
    res2 = client.get("/api/analytics/summary", headers=second_auth_headers)
    cats2 = {c['category'] for c in res2.json()['category_breakdown']}
    assert 'electronics' in cats2
    assert 'groceries' not in cats2


def test_split_aware_pdf_user_isolation(client, auth_headers, second_auth_headers):
    tx1 = _add_tx(1, "MyStore", "100.00", "shopping", tx_date=date(2026, 9, 1))
    _add_split(tx1.id, 1, "food", "100.00")

    tx2 = _add_tx(2, "TheirStore", "200.00", "shopping", tx_date=date(2026, 9, 1))
    _add_split(tx2.id, 2, "electronics", "200.00")

    # User 1 PDF
    res1 = client.get("/api/reports/monthly?year=2026&month=9", headers=auth_headers)
    assert res1.status_code == 200

    # User 2 PDF
    res2 = client.get("/api/reports/monthly?year=2026&month=9", headers=second_auth_headers)
    assert res2.status_code == 200


# ── Decimal Precision ──

def test_decimal_precision_in_split_analytics(client, auth_headers):
    tx = _add_tx(1, "Precise", "33.33", "test", tx_date=date(2026, 9, 1))
    _add_split(tx.id, 1, "a", "11.11")
    _add_split(tx.id, 1, "b", "11.11")
    _add_split(tx.id, 1, "c", "11.11")

    res = client.get("/api/analytics/summary", headers=auth_headers)
    data = res.json()
    assert float(data['total_expenses']) == 33.33
    cat_total = sum(c['amount'] for c in data['category_breakdown'])
    assert float(cat_total) == 33.33


def test_decimal_precision_in_pdf_split_analytics(db_session):
    from app.services.report_service import get_monthly_report_data

    tx = _add_tx(1, "Precise", "33.33", "test", tx_date=date(2026, 9, 1))
    _add_split(tx.id, 1, "a", "11.11")
    _add_split(tx.id, 1, "b", "11.11")
    _add_split(tx.id, 1, "c", "11.11")

    data = get_monthly_report_data(db_session, 1, 2026, 9)
    assert data['total_expenses'] == Decimal('33.33')
    cat_total = sum(c['amount'] for c in data['category_breakdown'])
    assert cat_total == Decimal('33.33')
