import pytest
from unittest.mock import patch, MagicMock
from app.services.receipts import parse_receipt_with_ai

def _make_mock_response(content):
    class MockMessage:
        def __init__(self, content):
            self.content = content
    class MockChoice:
        def __init__(self, message):
            self.message = message
    class MockResponse:
        def __init__(self, choices):
            self.choices = choices
    return MockResponse([MockChoice(MockMessage(content))])

@patch('app.services.receipts.get_openrouter_client')
def test_parse_clean_receipt(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.chat.completions.create.return_value = _make_mock_response(
        '{"merchant": "Starbucks", "date": "2026-07-10", "amount": 5.40, "category": "Food & Dining", "needs_review": false}'
    )
    
    res = parse_receipt_with_ai("Starbucks\nTotal: 5.40\nJuly 10, 2026")
    assert res["merchant"] == "Starbucks"
    assert res["amount"] == 5.40
    assert res["needs_review"] is False

@patch('app.services.receipts.get_openrouter_client')
def test_parse_messy_receipt(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.chat.completions.create.return_value = _make_mock_response(
        '{"merchant": null, "date": null, "amount": null, "category": null, "needs_review": true}'
    )
    
    res = parse_receipt_with_ai("ajdfjalkd jfakldfj  totla")
    assert res["needs_review"] is True
    assert res["amount"] is None

def test_parse_empty_text():
    res = parse_receipt_with_ai("")
    assert res["needs_review"] is True
    assert "error" in res
