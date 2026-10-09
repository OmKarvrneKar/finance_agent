"""Phase 5B: POST /api/transactions — manual transaction creation (backend)."""

from datetime import date

import pytest


BASE_PAYLOAD = {
    "date": "2026-07-01",
    "description": "Corner Store",
    "amount": 10.50,
    "transaction_type": "debit",
    "category": "Shopping",
}


def _payload(**overrides):
    payload = dict(BASE_PAYLOAD)
    payload.update(overrides)
    return payload


def _create(client, headers, **overrides):
    return client.post("/api/transactions", json=_payload(**overrides), headers=headers)


def _notifications(client, headers):
    return client.get("/api/notifications", headers=headers).json()["notifications"]


def _create_account(client, headers, name="Checking"):
    res = client.post(
        "/api/accounts",
        json={"name": name, "account_type": "bank"},
        headers=headers,
    )
    assert res.status_code == 201
    return res.json()["id"]


class TestAuthenticatedCreation:
    def test_unauthenticated_rejected(self, client):
        res = client.post("/api/transactions", json=_payload())
        assert res.status_code == 401

    def test_authenticated_creation_returns_201(self, client, auth_headers):
        res = _create(client, auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert isinstance(data["id"], int)
        assert data["date"] == "2026-07-01"
        assert data["description"] == "Corner Store"
        assert data["transaction_type"] == "debit"
        assert data["category"] == "Shopping"
        assert data["account_id"] is None
        assert data["is_recurring"] is False
        assert data["is_user_confirmed_recurring"] is False
        assert float(data["amount"]) == 10.50

    def test_created_transaction_visible_only_to_owner(self, client, auth_headers, second_auth_headers):
        created = _create(client, auth_headers).json()
        tx_id = created["id"]

        owner_list = client.get("/api/transactions", headers=auth_headers).json()
        assert owner_list["total"] == 1
        assert owner_list["transactions"][0]["id"] == tx_id

        other_list = client.get("/api/transactions", headers=second_auth_headers).json()
        assert other_list["total"] == 0
        assert all(t["id"] != tx_id for t in other_list["transactions"])

    def test_user_id_cannot_be_set_by_client(self, client, auth_headers):
        res = client.post(
            "/api/transactions",
            json=_payload(user_id=999),
            headers=auth_headers,
        )
        assert res.status_code == 422

    def test_unknown_field_rejected(self, client, auth_headers):
        res = client.post(
            "/api/transactions",
            json=_payload(fake_field="value"),
            headers=auth_headers,
        )
        assert res.status_code == 422

    def test_source_cannot_be_spoofed(self, client, auth_headers):
        res = client.post(
            "/api/transactions",
            json=_payload(source="receipt_ocr"),
            headers=auth_headers,
        )
        assert res.status_code == 422


class TestTransactionTypes:
    def test_expense_debit(self, client, auth_headers):
        res = _create(client, auth_headers, transaction_type="debit")
        assert res.status_code == 201
        assert res.json()["transaction_type"] == "debit"

    def test_income_credit(self, client, auth_headers):
        res = _create(
            client, auth_headers,
            transaction_type="credit",
            description="Salary",
            category="Salary/Income",
            amount=2500.00,
        )
        assert res.status_code == 201
        assert res.json()["transaction_type"] == "credit"

    def test_invalid_type_expense_rejected(self, client, auth_headers):
        assert _create(client, auth_headers, transaction_type="expense").status_code == 422

    def test_invalid_type_debit_lowercase_rejected(self, client, auth_headers):
        assert _create(client, auth_headers, transaction_type="Debit").status_code == 422

    def test_invalid_type_credit_mixedcase_rejected(self, client, auth_headers):
        assert _create(client, auth_headers, transaction_type="Credit").status_code == 422

    def test_missing_type_rejected(self, client, auth_headers):
        payload = _payload()
        del payload["transaction_type"]
        assert client.post("/api/transactions", json=payload, headers=auth_headers).status_code == 422


class TestAmountValidation:
    def test_zero_amount_rejected(self, client, auth_headers):
        assert _create(client, auth_headers, amount=0).status_code == 422

    def test_negative_amount_rejected(self, client, auth_headers):
        assert _create(client, auth_headers, amount=-100).status_code == 422

    def test_non_numeric_amount_rejected(self, client, auth_headers):
        assert _create(client, auth_headers, amount="abc").status_code == 422

    def test_missing_amount_rejected(self, client, auth_headers):
        payload = _payload()
        del payload["amount"]
        assert client.post("/api/transactions", json=payload, headers=auth_headers).status_code == 422


class TestCategoryValidation:
    def test_empty_category_rejected(self, client, auth_headers):
        assert _create(client, auth_headers, category="").status_code == 422

    def test_whitespace_category_rejected(self, client, auth_headers):
        assert _create(client, auth_headers, category="   ").status_code == 422

    def test_missing_category_rejected(self, client, auth_headers):
        payload = _payload()
        del payload["category"]
        assert client.post("/api/transactions", json=payload, headers=auth_headers).status_code == 422

    def test_category_is_stripped(self, client, auth_headers):
        res = _create(client, auth_headers, category="  Food & Dining  ")
        assert res.status_code == 201
        assert res.json()["category"] == "Food & Dining"


class TestDecimalPrecision:
    def test_two_decimal_precision_preserved(self, client, auth_headers):
        res = _create(client, auth_headers, amount=123.45)
        assert res.status_code == 201
        assert float(res.json()["amount"]) == 123.45

    def test_string_decimal_amount_accepted(self, client, auth_headers):
        res = _create(client, auth_headers, amount="89.99")
        assert res.status_code == 201
        assert float(res.json()["amount"]) == 89.99

    def test_large_amount_precision_preserved(self, client, auth_headers):
        res = _create(client, auth_headers, amount=1234567.89)
        assert res.status_code == 201
        assert float(res.json()["amount"]) == 1234567.89

    def test_round_trip_through_list_endpoint(self, client, auth_headers):
        _create(client, auth_headers, amount=49.99)
        tx = client.get("/api/transactions", headers=auth_headers).json()["transactions"][0]
        assert float(tx["amount"]) == 49.99


class TestDateHandling:
    def test_valid_date_accepted(self, client, auth_headers):
        res = _create(client, auth_headers, date="2026-08-15")
        assert res.status_code == 201
        assert res.json()["date"] == "2026-08-15"

    def test_invalid_date_rejected(self, client, auth_headers):
        assert _create(client, auth_headers, date="not-a-date").status_code == 422

    def test_slash_date_rejected(self, client, auth_headers):
        assert _create(client, auth_headers, date="07/01/2026").status_code == 422

    def test_missing_date_rejected(self, client, auth_headers):
        payload = _payload()
        del payload["date"]
        assert client.post("/api/transactions", json=payload, headers=auth_headers).status_code == 422


class TestAccountOwnership:
    def test_attach_own_account(self, client, auth_headers):
        account_id = _create_account(client, auth_headers)
        res = _create(client, auth_headers, account_id=account_id)
        assert res.status_code == 201
        assert res.json()["account_id"] == account_id

        listed = client.get("/api/transactions", headers=auth_headers).json()["transactions"][0]
        assert listed["account_id"] == account_id

    def test_foreign_account_rejected(self, client, auth_headers, second_auth_headers):
        foreign_id = _create_account(client, second_auth_headers, name="Other User Bank")

        res = _create(client, auth_headers, account_id=foreign_id)
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."

        assert client.get("/api/transactions", headers=auth_headers).json()["total"] == 0

    def test_nonexistent_account_rejected(self, client, auth_headers):
        res = _create(client, auth_headers, account_id=999999)
        assert res.status_code == 404
        assert client.get("/api/transactions", headers=auth_headers).json()["total"] == 0


class TestNotificationIntegration:
    def test_qualifying_expense_creates_budget_notification(self, client, auth_headers):
        budget = client.post(
            "/api/budgets",
            json={"category": "Food", "monthly_cap": 1000},
            headers=auth_headers,
        )
        assert budget.status_code == 200
        assert _notifications(client, auth_headers) == []

        res = _create(
            client, auth_headers,
            date=date.today().isoformat(),
            description="Rent",
            category="Food",
            amount=1400,
        )
        assert res.status_code == 201

        notes = _notifications(client, auth_headers)
        assert len(notes) == 1
        assert notes[0]["type"] == "budget_exceeded"
        assert notes[0]["severity"] == "critical"

    def test_repeated_qualifying_creation_does_not_duplicate(self, client, auth_headers):
        client.post(
            "/api/budgets",
            json={"category": "Food", "monthly_cap": 1000},
            headers=auth_headers,
        )
        first = _create(
            client, auth_headers,
            date=date.today().isoformat(),
            description="Rent",
            category="Food",
            amount=1400,
        )
        second = _create(
            client, auth_headers,
            date=date.today().isoformat(),
            description="Groceries",
            category="Food",
            amount=500,
        )
        assert first.status_code == second.status_code == 201

        notes = _notifications(client, auth_headers)
        assert len(notes) == 1
        assert notes[0]["type"] == "budget_exceeded"

    def test_non_qualifying_creation_creates_nothing(self, client, auth_headers):
        res = _create(client, auth_headers)
        assert res.status_code == 201
        assert _notifications(client, auth_headers) == []


class TestSplitIntegration:
    def test_created_transaction_accepts_existing_splits(self, client, auth_headers):
        created = _create(client, auth_headers, amount=100.00, category="Food").json()
        tx_id = created["id"]

        res = client.post(
            f"/api/transactions/{tx_id}/splits",
            json=[
                {"category": "Food", "amount": 60},
                {"category": "Transport", "amount": 40},
            ],
            headers=auth_headers,
        )
        assert res.status_code == 201
        assert len(res.json()) == 2

        summary = client.get(
            f"/api/transactions/{tx_id}/split-summary",
            headers=auth_headers,
        ).json()
        assert summary["is_split"] is True
        assert float(summary["split_total"]) == 100.00
