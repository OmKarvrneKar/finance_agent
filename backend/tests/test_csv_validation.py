import pytest
import io
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database.db import Base, get_db
from datetime import date

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
def setup_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

VALID_CSV = b"Date,Description,Debit,Credit\n2026-07-01,Amazon,49.99,\n2026-07-02,Salary,,2500.00\n"

MOCK_CATEGORIZED = [
    {'date': date(2026, 7, 1), 'description': 'Amazon', 'amount': 49.99, 'transaction_type': 'debit', 'raw_text': '', 'category': 'Shopping', 'subcategory': None, 'is_recurring': False},
    {'date': date(2026, 7, 2), 'description': 'Salary', 'amount': 2500.00, 'transaction_type': 'credit', 'raw_text': '', 'category': 'Salary/Income', 'subcategory': None, 'is_recurring': True},
]

@patch('app.routers.transactions.categorize_transactions')
def test_upload_valid_csv(mock_categorize):
    mock_categorize.return_value = MOCK_CATEGORIZED
    response = client.post(
        "/api/upload-statement",
        files={"file": ("transactions.csv", io.BytesIO(VALID_CSV), "text/csv")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_transactions"] == 2

def test_upload_rejects_non_csv_extension():
    response = client.post(
        "/api/upload-statement",
        files={"file": ("transactions.txt", io.BytesIO(VALID_CSV), "text/csv")}
    )
    assert response.status_code == 400
    assert "Only CSV" in response.json()["detail"]

def test_upload_rejects_oversized_csv():
    large_csv = b"Date,Description,Debit,Credit\n" + b"x" * (6 * 1024 * 1024)
    response = client.post(
        "/api/upload-statement",
        files={"file": ("transactions.csv", io.BytesIO(large_csv), "text/csv")}
    )
    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower() or "5MB" in response.json()["detail"]

def test_upload_rejects_empty_csv():
    response = client.post(
        "/api/upload-statement",
        files={"file": ("transactions.csv", io.BytesIO(b""), "text/csv")}
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()

def test_upload_rejects_malformed_csv_no_headers():
    malformed_csv = b"This is not a CSV file, just random text\nAnother line\n"
    response = client.post(
        "/api/upload-statement",
        files={"file": ("transactions.csv", io.BytesIO(malformed_csv), "text/csv")}
    )
    assert response.status_code == 422
    assert "parsing failed" in response.json()["detail"].lower()

def test_upload_rejects_wrong_columns_csv():
    wrong_cols = b"Name,Address,City\nJohn,123 St,NYC\n"
    response = client.post(
        "/api/upload-statement",
        files={"file": ("transactions.csv", io.BytesIO(wrong_cols), "text/csv")}
    )
    assert response.status_code == 422
    assert "parsing failed" in response.json()["detail"].lower()

@patch('app.routers.transactions.categorize_transactions')
def test_upload_csv_with_ai_categorization(mock_categorize):
    mock_categorize.return_value = MOCK_CATEGORIZED

    response = client.post(
        "/api/upload-statement",
        files={"file": ("transactions.csv", io.BytesIO(VALID_CSV), "text/csv")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_transactions"] == 2
    assert "category_breakdown" in data
    assert "Shopping" in data["category_breakdown"]
