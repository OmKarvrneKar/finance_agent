import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.database.db import Base, get_db, Transaction, BudgetGoal, SavingsGoal
from app.services.report_service import get_monthly_report_data

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


def _add_tx(user_id, description, amount, category, tx_date=None, tx_type="debit", is_recurring=False):
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
            is_recurring=is_recurring,
        ))
        db.commit()
    finally:
        db.close()


def _add_budget(user_id, category, monthly_cap):
    db = TestingSessionLocal()
    try:
        db.add(BudgetGoal(user_id=user_id, category=category, monthly_cap=Decimal(str(monthly_cap))))
        db.commit()
    finally:
        db.close()


def _add_goal(user_id, name, target, current, status="active"):
    db = TestingSessionLocal()
    try:
        db.add(SavingsGoal(user_id=user_id, name=name, target_amount=Decimal(str(target)), current_amount=Decimal(str(current)), status=status))
        db.commit()
    finally:
        db.close()


# ── Authentication Tests ──

def test_unauthenticated_returns_401(client):
    res = client.get("/api/reports/monthly?year=2026&month=9")
    assert res.status_code in (401, 403)


# ── User Isolation Tests (data service) ──

def test_user_isolation(db_session):
    _add_tx(1, "MyIncome", "5000.00", "income", tx_date=date(2026, 9, 1), tx_type="credit")
    _add_tx(2, "TheirIncome", "8000.00", "income", tx_date=date(2026, 9, 1), tx_type="credit")

    data1 = get_monthly_report_data(db_session, 1, 2026, 9)
    data2 = get_monthly_report_data(db_session, 2, 2026, 9)

    assert data1['total_income'] == Decimal('5000.00')
    assert data2['total_income'] == Decimal('8000.00')


# ── Valid Month Tests ──

def test_valid_month_returns_pdf(client, auth_headers):
    _add_tx(1, "Cafe", "10.00", "food", tx_date=date(2026, 7, 15))
    res = client.get("/api/reports/monthly?year=2026&month=7", headers=auth_headers)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"


# ── Invalid Month/Year Tests ──

def test_invalid_month(client, auth_headers):
    res = client.get("/api/reports/monthly?year=2026&month=13", headers=auth_headers)
    assert res.status_code == 422

def test_invalid_month_zero(client, auth_headers):
    res = client.get("/api/reports/monthly?year=2026&month=0", headers=auth_headers)
    assert res.status_code == 422


def test_missing_year(client, auth_headers):
    res = client.get("/api/reports/monthly?month=9", headers=auth_headers)
    assert res.status_code == 422


def test_missing_month(client, auth_headers):
    res = client.get("/api/reports/monthly?year=2026", headers=auth_headers)
    assert res.status_code == 422


# ── Empty Month Tests ──

def test_empty_month_returns_valid_pdf(client, auth_headers):
    res = client.get("/api/reports/monthly?year=2025&month=3", headers=auth_headers)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert b"%PDF" in res.content


# ── Income/Expense Totals Tests (data service) ──

def test_income_expense_totals(db_session):
    _add_tx(1, "Salary", "10000.00", "income", tx_date=date(2026, 9, 1), tx_type="credit")
    _add_tx(1, "Cafe", "50.00", "food", tx_date=date(2026, 9, 5))
    _add_tx(1, "Uber", "30.00", "transport", tx_date=date(2026, 9, 10))

    data = get_monthly_report_data(db_session, 1, 2026, 9)
    assert data['total_income'] == Decimal('10000.00')
    assert data['total_expenses'] == Decimal('80.00')
    assert data['net_cashflow'] == Decimal('9920.00')
    assert data['transaction_count'] == 3


# ── Category Totals Tests (data service) ──

def test_category_totals(db_session):
    _add_tx(1, "Cafe", "25.00", "food", tx_date=date(2026, 9, 5))
    _add_tx(1, "Restaurant", "35.00", "food", tx_date=date(2026, 9, 8))
    _add_tx(1, "Uber", "15.00", "transport", tx_date=date(2026, 9, 10))

    data = get_monthly_report_data(db_session, 1, 2026, 9)
    cats = {c['category']: c['amount'] for c in data['category_breakdown']}
    assert cats['food'] == Decimal('60.00')
    assert cats['transport'] == Decimal('15.00')


