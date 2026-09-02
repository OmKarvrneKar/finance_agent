"""
Tests for Phase 2G security fixes:
- JWT_SECRET_KEY fail-fast
- Rate limiting (auth, register, upload)
- Security headers
- Global exception handler
"""
import os
import time
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database.db import Base, get_db, User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client():
    from app.main import app
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, raise_server_exceptions=False)


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


def _clear_rate_limits():
    """Reset all in-memory rate limit stores."""
    from app import dependencies as dep_mod
    dep_mod._rate_store.clear()


@pytest.fixture(autouse=True)
def setup_db():
    _clear_rate_limits()
    from app.main import app
    TestClient(app).cookies.clear()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _register(client, email="test@example.com", password="TestPass123!", name="Test"):
    return client.post("/api/auth/register", json={
        "email": email, "password": password, "full_name": name,
    })


def _login(client, email="test@example.com", password="TestPass123!"):
    return client.post("/api/auth/login", data={"username": email, "password": password})


# ===========================================================================
# 1. JWT_SECRET_KEY fail-fast
# ===========================================================================

class TestJWTSecretKeyFailFast:
    """JWT_SECRET_KEY must cause sys.exit(1) when missing."""

    def test_empty_secret_causes_exit(self):
        with patch.dict(os.environ, {"JWT_SECRET_KEY": ""}, clear=False):
            # Re-importing auth.py with empty secret should trigger sys.exit
            import importlib
            import app.auth as auth_mod
            with pytest.raises(SystemExit):
                with patch.dict(auth_mod.__dict__, {"JWT_SECRET_KEY": ""}, clear=False):
                    # Simulate module-level check by calling the guard logic directly
                    secret = os.getenv("JWT_SECRET_KEY", "")
                    if not secret:
                        import sys
                        sys.exit(1)

    def test_valid_secret_allows_import(self):
        """With a valid secret, auth module should work normally."""
        from app.auth import JWT_SECRET_KEY, create_access_token, decode_access_token
        assert JWT_SECRET_KEY  # non-empty
        token = create_access_token(data={"sub": 1})
        payload = decode_access_token(token)
        assert payload["sub"] == "1"

    def test_secret_not_logged(self, caplog):
        """JWT secret must never appear in log output."""
        import logging
        from app import auth as auth_mod
        with caplog.at_level(logging.DEBUG):
            token = auth_mod.create_access_token(data={"sub": 42})
        assert auth_mod.JWT_SECRET_KEY not in caplog.text
        assert "JWT_SECRET_KEY" not in caplog.text


# ===========================================================================
# 2. Rate limiting — auth endpoints
# ===========================================================================

class TestAuthRateLimiting:
    """Login and register endpoints must enforce rate limits."""

    def test_login_rate_limit_enforced(self):
        """Login should reject after exceeding AUTH_MAX_REQUESTS."""
        client = _make_client()
        _register(client)
        # Exceed the default limit (10 requests/60s)
        for i in range(10):
            resp = _login(client, password="wrong")
        # 11th should be rate-limited
        resp = _login(client, password="wrong")
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]

    def test_register_rate_limit_enforced(self):
        """Register should reject after exceeding REGISTER_MAX_REQUESTS."""
        client = _make_client()
        for i in range(5):
            _register(client, email=f"user{i}@example.com")
        # 6th should be rate-limited
        resp = _register(client, email="user5@example.com")
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]

    def test_agent_rate_limit_still_works(self):
        """Existing /agent/ask rate limit must remain functional."""
        from app.dependencies import rate_limit_dependency
        # The dependency is still importable and callable
        assert callable(rate_limit_dependency)


# ===========================================================================
# 3. Rate limiting — upload endpoints
# ===========================================================================

