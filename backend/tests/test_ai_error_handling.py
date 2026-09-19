import pytest
from unittest.mock import patch, MagicMock
from openai import APITimeoutError, APIConnectionError, APIStatusError
from app.services.agent_service import get_openrouter_client, process_query
from app.services.categorizer import get_openrouter_client as get_categorizer_client
from app.services.receipts import get_openrouter_client as get_receipts_client

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_key")

def test_agent_client_respects_timeout():
    with patch('app.services.agent_service.OpenAI') as mock_openai:
        mock_openai.return_value = MagicMock()
        client = get_openrouter_client()
        assert mock_openai.call_args.kwargs.get('timeout') == 30.0

def test_categorizer_client_respects_timeout():
    with patch('app.services.categorizer.OpenAI') as mock_openai:
        mock_openai.return_value = MagicMock()
        client = get_categorizer_client()
        assert mock_openai.call_args.kwargs.get('timeout') == 60.0

def test_receipts_client_respects_timeout():
    with patch('app.services.receipts.OpenAI') as mock_openai:
        mock_openai.return_value = MagicMock()
        client = get_receipts_client()
        assert mock_openai.call_args.kwargs.get('timeout') == 30.0

def test_agent_handles_timeout_gracefully():
    with patch('app.services.agent_service.get_openrouter_client') as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())
        
        result = process_query("What is my balance?", user_id=1)
        assert "timed out" in result["answer"].lower() or "try again" in result["answer"].lower()

def test_agent_handles_connection_error_gracefully():
    with patch('app.services.agent_service.get_openrouter_client') as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
        
        result = process_query("What is my balance?", user_id=1)
        assert "connect" in result["answer"].lower() or "network" in result["answer"].lower()

def test_agent_handles_429_rate_limit():
    with patch('app.services.agent_service.get_openrouter_client') as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.chat.completions.create.side_effect = APIStatusError(
            message="rate limited", response=mock_response, body=None
        )
        
        result = process_query("What is my balance?", user_id=1)
        assert "rate-limit" in result["answer"].lower() or "rate limit" in result["answer"].lower()

def test_categorizer_handles_timeout():
    with patch('app.services.categorizer.get_openrouter_client') as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())
        
        from app.services.categorizer import categorize_transactions
        with pytest.raises(RuntimeError, match="timed out"):
            categorize_transactions([{'description': 'test', 'amount': 10, 'transaction_type': 'debit'}])

def test_categorizer_handles_connection_error():
    with patch('app.services.categorizer.get_openrouter_client') as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
        
        from app.services.categorizer import categorize_transactions
        with pytest.raises(RuntimeError, match="connect"):
            categorize_transactions([{'description': 'test', 'amount': 10, 'transaction_type': 'debit'}])

def test_receipts_parse_handles_timeout():
    with patch('app.services.receipts.get_openrouter_client') as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())
        
        from app.services.receipts import parse_receipt_with_ai
        result = parse_receipt_with_ai("Starbucks receipt")
        assert result["needs_review"] is True
        assert "timed out" in result["error"].lower()

def test_receipts_parse_handles_connection_error():
    with patch('app.services.receipts.get_openrouter_client') as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
        
        from app.services.receipts import parse_receipt_with_ai
        result = parse_receipt_with_ai("Starbucks receipt")
        assert result["needs_review"] is True
        assert "connect" in result["error"].lower()

def test_receipts_parse_returns_review_on_empty_text():
    from app.services.receipts import parse_receipt_with_ai
    result = parse_receipt_with_ai("")
    assert result["needs_review"] is True
    assert "no text" in result["error"].lower()
