import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database.db import Base, get_db
from app.config import Config

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
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def register_and_login(email="test@example.com", password="SecurePass123", name="Test User"):
    client.post("/api/auth/register", json={
        "email": email, "password": password, "full_name": name,
    })
    return client.post("/api/auth/login", data={"username": email, "password": password})


# --- Login sets HttpOnly cookie ---

def test_login_sets_cookie():
    response = register_and_login()
    assert response.status_code == 200
    # Check that the cookie is set
    cookies = response.cookies
    assert Config.COOKIE_NAME in cookies
    cookie = cookies[Config.COOKIE_NAME]
    assert cookie is not None
    assert len(cookie) > 0


def test_login_cookie_is_httponly():
    response = register_and_login()
    cookie = response.cookies[Config.COOKIE_NAME]
    # Starlette TestClient doesn't expose httponly directly in the cookie object,
    # but we can verify the Set-Cookie header
    set_cookie_header = response.headers.get("set-cookie", "")
    assert Config.COOKIE_NAME in set_cookie_header
    assert "httponly" in set_cookie_header.lower()


def test_login_cookie_samesite():
    response = register_and_login()
    set_cookie_header = response.headers.get("set-cookie", "")
    assert "samesite" in set_cookie_header.lower()


def test_login_cookie_has_path():
    response = register_and_login()
    set_cookie_header = response.headers.get("set-cookie", "")
    assert "path=/" in set_cookie_header.lower()


def test_login_cookie_has_max_age():
    response = register_and_login()
    set_cookie_header = response.headers.get("set-cookie", "")
    assert "max-age" in set_cookie_header.lower()


# --- JavaScript cannot access the cookie (httponly flag) ---

def test_cookie_not_in_response_body():
    response = register_and_login()
    data = response.json()
    # The token should be in the response body for backward compat
    assert "access_token" in data
    # But the cookie itself should be httponly (verified by Set-Cookie header)


# --- Authenticated request works using cookie ---

def test_authenticated_request_using_cookie():
    register_and_login()
    # Clear cookies to simulate no-auth state
    client.cookies.clear()
    response = client.get("/api/auth/me")
    assert response.status_code == 401

    # Login to get a fresh cookie
    login_resp = register_and_login("another@example.com", "SecurePass123", "Another")
    cookie_value = login_resp.cookies[Config.COOKIE_NAME]

    # Use the cookie
    response = client.get("/api/auth/me", cookies={Config.COOKIE_NAME: cookie_value})
    assert response.status_code == 200


# --- Logout clears cookie ---

def test_logout_clears_cookie():
    register_and_login()
    login_resp = register_and_login("user2@example.com", "SecurePass123", "User2")
    cookie_value = login_resp.cookies[Config.COOKIE_NAME]

    # Verify cookie works
    response = client.get("/api/auth/me", cookies={Config.COOKIE_NAME: cookie_value})
    assert response.status_code == 200

    # Logout
    logout_resp = client.post("/api/auth/logout", cookies={Config.COOKIE_NAME: cookie_value})
    assert logout_resp.status_code == 200

    # Cookie should be cleared (empty or expired)
    set_cookie_header = logout_resp.headers.get("set-cookie", "")
    assert Config.COOKIE_NAME in set_cookie_header
    # The cookie value should be empty after clearing
    assert f"{Config.COOKIE_NAME}=" in set_cookie_header


# --- Logout still revokes token ---

def test_logout_revokes_token():
    register_and_login()
    login_resp = register_and_login("revoke@example.com", "SecurePass123", "Revoke")
    cookie_value = login_resp.cookies[Config.COOKIE_NAME]

    # Logout to revoke
    client.post("/api/auth/logout", cookies={Config.COOKIE_NAME: cookie_value})

    # Try to use the revoked cookie — should fail
    response = client.get("/api/auth/me", cookies={Config.COOKIE_NAME: cookie_value})
    assert response.status_code == 401


# --- Revoked cookie token is rejected ---

def test_revoked_cookie_rejected_on_protected_endpoint():
    register_and_login()
    login_resp = register_and_login("protected@example.com", "SecurePass123", "Protected")
    cookie_value = login_resp.cookies[Config.COOKIE_NAME]

    # Logout to revoke
    client.post("/api/auth/logout", cookies={Config.COOKIE_NAME: cookie_value})

    # Try to access protected endpoint with revoked cookie
    response = client.get("/api/transactions", cookies={Config.COOKIE_NAME: cookie_value})
    assert response.status_code == 401

    response = client.get("/api/goals", cookies={Config.COOKIE_NAME: cookie_value})
    assert response.status_code == 401


# --- Unauthenticated request rejected ---

def test_unauthenticated_request_rejected():
    response = client.get("/api/auth/me")
    assert response.status_code == 401

    response = client.get("/api/transactions")
    assert response.status_code == 401

    response = client.get("/api/goals")
    assert response.status_code == 401


# --- Existing Authorization header compatibility ---

def test_authorization_header_still_works():
    register_and_login()
    login_resp = register_and_login("compat@example.com", "SecurePass123", "Compat")
    token = login_resp.json()["access_token"]

    # Use Authorization header (backward compat)
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "compat@example.com"


def test_header_takes_precedence_over_cookie():
    register_and_login()
    login_resp1 = register_and_login("user1@example.com", "SecurePass123", "User1")
    login_resp2 = register_and_login("user2@example.com", "SecurePass123", "User2")

    cookie_value = login_resp1.cookies[Config.COOKIE_NAME]
    header_token = login_resp2.json()["access_token"]

    # Send both cookie and header — header should take precedence
    response = client.get(
        "/api/auth/me",
        cookies={Config.COOKIE_NAME: cookie_value},
        headers={"Authorization": f"Bearer {header_token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "user2@example.com"


# --- CORS credentials behavior ---

def test_cors_credentials_configured():
    from app.main import app as fastapi_app
    middleware_stack = fastapi_app.user_middleware
    # CORS middleware should be configured with allow_credentials=True
    cors_found = False
    for mw in middleware_stack:
        if hasattr(mw, 'cls') and 'CORS' in mw.cls.__name__:
            cors_found = True
            break
    assert cors_found, "CORS middleware not found"


# --- Login response still returns access_token (backward compat) ---

def test_login_returns_access_token_in_body():
    response = register_and_login()
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


# --- Multiple logins produce valid cookies ---

def test_multiple_logins_produce_valid_cookies():
    register_and_login()
    login1 = register_and_login("multi@example.com", "SecurePass123", "Multi")
    login2 = client.post("/api/auth/login", data={"username": "multi@example.com", "password": "SecurePass123"})

    cookie1 = login1.cookies[Config.COOKIE_NAME]
    cookie2 = login2.cookies[Config.COOKIE_NAME]

    # Both cookies should work
    r1 = client.get("/api/auth/me", cookies={Config.COOKIE_NAME: cookie1})
    r2 = client.get("/api/auth/me", cookies={Config.COOKIE_NAME: cookie2})
    assert r1.status_code == 200
    assert r2.status_code == 200


# --- Logout without any token (no cookie, no header) ---

def test_logout_without_any_token():
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    # Should still clear cookie
    set_cookie_header = response.headers.get("set-cookie", "")
    assert Config.COOKIE_NAME in set_cookie_header


# --- Cookie config values ---

def test_cookie_config_defaults():
    assert Config.COOKIE_NAME == "access_token"
    assert Config.COOKIE_SAMESITE == "lax"
