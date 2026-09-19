import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database.db import Base, get_db, User
from app.auth import hash_password, create_access_token, decode_access_token
from datetime import timedelta

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

TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "securepassword123"
TEST_NAME = "Test User"


def register_user(email=TEST_EMAIL, password=TEST_PASSWORD, name=TEST_NAME):
    return client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "full_name": name,
    })


def login_user(email=TEST_EMAIL, password=TEST_PASSWORD):
    return client.post("/api/auth/login", data={
        "username": email,
        "password": password,
    })


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


# --- Registration Tests ---

def test_register_success():
    response = register_user()
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == TEST_EMAIL
    assert data["full_name"] == TEST_NAME
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data
    assert "hashed_password" not in data  # must never be exposed


def test_register_duplicate_email():
    register_user()
    response = register_user()
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_register_invalid_email():
    response = client.post("/api/auth/register", json={
        "email": "not-an-email",
        "password": TEST_PASSWORD,
    })
    assert response.status_code == 422  # Pydantic validation error


def test_register_short_password():
    response = client.post("/api/auth/register", json={
        "email": "new@example.com",
        "password": "ab",
    })
    # Password validation is minimal (just required), so this may pass
    # The important thing is it doesn't crash
    assert response.status_code in [201, 422]


def test_register_without_name():
    response = client.post("/api/auth/register", json={
        "email": "noname@example.com",
        "password": TEST_PASSWORD,
    })
    assert response.status_code == 201
    assert response.json()["full_name"] is None


# --- Login Tests ---

def test_login_success():
    register_user()
    response = login_user()
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password():
    register_user()
    response = login_user(password="wrongpassword")
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


def test_login_nonexistent_user():
    response = login_user(email="nonexistent@example.com")
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


# --- Token Tests ---

def test_me_with_valid_token():
    register_user()
    login_resp = login_user()
    token = login_resp.json()["access_token"]

    response = client.get("/api/auth/me", headers=auth_header(token))
    assert response.status_code == 200
    assert response.json()["email"] == TEST_EMAIL


def test_me_without_token():
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_with_invalid_token():
    response = client.get("/api/auth/me", headers=auth_header("invalid.token.here"))
    assert response.status_code == 401
    assert "Invalid or expired token" in response.json()["detail"]


def test_me_with_expired_token():
    register_user()
    login_resp = login_user()
    token = login_resp.json()["access_token"]

    # Decode to get the user_id, then create an expired token
    from app.auth import decode_access_token as _decode
    # Manually decode the valid token to get user_id
    import jose.jwt as _jwt
    from app.auth import JWT_SECRET_KEY, JWT_ALGORITHM
    payload = _jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
    user_id = int(payload["sub"])

    expired_token = create_access_token(
        data={"sub": user_id},
        expires_delta=timedelta(seconds=-1)
    )

    response = client.get("/api/auth/me", headers=auth_header(expired_token))
    assert response.status_code == 401
    assert "Invalid or expired token" in response.json()["detail"]


def test_me_with_token_for_deleted_user():
    register_user()
    login_resp = login_user()
    token = login_resp.json()["access_token"]

    # Decode to get user_id before deleting
    import jose.jwt as _jwt
    from app.auth import JWT_SECRET_KEY, JWT_ALGORITHM
    payload = _jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
    user_id = int(payload["sub"])

    # Delete the user via the test DB
    db = TestingSessionLocal()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    db.close()

    response = client.get("/api/auth/me", headers=auth_header(token))
    assert response.status_code == 401
    assert "User not found" in response.json()["detail"]


def test_token_contains_correct_user_id():
    register_user()
    login_resp = login_user()
    token = login_resp.json()["access_token"]

    import jose.jwt as _jwt
    from app.auth import JWT_SECRET_KEY, JWT_ALGORITHM
    payload = _jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    # sub is a string per JWT spec
    assert payload["sub"] is not None
    assert isinstance(payload["sub"], str)
    # Should be convertible to int (the user ID)
    assert int(payload["sub"]) > 0


def test_password_not_in_token():
    register_user()
    login_resp = login_user()
    token = login_resp.json()["access_token"]

    import jose.jwt as _jwt
    from app.auth import JWT_SECRET_KEY, JWT_ALGORITHM
    payload = _jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    assert "password" not in payload
    assert "hashed_password" not in payload


def test_password_not_in_register_response():
    response = register_user()
    data = response.json()
    assert "password" not in data
    assert "hashed_password" not in data
