import pytest
from unittest.mock import patch
from app.services.receipts import parse_receipt_with_ai

@patch('app.services.receipts.client.chat.completions.create')
def test_parse_clean_receipt(mock_create):
    class MockMessage:
        def __init__(self, content):
            self.content = content
            
    class MockChoice:
        def __init__(self, message):
            self.message = message
            
    class MockResponse:
        def __init__(self, choices):
            self.choices = choices
            
    mock_create.return_value = MockResponse([
        MockChoice(MockMessage('{"merchant": "Starbucks", "date": "2026-07-10", "amount": 5.40, "category": "Food & Dining", "needs_review": false}'))
    ])
    
    res = parse_receipt_with_ai("Starbucks\nTotal: 5.40\nJuly 10, 2026")
    assert res["merchant"] == "Starbucks"
    assert res["amount"] == 5.40
    assert res["needs_review"] is False

@patch('app.services.receipts.client.chat.completions.create')
def test_parse_messy_receipt(mock_create):
    class MockMessage:
        def __init__(self, content):
            self.content = content
            
    class MockChoice:
        def __init__(self, message):
            self.message = message
            
    class MockResponse:
        def __init__(self, choices):
            self.choices = choices
            
    mock_create.return_value = MockResponse([
        MockChoice(MockMessage('{"merchant": null, "date": null, "amount": null, "category": null, "needs_review": true}'))
    ])
    
    res = parse_receipt_with_ai("ajdfjalkd jfakldfj  totla")
    assert res["needs_review"] is True
    assert res["amount"] is None

def test_parse_empty_text():
    res = parse_receipt_with_ai("")
    assert res["needs_review"] is True
    assert "error" in res
