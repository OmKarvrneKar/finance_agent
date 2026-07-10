import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.db import Base, Transaction, AnomalyReview
from app.services.anomalies import detect_recurring_price_jumps, detect_duplicate_charges, detect_unfamiliar_large_merchant, generate_anomaly_report

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

def test_recurring_price_jump(db):
    t1 = Transaction(date=date(2026, 1, 1), description="Netflix", amount=10.0, transaction_type="debit", category="Ent", is_recurring=True)
    t2 = Transaction(date=date(2026, 2, 1), description="Netflix", amount=10.0, transaction_type="debit", category="Ent", is_recurring=True)
    t3 = Transaction(date=date(2026, 3, 1), description="Netflix", amount=15.0, transaction_type="debit", category="Ent", is_recurring=True)
    db.add_all([t1, t2, t3])
    db.commit()
    
    anomalies = detect_recurring_price_jumps(db)
    assert len(anomalies) == 1
    assert anomalies[0]["merchant"] == "Netflix"
    assert anomalies[0]["percent_increase"] == 50.0

def test_duplicate_charges(db):
    t1 = Transaction(date=date(2026, 3, 1), description="Target", amount=45.0, transaction_type="debit", category="Shop", is_recurring=False)
    t2 = Transaction(date=date(2026, 3, 2), description="Target", amount=45.0, transaction_type="debit", category="Shop", is_recurring=False)
    db.add_all([t1, t2])
    db.commit()
    
    anomalies = detect_duplicate_charges(db)
    assert len(anomalies) == 1
    assert anomalies[0]["merchant"] == "Target"
    
def test_duplicate_charges_recurring_short_cycle(db):
    t1 = Transaction(date=date(2026, 3, 1), description="Coffee", amount=5.0, transaction_type="debit", category="Food", is_recurring=True)
    t2 = Transaction(date=date(2026, 3, 2), description="Coffee", amount=5.0, transaction_type="debit", category="Food", is_recurring=True)
    db.add_all([t1, t2])
    db.commit()
    
    anomalies = detect_duplicate_charges(db)
    assert len(anomalies) == 0

def test_unfamiliar_large_merchant(db):
    txs = []
    for i in range(10):
        txs.append(Transaction(date=date(2026, 1, i+1), description=f"Store{i}", amount=10.0, transaction_type="debit", category="Shop", is_recurring=False))
    
    txs.append(Transaction(date=date(2026, 2, 1), description="Rolex", amount=5000.0, transaction_type="debit", category="Shop", is_recurring=False))
    
    db.add_all(txs)
    db.commit()
    
    anomalies = detect_unfamiliar_large_merchant(db, std_dev_multiplier=2.0, min_history_transactions=10)
    assert len(anomalies) == 1
    assert anomalies[0]["merchant"] == "Rolex"

def test_unfamiliar_large_merchant_insufficient_history(db):
    t1 = Transaction(date=date(2026, 2, 1), description="Rolex", amount=5000.0, transaction_type="debit", category="Shop", is_recurring=False)
    db.add(t1)
    db.commit()
    
    anomalies = detect_unfamiliar_large_merchant(db, std_dev_multiplier=2.0, min_history_transactions=10)
    assert len(anomalies) == 0

def test_anomaly_report_dismissal(db):
    t1 = Transaction(date=date(2026, 3, 1), description="Target", amount=45.0, transaction_type="debit", category="Shop", is_recurring=False)
    t2 = Transaction(date=date(2026, 3, 2), description="Target", amount=45.0, transaction_type="debit", category="Shop", is_recurring=False)
    db.add_all([t1, t2])
    db.commit()
    
    rep1 = generate_anomaly_report(db)
    assert len(rep1) == 1
    
    # Dismiss it
    sig = rep1[0]["id"]
    rev = AnomalyReview(anomaly_signature=sig, status="dismissed")
    db.add(rev)
    db.commit()
    
    rep2 = generate_anomaly_report(db)
    assert len(rep2) == 0
