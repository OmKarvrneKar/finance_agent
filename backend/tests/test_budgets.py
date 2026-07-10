import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.db import Base, Transaction, BudgetGoal, SavingsGoal
from app.services.budgets import get_budget_status, simulate_what_if

engine = create_engine('sqlite:///:memory:')
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

def test_budget_status_on_track(db):
    bg = BudgetGoal(category="Food", monthly_cap=100.0)
    db.add(bg)
    t = Transaction(date=date.today(), description="Burger", amount=10, transaction_type="debit", category="Food")
    db.add(t)
    db.commit()
    
    status = get_budget_status(db)
    assert len(status) == 1
    assert status[0]["category"] == "Food"
    assert status[0]["status"] == "on_track"

def test_budget_status_over(db):
    bg = BudgetGoal(category="Food", monthly_cap=100.0)
    db.add(bg)
    t = Transaction(date=date.today(), description="Lobster", amount=150, transaction_type="debit", category="Food")
    db.add(t)
    db.commit()
    
    status = get_budget_status(db)
    assert status[0]["status"] == "over"

def test_budget_status_approaching(db):
    bg = BudgetGoal(category="Food", monthly_cap=100.0)
    db.add(bg)
    t = Transaction(date=date.today(), description="Groceries", amount=85, transaction_type="debit", category="Food")
    db.add(t)
    db.commit()
    
    status = get_budget_status(db)
    assert status[0]["status"] == "approaching"

def test_simulate_what_if_no_data(db):
    res = simulate_what_if(db, category="Food", percent_change=-20.0)
    assert "error" in res
    assert res["error"] == "insufficient data"

def test_simulate_what_if_normal(db):
    # Add historical data
    h1 = Transaction(date=date(2025, 1, 10), description="old", amount=100, transaction_type="debit", category="Food")
    h2 = Transaction(date=date(2025, 2, 10), description="old", amount=100, transaction_type="debit", category="Food")
    h3 = Transaction(date=date(2025, 3, 10), description="old", amount=100, transaction_type="debit", category="Food")
    db.add_all([h1, h2, h3])
    
    sg = SavingsGoal(name="Car", target_amount=240.0)
    db.add(sg)
    db.commit()
    
    res = simulate_what_if(db, category="Food", percent_change=-20.0, months=12, goal_name="Car")
    
    assert "error" not in res
    assert res["baseline_monthly_spend"] == 100.0
    assert res["new_monthly_spend"] == 80.0
    assert res["monthly_delta"] == 20.0
    assert res["projected_total_over_period"] == 240.0
    assert res["months_to_goal"] == 12.0