# ── Merchant Totals Tests (data service) ──

def test_merchant_totals(db_session):
    _add_tx(1, "Starbucks", "7.50", "coffee", tx_date=date(2026, 9, 1))
    _add_tx(1, "Starbucks", "12.00", "coffee", tx_date=date(2026, 9, 15))

    data = get_monthly_report_data(db_session, 1, 2026, 9)
    merchants = {m['merchant']: m['total_spent'] for m in data['top_merchants']}
    assert merchants['Starbucks'] == Decimal('19.50')


# ── PDF Response/Content Type Tests ──

def test_pdf_content_type(client, auth_headers):
    res = client.get("/api/reports/monthly?year=2026&month=9", headers=auth_headers)
    assert res.headers["content-type"] == "application/pdf"


def test_pdf_starts_with_magic_bytes(client, auth_headers):
    res = client.get("/api/reports/monthly?year=2026&month=9", headers=auth_headers)
    assert res.content[:5] == b"%PDF-"


# ── Content-Disposition Filename Tests ──

def test_content_disposition_filename(client, auth_headers):
    res = client.get("/api/reports/monthly?year=2026&month=9", headers=auth_headers)
    cd = res.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "financial_report_2026_09.pdf" in cd


def test_content_disposition_filename_january(client, auth_headers):
    res = client.get("/api/reports/monthly?year=2025&month=1", headers=auth_headers)
    cd = res.headers.get("content-disposition", "")
    assert "financial_report_2025_01.pdf" in cd


# ── No Cross-User Data Leakage Tests (data service) ──

def test_no_cross_user_data(db_session):
    _add_tx(1, "MyExpense", "100.00", "food", tx_date=date(2026, 9, 1))
    _add_tx(2, "TheirExpense", "200.00", "food", tx_date=date(2026, 9, 1))

    data1 = get_monthly_report_data(db_session, 1, 2026, 9)
    data2 = get_monthly_report_data(db_session, 2, 2026, 9)

    merchants1 = [m['merchant'] for m in data1['top_merchants']]
    merchants2 = [m['merchant'] for m in data2['top_merchants']]
    assert 'MyExpense' in merchants1
    assert 'TheirExpense' not in merchants1
    assert 'TheirExpense' in merchants2
    assert 'MyExpense' not in merchants2


# ── Recurring Expenses Tests (data service) ──

def test_recurring_expenses(db_session):
    _add_tx(1, "Netflix", "15.00", "entertainment", tx_date=date(2026, 9, 1), is_recurring=True)
    _add_tx(1, "Cafe", "10.00", "food", tx_date=date(2026, 9, 5), is_recurring=False)

    data = get_monthly_report_data(db_session, 1, 2026, 9)
    rec_descs = [r['description'] for r in data['recurring_expenses']]
    assert 'Netflix' in rec_descs
    assert 'Cafe' not in rec_descs


# ── Budget Status Tests (data service) ──

def test_budget_status(db_session):
    _add_budget(1, "food", "200.00")
    _add_tx(1, "Cafe", "50.00", "food", tx_date=date(2026, 9, 5))

    data = get_monthly_report_data(db_session, 1, 2026, 9)
    assert len(data['budget_status']) == 1
    b = data['budget_status'][0]
    assert b['category'] == 'food'
    assert b['monthly_cap'] == Decimal('200.00')
    assert b['spent'] == Decimal('50.00')
    assert b['remaining'] == Decimal('150.00')


# ── Savings Goal Progress Tests (data service) ──

def test_savings_progress(db_session):
    _add_goal(1, "Emergency Fund", "10000.00", "3000.00")

    data = get_monthly_report_data(db_session, 1, 2026, 9)
    assert len(data['savings_progress']) == 1
    g = data['savings_progress'][0]
    assert g['name'] == 'Emergency Fund'
    assert g['target_amount'] == Decimal('10000.00')
    assert g['current_amount'] == Decimal('3000.00')
    assert g['progress_percent'] == 30.0
