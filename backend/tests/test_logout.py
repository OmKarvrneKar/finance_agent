import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database.db import Base, get_db, User, RevokedToken
from app.auth import create_access_token, revoke_token, is_token_revoked, JWT_SECRET_KEY, JWT_ALGORITHM
import jose.jwt as _jwt

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
    from app.dependencies import _rate_store
    _rate_store.clear()
    client.cookies.clear()
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def register_and_login(email="test@example.com", password="SecurePass123", name="Test User"):
    client.post("/api/auth/register", json={
        "email": email, "password": password, "full_name": name,
    })
    res = client.post("/api/auth/login", data={"username": email, "password": password})
    return res.json()["access_token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def decode_token_payload(token):
    return _jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})


# --- Logout endpoint tests ---

def test_logout_success():
    token = register_and_login()
    response = client.post("/api/auth/logout", headers=auth_header(token))
    assert response.status_code == 200
    assert response.json()["detail"] == "Successfully logged out"


def test_logout_without_token():
    response = client.post("/api/auth/logout")
    assert response.status_code == 200  # idempotent — no token is fine
    assert response.json()["detail"] == "Successfully logged out"


def test_logout_with_invalid_token():
    response = client.post("/api/auth/logout", headers=auth_header("invalid.token.here"))
    assert response.status_code == 200  # idempotent — nothing to revoke


# --- Token valid before logout ---

def test_token_works_before_logout():
    token = register_and_login()
    response = client.get("/api/auth/me", headers=auth_header(token))
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


# --- Token rejected after logout ---

def test_token_rejected_after_logout():
    token = register_and_login()
    # Verify token works
    response = client.get("/api/auth/me", headers=auth_header(token))
    assert response.status_code == 200

    # Logout
    client.post("/api/auth/logout", headers=auth_header(token))

    # Same token should be rejected
    response = client.get("/api/auth/me", headers=auth_header(token))
    assert response.status_code == 401
    assert "revoked" in response.json()["detail"].lower()


# --- Revoked token cannot access protected endpoints ---

def test_revoked_token_cannot_access_transactions():
    token = register_and_login()
    # Logout to revoke
    client.post("/api/auth/logout", headers=auth_header(token))
    # Try to access protected endpoint
    response = client.get("/api/transactions", headers=auth_header(token))
    assert response.status_code == 401


def test_revoked_token_cannot_access_goals():
    token = register_and_login()
    client.post("/api/auth/logout", headers=auth_header(token))
    response = client.get("/api/goals", headers=auth_header(token))
    assert response.status_code == 401


def test_revoked_token_cannot_access_analytics():
    token = register_and_login()
    client.post("/api/auth/logout", headers=auth_header(token))
    response = client.get("/api/analytics/summary", headers=auth_header(token))
    assert response.status_code == 401


# --- Another user's token is unaffected ---

def test_other_user_token_unaffected():
    token1 = register_and_login("user1@example.com", "SecurePass123", "User 1")
    token2 = register_and_login("user2@example.com", "SecurePass123", "User 2")

    # Logout user1
    client.post("/api/auth/logout", headers=auth_header(token1))

    # user1's token should be revoked
    response = client.get("/api/auth/me", headers=auth_header(token1))
    assert response.status_code == 401

    # user2's token should still work
    response = client.get("/api/auth/me", headers=auth_header(token2))
    assert response.status_code == 200
    assert response.json()["email"] == "user2@example.com"


# --- Expired token behavior ---

def test_expired_token_rejected():
    token = register_and_login()
    # Create an expired token with a valid jti
    payload = decode_token_payload(token)
    expired_token = create_access_token(
        data={"sub": int(payload["sub"])},
        expires_delta=timedelta(seconds=-1)
    )
    response = client.get("/api/auth/me", headers=auth_header(expired_token))
    assert response.status_code == 401


# --- Logout when already logged out (token already revoked) ---

def test_logout_already_logged_out():
    token = register_and_login()
    # First logout
    response = client.post("/api/auth/logout", headers=auth_header(token))
    assert response.status_code == 200

    # Second logout with same token — should still succeed (idempotent)
    response = client.post("/api/auth/logout", headers=auth_header(token))
    assert response.status_code == 200


# --- jti claim presence ---

def test_token_contains_jti():
    token = register_and_login()
    payload = decode_token_payload(token)
    assert "jti" in payload
    assert isinstance(payload["jti"], str)
    assert len(payload["jti"]) == 32  # uuid4 hex


# --- revoke_token / is_token_revoked unit tests ---

def test_revoke_token_adds_to_db():
    token = register_and_login()
    payload = decode_token_payload(token)
    db = TestingSessionLocal()
    try:
        revoke_token(payload["jti"], int(payload["sub"]), db)
        assert is_token_revoked(payload["jti"], db)
    finally:
        db.close()


def test_is_token_revoked_returns_false_for_unknown():
    db = TestingSessionLocal()
    try:
        assert not is_token_revoked("nonexistent-jti", db)
    finally:
        db.close()


def test_revoke_token_idempotent():
    token = register_and_login()
    payload = decode_token_payload(token)
    db = TestingSessionLocal()
    try:
        revoke_token(payload["jti"], int(payload["sub"]), db)
        revoke_token(payload["jti"], int(payload["sub"]), db)  # second call should not fail
        assert is_token_revoked(payload["jti"], db)
        # Should only have one record
        count = db.query(RevokedToken).filter(RevokedToken.jti == payload["jti"]).count()
        assert count == 1
    finally:
        db.close()


# --- Migration file exists and is syntactically valid ---

def test_migration_004_exists():
    import os
    migration_path = os.path.join(
        os.path.dirname(__file__), "..", "alembic", "versions", "004_add_revoked_tokens.py"
    )
    assert os.path.exists(migration_path)
    with open(migration_path) as f:
        content = f.read()
    assert "upgrade" in content
    assert "downgrade" in content
    assert "revoked_tokens" in content
    assert "jti" in content
    assert "user_id" in content


# --- Multiple tokens, revoke one ---

def test_revoke_one_token_other_works():
    token1 = register_and_login("user@example.com", "SecurePass123", "User")
    # Login again to get a second token
    res = client.post("/api/auth/login", data={"username": "user@example.com", "password": "SecurePass123"})
    token2 = res.json()["access_token"]

    # Both tokens should work
    assert client.get("/api/auth/me", headers=auth_header(token1)).status_code == 200
    assert client.get("/api/auth/me", headers=auth_header(token2)).status_code == 200

    # Logout with token1 (revokes token1)
    client.post("/api/auth/logout", headers=auth_header(token1))

    # token1 should be revoked
    assert client.get("/api/auth/me", headers=auth_header(token1)).status_code == 401
    # token2 should still work
    assert client.get("/api/auth/me", headers=auth_header(token2)).status_code == 200
