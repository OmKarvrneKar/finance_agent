import pytest
import csv
import io
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.database.db import Base, get_db, Transaction

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


def _add_tx(user_id, description, amount, category, tx_date=None, tx_type="debit", source="bank_statement"):
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
            source=source,
        ))
        db.commit()
    finally:
        db.close()


def _parse_csv(content):
    reader = csv.reader(io.StringIO(content))
    return list(reader)


# ── CSV Content Tests ──

def test_csv_content(client, auth_headers):
    today = date.today()
    _add_tx(1, "Starbucks", "7.50", "coffee", tx_date=today)

    res = client.get("/api/transactions/export", headers=auth_headers)
    assert res.status_code == 200
    rows = _parse_csv(res.text)
    assert len(rows) == 2  # header + 1 data row
    assert rows[1][0] == today.isoformat()
    assert rows[1][1] == "Starbucks"
    assert rows[1][3] == "7.50"


# ── CSV Headers Tests ──

def test_csv_headers(client, auth_headers):
    res = client.get("/api/transactions/export", headers=auth_headers)
    assert res.status_code == 200
    rows = _parse_csv(res.text)
    assert rows[0] == ["date", "description", "category", "amount", "transaction_type", "source"]


# ── Filename/Content-Disposition Tests ──

def test_content_disposition(client, auth_headers):
    res = client.get("/api/transactions/export", headers=auth_headers)
    assert res.status_code == 200
    cd = res.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "transactions_export.csv" in cd


def test_content_type(client, auth_headers):
    res = client.get("/api/transactions/export", headers=auth_headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("content-type", "")


# ── Date Filtering Tests ──

def test_date_filtering(client, auth_headers):
    _add_tx(1, "Cafe", "10.00", "food", tx_date=date(2026, 6, 15))
    _add_tx(1, "Cafe", "20.00", "food", tx_date=date(2026, 7, 15))
    _add_tx(1, "Cafe", "30.00", "food", tx_date=date(2026, 8, 15))

    res = client.get("/api/transactions/export?start_date=2026-07-01&end_date=2026-07-31", headers=auth_headers)
    rows = _parse_csv(res.text)
    assert len(rows) == 2  # header + 1 row
    assert rows[1][0] == "2026-07-15"


def test_date_filtering_start_only(client, auth_headers):
    _add_tx(1, "Cafe", "10.00", "food", tx_date=date(2026, 6, 15))
    _add_tx(1, "Cafe", "20.00", "food", tx_date=date(2026, 8, 15))

    res = client.get("/api/transactions/export?start_date=2026-07-01", headers=auth_headers)
    rows = _parse_csv(res.text)
    assert len(rows) == 2  # header + 1 row


# ── Category Filtering Tests ──

def test_category_filtering(client, auth_headers):
    today = date.today()
    _add_tx(1, "Cafe", "10.00", "food", tx_date=today)
    _add_tx(1, "Uber", "15.00", "transport", tx_date=today)

    res = client.get("/api/transactions/export?category=food", headers=auth_headers)
    rows = _parse_csv(res.text)
    assert len(rows) == 2  # header + 1 row
    assert rows[1][2] == "food"


# ── Type Filtering Tests ──

def test_type_filtering(client, auth_headers):
    today = date.today()
    _add_tx(1, "Cafe", "10.00", "food", tx_date=today, tx_type="debit")
    _add_tx(1, "Salary", "5000.00", "income", tx_date=today, tx_type="credit")

    res = client.get("/api/transactions/export?transaction_type=credit", headers=auth_headers)
    rows = _parse_csv(res.text)
    assert len(rows) == 2  # header + 1 row
    assert rows[1][4] == "credit"


# ── Search Filtering Tests ──

def test_search_filtering(client, auth_headers):
    today = date.today()
    _add_tx(1, "Starbucks Coffee", "7.50", "coffee", tx_date=today)
    _add_tx(1, "Amazon", "50.00", "shopping", tx_date=today)

    res = client.get("/api/transactions/export?search=starbucks", headers=auth_headers)
    rows = _parse_csv(res.text)
    assert len(rows) == 2  # header + 1 row
    assert rows[1][1] == "Starbucks Coffee"


# ── Empty Export Tests ──

def test_empty_export(client, auth_headers):
    res = client.get("/api/transactions/export", headers=auth_headers)
    assert res.status_code == 200
    rows = _parse_csv(res.text)
    assert len(rows) == 1  # header only
    assert rows[0] == ["date", "description", "category", "amount", "transaction_type", "source"]


def test_empty_export_with_no_matching_filter(client, auth_headers):
    _add_tx(1, "Cafe", "10.00", "food", tx_date=date.today())

    res = client.get("/api/transactions/export?category=nonexistent", headers=auth_headers)
    rows = _parse_csv(res.text)
    assert len(rows) == 1  # header only


# ── Decimal/Amount Accuracy Tests ──

def test_decimal_accuracy(client, auth_headers):
    today = date.today()
    _add_tx(1, "Cafe", "33.33", "food", tx_date=today)
    _add_tx(1, "Shop", "0.01", "misc", tx_date=today)
    _add_tx(1, "Big", "999999.99", "other", tx_date=today)

    res = client.get("/api/transactions/export", headers=auth_headers)
    rows = _parse_csv(res.text)
    amounts = {row[1]: row[3] for row in rows[1:]}
    assert amounts["Cafe"] == "33.33"
    assert amounts["Shop"] == "0.01"
    assert amounts["Big"] == "999999.99"


# ── User Isolation Tests ──

def test_user_isolation(client, auth_headers, second_auth_headers):
    today = date.today()
    _add_tx(1, "MyTx", "10.00", "food", tx_date=today)
    _add_tx(2, "TheirTx", "20.00", "food", tx_date=today)

    res1 = client.get("/api/transactions/export", headers=auth_headers)
    res2 = client.get("/api/transactions/export", headers=second_auth_headers)

    rows1 = _parse_csv(res1.text)
    rows2 = _parse_csv(res2.text)

    assert len(rows1) == 2  # header + 1
    assert len(rows2) == 2  # header + 1
    assert rows1[1][1] == "MyTx"
    assert rows2[1][1] == "TheirTx"


def test_unauthenticated_returns_401(client):
    res = client.get("/api/transactions/export")
    assert res.status_code in (401, 403)


# ── Multiple Rows Tests ──

def test_multiple_rows_ordering(client, auth_headers):
    _add_tx(1, "First", "10.00", "food", tx_date=date(2026, 1, 1))
    _add_tx(1, "Second", "20.00", "food", tx_date=date(2026, 6, 1))
    _add_tx(1, "Third", "30.00", "food", tx_date=date(2026, 12, 1))

    res = client.get("/api/transactions/export", headers=auth_headers)
    rows = _parse_csv(res.text)
    assert len(rows) == 4  # header + 3 rows
    # ordered by date desc
    assert rows[1][1] == "Third"
    assert rows[2][1] == "Second"
    assert rows[3][1] == "First"


# ── Source Field Tests ──

def test_source_field_included(client, auth_headers):
    today = date.today()
    _add_tx(1, "Cafe", "10.00", "food", tx_date=today, source="manual")

    res = client.get("/api/transactions/export", headers=auth_headers)
    rows = _parse_csv(res.text)
    assert rows[1][5] == "manual"