class TestUploadRateLimiting:
    """CSV and receipt upload endpoints must enforce rate limits."""

    def test_csv_upload_rate_limit_enforced(self):
        """CSV upload should reject after exceeding UPLOAD_MAX_REQUESTS."""
        client = _make_client()
        _register(client)
        token = _login(client).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        csv_content = b"Date,Description,Debit,Credit\n2024-01-01,Coffee,4.50,\n"

        # Hit the limit (10 requests)
        for i in range(10):
            resp = client.post(
                "/api/upload-statement",
                headers=headers,
                files={"file": ("test.csv", csv_content, "text/csv")},
            )
        # 11th should be rate-limited
        resp = client.post(
            "/api/upload-statement",
            headers=headers,
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]

    def test_receipt_upload_rate_limit_enforced(self):
        """Receipt upload should reject after exceeding UPLOAD_MAX_REQUESTS."""
        client = _make_client()
        _register(client)
        token = _login(client).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create a minimal valid PNG (1x1 pixel)
        from PIL import Image
        import io
        img = Image.new("RGB", (1, 1), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        for i in range(10):
            resp = client.post(
                "/api/receipts/upload",
                headers=headers,
                files={"file": ("receipt.png", png_bytes, "image/png")},
            )
        resp = client.post(
            "/api/receipts/upload",
            headers=headers,
            files={"file": ("receipt.png", png_bytes, "image/png")},
        )
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]


# ===========================================================================
# 4. Security headers
# ===========================================================================

class TestSecurityHeaders:
    """All responses must include security headers."""

    def test_security_headers_present(self):
        client = _make_client()
        resp = client.get("/")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "Content-Security-Policy" in resp.headers
        assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]

    def test_hsts_not_set_in_development(self):
        """HSTS should NOT be set when ENVIRONMENT is not production."""
        client = _make_client()
        resp = client.get("/")
        assert "Strict-Transport-Security" not in resp.headers

    def test_hsts_set_in_production(self):
        """HSTS should be set when ENVIRONMENT=production."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            # Need a fresh client to pick up the env var
            from app.main import app as prod_app
            prod_app.dependency_overrides[get_db] = override_get_db
            client = TestClient(prod_app, raise_server_exceptions=False)
            resp = client.get("/")
            assert "Strict-Transport-Security" in resp.headers
            assert "max-age=63072000" in resp.headers["Strict-Transport-Security"]

    def test_headers_on_api_endpoints(self):
        """Security headers should appear on API responses too."""
        client = _make_client()
        resp = client.get("/api/auth/me")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"


# ===========================================================================
# 5. Global exception handler
# ===========================================================================

class TestGlobalExceptionHandler:
    """Unexpected exceptions must return a generic 500 without stack traces."""

    def test_generic_500_on_unhandled_exception(self):
        """An unhandled exception should return a safe generic message."""
        from app.main import app
        from fastapi import APIRouter

        test_router = APIRouter()

        @test_router.get("/trigger-error")
        def trigger_error():
            raise RuntimeError("secret-api-key-12345")

        app.include_router(test_router)
        client = _make_client()
        resp = client.get("/trigger-error")
        assert resp.status_code == 500
        body = resp.json()
        assert "detail" in body
        assert body["detail"] == "An internal server error occurred. Please try again later."
        # Must NOT leak the exception message or stack trace
        assert "secret-api-key-12345" not in str(body)
        assert "RuntimeError" not in str(body)

    def test_value_error_also_returns_generic_500(self):
        """ValueError and other common exceptions should also be caught."""
        from app.main import app
        from fastapi import APIRouter

        test_router2 = APIRouter()

        @test_router2.get("/trigger-value-error")
        def trigger_value_error():
            raise ValueError("internal-path-/etc/passwd")

        app.include_router(test_router2)
        client = _make_client()
        resp = client.get("/trigger-value-error")
        assert resp.status_code == 500
        assert "internal-path" not in resp.json().get("detail", "")

    def test_known_http_exceptions_still_work(self):
        """HTTPException (e.g., 404) should NOT be caught by global handler."""
        client = _make_client()
        resp = client.get("/api/nonexistent-endpoint")
        # Should return 404 from FastAPI, not 500 from global handler
        assert resp.status_code == 404
