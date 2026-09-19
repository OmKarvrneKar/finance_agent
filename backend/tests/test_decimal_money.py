import pytest
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.db import Base, Transaction, BudgetGoal, SavingsGoal, User
from app.services.csv_parser import parse_bank_csv
from app.services.forecasting import get_daily_run_rate, forecast_month_end_spend
from app.services.budgets import get_budget_status, simulate_what_if
from app.services.anomalies import detect_recurring_price_jumps

engine = create_engine('sqlite:///:memory:')
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

USER_ID = 1

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    user = User(id=USER_ID, email="test@test.com", hashed_password="fake", full_name="Test")
    db.add(user)
    db.commit()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

def test_csv_parser_returns_decimal_amounts():
    csv_content = b"Date,Description,Debit,Credit\n2026-07-01,Amazon,49.99,\n2026-07-02,Salary,,2500.00\n"
    txs = parse_bank_csv(csv_content)
    assert len(txs) == 2
    assert isinstance(txs[0]['amount'], Decimal)
    assert txs[0]['amount'] == Decimal('49.99')
    assert txs[1]['amount'] == Decimal('2500.00')

def test_budget_status_with_decimal_cap(db):
    bg = BudgetGoal(user_id=USER_ID, category="Food", monthly_cap=Decimal('100.00'))
    db.add(bg)
    t = Transaction(user_id=USER_ID, date=date.today(), description="Lunch", amount=Decimal('45.50'), transaction_type="debit", category="Food")
    db.add(t)
    db.commit()
    
    status = get_budget_status(db, USER_ID)
    assert len(status) == 1
    assert status[0]["status"] == "on_track"
    assert status[0]["percent_used"] <= 100.0

def test_budget_status_over_decimal(db):
    bg = BudgetGoal(user_id=USER_ID, category="Shopping", monthly_cap=Decimal('200.00'))
    db.add(bg)
    t = Transaction(user_id=USER_ID, date=date.today(), description="Gadget", amount=Decimal('250.00'), transaction_type="debit", category="Shopping")
    db.add(t)
    db.commit()
    
    status = get_budget_status(db, USER_ID)
    assert status[0]["status"] == "over"

def test_forecasting_with_decimal_amounts(db):
    t1 = Transaction(user_id=USER_ID, date=date(2026, 7, 1), description="Food", amount=Decimal('15.50'), transaction_type="debit", category="Food")
    t2 = Transaction(user_id=USER_ID, date=date(2026, 7, 3), description="Food", amount=Decimal('22.75'), transaction_type="debit", category="Food")
    t3 = Transaction(user_id=USER_ID, date=date(2026, 7, 5), description="Food", amount=Decimal('31.25'), transaction_type="debit", category="Food")
    db.add_all([t1, t2, t3])
    db.commit()
    
    res = get_daily_run_rate("Food", "2026-07", db, USER_ID)
    assert "error" not in res
    assert res["total_spend_so_far"] == Decimal('69.50')
    
    forecast = forecast_month_end_spend("Food", "2026-07", db, USER_ID)
    assert "error" not in forecast
    assert isinstance(forecast["forecasted_total"], Decimal)

def test_anomaly_detection_with_decimal(db):
    t1 = Transaction(user_id=USER_ID, date=date(2026, 1, 1), description="Netflix", amount=Decimal('10.00'), transaction_type="debit", category="Ent", is_recurring=True)
    t2 = Transaction(user_id=USER_ID, date=date(2026, 2, 1), description="Netflix", amount=Decimal('10.00'), transaction_type="debit", category="Ent", is_recurring=True)
    t3 = Transaction(user_id=USER_ID, date=date(2026, 3, 1), description="Netflix", amount=Decimal('15.00'), transaction_type="debit", category="Ent", is_recurring=True)
    db.add_all([t1, t2, t3])
    db.commit()
    
    anomalies = detect_recurring_price_jumps(db, USER_ID)
    assert len(anomalies) == 1
    assert anomalies[0]["percent_increase"] == Decimal('50.00')

def test_savings_goal_with_decimal(db):
    sg = SavingsGoal(user_id=USER_ID, name="Vacation", target_amount=Decimal('3000.00'))
    db.add(sg)
    db.commit()
    
    res = db.query(SavingsGoal).first()
    assert res.target_amount == Decimal('3000.00')

def test_simulate_what_if_decimal(db):
    h1 = Transaction(user_id=USER_ID, date=date(2025, 1, 10), description="old", amount=Decimal('100.00'), transaction_type="debit", category="Food")
    h2 = Transaction(user_id=USER_ID, date=date(2025, 2, 10), description="old", amount=Decimal('100.00'), transaction_type="debit", category="Food")
    h3 = Transaction(user_id=USER_ID, date=date(2025, 3, 10), description="old", amount=Decimal('100.00'), transaction_type="debit", category="Food")
    db.add_all([h1, h2, h3])
    db.commit()
    
    res = simulate_what_if(db, USER_ID, category="Food", percent_change=-20.0)
    assert "error" not in res
    assert isinstance(res["baseline_monthly_spend"], Decimal)
    assert res["new_monthly_spend"] == Decimal('80.00')
