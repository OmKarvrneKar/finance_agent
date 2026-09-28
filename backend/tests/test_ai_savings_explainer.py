import pytest
import json
from unittest.mock import patch, MagicMock
from decimal import Decimal
from datetime import date
from openai import APITimeoutError, APIConnectionError, APIStatusError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.database.db import Base, get_db, Transaction

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
def setup_db(client):
    from app.dependencies import _rate_store
    _rate_store.clear()
    client.cookies.clear()
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def _register_and_login(client, email, password, name):
    client.post("/api/auth/register", json={"email": email, "password": password, "full_name": name})
    res = client.post("/api/auth/login", data={"username": email, "password": password})
    return res.json()["access_token"]


@pytest.fixture
def auth_token(client):
    return _register_and_login(client, "testuser@example.com", "TestPass123", "Test User")


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def second_auth_token(client):
    return _register_and_login(client, "other@example.com", "OtherPass123", "Other User")


@pytest.fixture
def second_auth_headers(second_auth_token):
    return {"Authorization": f"Bearer {second_auth_token}"}


def _add_tx(user_id, description, amount, category, tx_date=None, tx_type="debit"):
    db = TestingSessionLocal()
    try:
        if tx_date is None:
            tx_date = date.today()
        db.add(Transaction(
            user_id=user_id,
            date=tx_date,
            description=description,
            amount=Decimal(str(amount)),
            transaction_type=tx_type,
            category=category,
        ))
        db.commit()
    finally:
        db.close()


def _calc_month_offset(today, i):
    y, m = today.year, today.month - i
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _seed_spending(user_id):
    today = date.today()
    for i in range(4):
        d = _calc_month_offset(today, i)
        _add_tx(user_id, "Rent", "1500", "housing", tx_date=d)
        _add_tx(user_id, "Groceries", "200", "food", tx_date=d)
        _add_tx(user_id, "Starbucks", "7.50", "coffee", tx_date=d)
        for day in [5, 15, 25]:
            _add_tx(user_id, "Starbucks", "7.50", "coffee", tx_date=date(d.year, d.month, min(day, 28)))


def _mock_gemini_success(explanation_text="This is a test explanation.", tips=None):
    if tips is None:
        tips = ["tip 1", "tip 2"]
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "explanations": [
            {
                "recommendation_index": 1,
                "explanation": explanation_text,
                "practical_tips": tips,
            }
        ],
        "summary": "You have good savings potential.",
    })
    return mock_response


# ── Gemini Receives Only Calculated Data ──

def test_gemini_receives_only_calculated_recommendation_data(client, auth_headers):
    _seed_spending(1)

    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_gemini_success()

        res = client.get("/api/savings-recommendations", headers=auth_headers)
        assert res.status_code == 200

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        prompt = messages[0]["content"]

        assert "RECOMMENDATIONS (already calculated):" in prompt
        assert "Type:" in prompt
        assert "Estimated monthly savings:" in prompt
        assert "Supporting data:" in prompt

        assert "user_id" not in prompt
        assert "transaction_id" not in prompt


def test_gemini_prompt_does_not_contain_raw_transaction_data(client, auth_headers):
    _seed_spending(1)

    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_gemini_success()

        res = client.get("/api/savings-recommendations", headers=auth_headers)
        assert res.status_code == 200

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        prompt = messages[0]["content"]

        assert "user_id" not in prompt
        assert "transaction_id" not in prompt
        assert "hashed_password" not in prompt


# ── Gemini Cannot Change Authoritative Savings Amounts ──

def test_gemini_cannot_change_authoritative_savings_amounts(client, auth_headers):
    _seed_spending(1)

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "explanations": [
            {
                "recommendation_index": 1,
                "explanation": "You spend a lot.",
                "practical_tips": ["Spend less"],
            }
        ],
        "summary": "Save money.",
    })

    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_resp

        res1 = client.get("/api/savings-recommendations", headers=auth_headers)

    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get2:
        mock_client2 = MagicMock()
        mock_get2.return_value = mock_client2
        mock_client2.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())

        res2 = client.get("/api/savings-recommendations", headers=auth_headers)

    assert res1.status_code == 200
    assert res2.status_code == 200
    d1 = res1.json()
    d2 = res2.json()
    assert Decimal(str(d1["total_estimated_monthly_savings"])) == Decimal(str(d2["total_estimated_monthly_savings"]))
    assert Decimal(str(d1["total_estimated_annual_savings"])) == Decimal(str(d2["total_estimated_annual_savings"]))
    assert d1["recommendations"] == d2["recommendations"]


# ── AI Failure Does Not Break Deterministic Recommendations ──

