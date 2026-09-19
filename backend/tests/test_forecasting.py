import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.db import Base, Transaction, User
from app.services.forecasting import get_daily_run_rate, forecast_month_end_spend, get_historical_average, generate_overspend_alerts

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

def test_insufficient_transactions(db):
    t1 = Transaction(user_id=USER_ID, date=date(2026, 7, 1), description="test", amount=10, transaction_type="debit", category="Food")
    t2 = Transaction(user_id=USER_ID, date=date(2026, 7, 2), description="test", amount=20, transaction_type="debit", category="Food")
    db.add_all([t1, t2])
    db.commit()
    
    res = get_daily_run_rate("Food", "2026-07", db, USER_ID)
    assert "error" in res
    assert "insufficient data" in res["error"]

def test_normal_month_forecast(db):
    t1 = Transaction(user_id=USER_ID, date=date(2026, 7, 1), description="test", amount=10, transaction_type="debit", category="Food")
    t2 = Transaction(user_id=USER_ID, date=date(2026, 7, 3), description="test", amount=20, transaction_type="debit", category="Food")
    t3 = Transaction(user_id=USER_ID, date=date(2026, 7, 5), description="test", amount=20, transaction_type="debit", category="Food")
    db.add_all([t1, t2, t3])
    db.commit()
    
    res = get_daily_run_rate("Food", "2026-07", db, USER_ID)
    assert "error" not in res
    assert res["total_spend_so_far"] == 50.0
    assert res["days_passed"] == 5
    assert res["daily_run_rate"] == 10.0
    
    forecast = forecast_month_end_spend("Food", "2026-07", db, USER_ID)
    assert forecast["forecasted_total"] == 310.0

def test_no_historical_data(db):
    res = get_historical_average("Food", db, USER_ID, num_past_months=3, exclude_month="2026-07")
    assert "error" in res
    assert "no historical data" in res["error"]

def test_edge_of_month(db):
    t1 = Transaction(user_id=USER_ID, date=date(2026, 2, 1), description="test", amount=10, transaction_type="debit", category="Food")
    t2 = Transaction(user_id=USER_ID, date=date(2026, 2, 15), description="test", amount=20, transaction_type="debit", category="Food")
    t3 = Transaction(user_id=USER_ID, date=date(2026, 2, 28), description="test", amount=54, transaction_type="debit", category="Food")
    db.add_all([t1, t2, t3])
    db.commit()
    
    forecast = forecast_month_end_spend("Food", "2026-02", db, USER_ID)
    assert forecast["forecasted_total"] == 84.0

def test_generate_overspend_alerts(db):
    h1 = Transaction(user_id=USER_ID, date=date(2026, 5, 10), description="old", amount=100, transaction_type="debit", category="Food")
    h2 = Transaction(user_id=USER_ID, date=date(2026, 6, 10), description="old", amount=100, transaction_type="debit", category="Food")
    
    c1 = Transaction(user_id=USER_ID, date=date(2026, 7, 1), description="curr", amount=30, transaction_type="debit", category="Food")
    c2 = Transaction(user_id=USER_ID, date=date(2026, 7, 5), description="curr", amount=30, transaction_type="debit", category="Food")
    c3 = Transaction(user_id=USER_ID, date=date(2026, 7, 10), description="curr", amount=40, transaction_type="debit", category="Food")
    
    db.add_all([h1, h2, c1, c2, c3])
    db.commit()
    
    alerts = generate_overspend_alerts(db, USER_ID, month="2026-07")
    
    food_alert = next((a for a in alerts if a["category"] == "Food"), None)
    assert food_alert is not None
    assert food_alert["historical_average"] == 100.0
    assert food_alert["forecasted_spend"] == 310.0
    assert food_alert["severity"] == "critical"
