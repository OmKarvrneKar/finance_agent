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

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_rate_store():
    _rate_store.clear()
    yield
    _rate_store.clear()

def test_agent_endpoint_accepts_normal_requests():
    response = client.post("/api/agent/ask", json={"question": "What is my balance?"})
    assert response.status_code in [200, 500, 503]

def test_agent_endpoint_blocks_after_max_requests():
    for _ in range(MAX_REQUESTS_PER_WINDOW):
        client.post("/api/agent/ask", json={"question": "test"})

    response = client.post("/api/agent/ask", json={"question": "test"})
    assert response.status_code == 429
    assert "Rate limit" in response.json()["detail"]

def test_rate_limit_resets_after_window():
    _rate_store["127.0.0.1"] = [time.time() - WINDOW_SECONDS - 1]

    response = client.post("/api/agent/ask", json={"question": "test"})
    assert response.status_code in [200, 500, 503]

def test_rate_limit_cleans_old_entries():
    _rate_store["127.0.0.1"] = [time.time() - WINDOW_SECONDS - 10] * 20

    response = client.post("/api/agent/ask", json={"question": "test"})
    assert response.status_code in [200, 500, 503]

def test_non_agent_endpoints_not_rate_limited():
    for _ in range(MAX_REQUESTS_PER_WINDOW + 5):
        response = client.get("/api/transactions")
        assert response.status_code != 429
