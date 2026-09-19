import pytest
import io
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database.db import Base, get_db
from PIL import Image

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

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

def _create_test_image(width=100, height=100, color='white'):
    img = Image.new('RGB', (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

def _create_corrupt_image():
    buf = io.BytesIO(b"NOT_AN_IMAGE_RANDOM_BYTES")
    buf.seek(0)
    return buf

@patch('app.routers.receipts.receipts.extract_receipt_text')
@patch('app.routers.receipts.receipts.parse_receipt_with_ai')
def test_upload_png_succeeds(mock_parse, mock_extract):
    mock_extract.return_value = "Starbucks receipt"
    mock_parse.return_value = {"merchant": "Starbucks", "date": "2026-07-10", "amount": 5.40, "category": "Food", "needs_review": False}

    img_buf = _create_test_image()
    response = client.post(
        "/api/receipts/upload",
        files={"file": ("receipt.png", img_buf, "image/png")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["merchant"] == "Starbucks"

@patch('app.routers.receipts.receipts.extract_receipt_text')
@patch('app.routers.receipts.receipts.parse_receipt_with_ai')
def test_upload_jpg_succeeds(mock_parse, mock_extract):
    mock_extract.return_value = "receipt text"
    mock_parse.return_value = {"merchant": "Test", "date": "2026-07-10", "amount": 10.0, "category": "Other", "needs_review": False}

    img = Image.new('RGB', (100, 100), 'white')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)

    response = client.post(
        "/api/receipts/upload",
        files={"file": ("receipt.jpg", buf, "image/jpeg")}
    )
    assert response.status_code == 200

def test_upload_rejects_non_image_file():
    response = client.post(
        "/api/receipts/upload",
        files={"file": ("receipt.txt", io.BytesIO(b"hello world"), "text/plain")}
    )
    assert response.status_code == 400

def test_upload_rejects_pdf():
    response = client.post(
        "/api/receipts/upload",
        files={"file": ("receipt.pdf", io.BytesIO(b"%PDF-1.4 fake content"), "application/pdf")}
    )
    assert response.status_code == 400

def test_upload_rejects_corrupt_image():
    corrupt_buf = _create_corrupt_image()
    response = client.post(
        "/api/receipts/upload",
        files={"file": ("receipt.png", corrupt_buf, "image/png")}
    )
    assert response.status_code == 400

def test_upload_rejects_oversized_image():
    large_buf = io.BytesIO(b"\x89PNG\r\n" + b"\x00" * (11 * 1024 * 1024))
    response = client.post(
        "/api/receipts/upload",
        files={"file": ("receipt.png", large_buf, "image/png")}
    )
    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()

def test_upload_rejects_empty_file():
    response = client.post(
        "/api/receipts/upload",
        files={"file": ("receipt.png", io.BytesIO(b""), "image/png")}
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()
