import pytest
import time
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database.db import Base, get_db
from app.dependencies import _rate_store, WINDOW_SECONDS, MAX_REQUESTS_PER_WINDOW

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

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_token(client):
    client.post("/api/auth/register", json={
        "email": "testuser@example.com",
        "password": "TestPass123",
        "full_name": "Test User"
    })
    res = client.post("/api/auth/login", data={
        "username": "testuser@example.com",
        "password": "TestPass123"
    })
    return res.json()["access_token"]

@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}

@pytest.fixture(autouse=True)
def clean_rate_store():
    _rate_store.clear()
    yield
    _rate_store.clear()

def test_agent_endpoint_accepts_normal_requests(client, auth_headers):
    response = client.post("/api/agent/ask", json={"question": "What is my balance?"}, headers=auth_headers)
    assert response.status_code in [200, 500, 503]

def test_agent_endpoint_blocks_after_max_requests(client, auth_headers):
    for _ in range(MAX_REQUESTS_PER_WINDOW):
        client.post("/api/agent/ask", json={"question": "test"}, headers=auth_headers)

    response = client.post("/api/agent/ask", json={"question": "test"}, headers=auth_headers)
    assert response.status_code == 429
    assert "Rate limit" in response.json()["detail"]

def test_rate_limit_resets_after_window(client, auth_headers):
    _rate_store["127.0.0.1"] = [time.time() - WINDOW_SECONDS - 1]

    response = client.post("/api/agent/ask", json={"question": "test"}, headers=auth_headers)
    assert response.status_code in [200, 500, 503]

def test_rate_limit_cleans_old_entries(client, auth_headers):
    _rate_store["127.0.0.1"] = [time.time() - WINDOW_SECONDS - 10] * 20

    response = client.post("/api/agent/ask", json={"question": "test"}, headers=auth_headers)
    assert response.status_code in [200, 500, 503]

def test_non_agent_endpoints_not_rate_limited(client, auth_headers):
    for _ in range(MAX_REQUESTS_PER_WINDOW + 5):
        response = client.get("/api/transactions", headers=auth_headers)
        assert response.status_code != 429