def test_ai_timeout_returns_deterministic_recommendations(client, auth_headers):
    _seed_spending(1)

    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())

        res = client.get("/api/savings-recommendations", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["recommendations"]) > 0
        assert data["total_estimated_monthly_savings"] > 0
        assert "ai_error" in data
        assert "timed out" in data["ai_error"].lower()
        assert "ai_summary" in data
        assert len(data["ai_summary"]) > 0


def test_ai_connection_error_returns_deterministic_recommendations(client, auth_headers):
    _seed_spending(1)

    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())

        res = client.get("/api/savings-recommendations", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["recommendations"]) > 0
        assert "ai_error" in data
        assert "connect" in data["ai_error"].lower()


def test_ai_api_error_returns_deterministic_recommendations(client, auth_headers):
    _seed_spending(1)

    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client.chat.completions.create.side_effect = APIStatusError(
            message="server error", response=mock_resp, body=None
        )

        res = client.get("/api/savings-recommendations", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["recommendations"]) > 0
        assert "ai_error" in data


def test_ai_not_configured_returns_deterministic_recommendations(client, auth_headers, monkeypatch):
    _seed_spending(1)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data["recommendations"]) > 0
    assert "ai_error" in data
    assert "not configured" in data["ai_error"].lower()


def test_ai_unexpected_error_returns_deterministic_recommendations(client, auth_headers):
    _seed_spending(1)

    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.side_effect = ValueError("unexpected")

        res = client.get("/api/savings-recommendations", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["recommendations"]) > 0
        assert "ai_error" in data


# ── No-Recommendations Case ──

def test_no_recommendations_returns_useful_ai_summary(client, auth_headers):
    res = client.get("/api/savings-recommendations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["recommendations"] == []
    assert len(data["ai_summary"]) > 0
    assert "not enough" in data["ai_summary"].lower() or "enough" in data["ai_summary"].lower()
    assert "ai_error" not in data
    assert data["ai_explanations"] == []


def test_no_recommendations_does_not_call_gemini(client, auth_headers):
    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get:
        res = client.get("/api/savings-recommendations", headers=auth_headers)
        assert res.status_code == 200
        mock_get.assert_not_called()


# ── User Isolation ──

def test_user_isolation_ai_explanations(client, auth_headers, second_auth_headers):
    _seed_spending(1)
    _seed_spending(2)

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "explanations": [{"recommendation_index": 1, "explanation": "test", "practical_tips": ["tip"]}],
        "summary": "Test summary.",
    })

    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_resp

        res1 = client.get("/api/savings-recommendations", headers=auth_headers)
        res2 = client.get("/api/savings-recommendations", headers=second_auth_headers)

    assert res1.status_code == 200
    assert res2.status_code == 200
    d1 = res1.json()
    d2 = res2.json()

    assert d1["recommendations"] != d2["recommendations"] or d1["categories_analyzed"] == d2["categories_analyzed"]
    assert mock_client.chat.completions.create.call_count == 2


# ── Auth ──

def test_unauthenticated_returns_401(client):
    res = client.get("/api/savings-recommendations")
    assert res.status_code in (401, 403)


# ── AI Success with Valid Response ──

def test_ai_success_populates_explanations(client, auth_headers):
    _seed_spending(1)

    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_gemini_success(
            explanation_text="Housing costs are your largest expense category.",
            tips=["Consider refinancing", "Look into housing assistance programs"],
        )

        res = client.get("/api/savings-recommendations", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["ai_explanations"]) >= 1
        exp = data["ai_explanations"][0]
        assert "recommendation_index" in exp
        assert "explanation" in exp
        assert "practical_tips" in exp
        assert isinstance(exp["practical_tips"], list)
        assert "ai_summary" in data
        assert "ai_error" not in data


def test_ai_success_no_error_field(client, auth_headers):
    _seed_spending(1)

    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_gemini_success()

        res = client.get("/api/savings-recommendations", headers=auth_headers)
        data = res.json()
        assert "ai_error" not in data


# ── Response Structure ──

def test_response_contains_all_expected_fields(client, auth_headers):
    _seed_spending(1)

    with patch("app.services.ai_savings_explainer.get_openrouter_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_gemini_success()

        res = client.get("/api/savings-recommendations", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "recommendations" in data
        assert "total_estimated_monthly_savings" in data
        assert "total_estimated_annual_savings" in data
        assert "categories_analyzed" in data
        assert "merchants_analyzed" in data
        assert "months_of_data" in data
        assert "generated_at" in data
        assert "ai_explanations" in data
        assert "ai_summary" in data
