"""Phase 5C: GET /api/transactions and /api/transactions/export — account scoping."""

BASE_TX = {
    "date": "2026-09-10",
    "description": "Coffee Shop",
    "amount": 100.00,
    "transaction_type": "debit",
    "category": "Food & Dining",
}


def _payload(**overrides):
    payload = dict(BASE_TX)
    payload.update(overrides)
    return payload


def _create_tx(client, headers, **overrides):
    res = client.post("/api/transactions", json=_payload(**overrides), headers=headers)
    assert res.status_code == 201
    return res.json()


def _create_account(client, headers, name):
    res = client.post(
        "/api/accounts",
        json={"name": name, "account_type": "bank"},
        headers=headers,
    )
    assert res.status_code == 201
    return res.json()["id"]


def _seed(client, headers):
    """Account A: 3 txs, Account B: 1 tx, NULL account: 1 tx."""
    acc_a = _create_account(client, headers, "Primary Checking")
    acc_b = _create_account(client, headers, "Credit Card")

    _create_tx(client, headers, date="2026-09-10", description="Coffee Shop",
               amount=100.00, category="Food & Dining", transaction_type="debit",
               account_id=acc_a)
    _create_tx(client, headers, date="2026-06-05", description="Salary Deposit",
               amount=5000.00, category="Salary/Income", transaction_type="credit",
               account_id=acc_a)
    _create_tx(client, headers, date="2026-07-20", description="Coffee Beans",
               amount=300.00, category="Food & Dining", transaction_type="debit",
               account_id=acc_a)
    _create_tx(client, headers, date="2026-08-15", description="Grocery Mart",
               amount=500.00, category="Groceries", transaction_type="debit",
               account_id=acc_b)
    _create_tx(client, headers, date="2026-09-01", description="Cash Withdrawal",
               amount=200.00, category="ATM/Cash", transaction_type="debit")
    return acc_a, acc_b


def _list(client, headers, params=""):
    res = client.get(f"/api/transactions{params}", headers=headers)
    return res


class TestListAccountFilter:
    def test_without_account_id_returns_all_transactions(self, client, auth_headers):
        _seed(client, auth_headers)
        res = _list(client, auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 5
        descriptions = {t["description"] for t in data["transactions"]}
        assert descriptions == {
            "Coffee Shop", "Salary Deposit", "Coffee Beans",
            "Grocery Mart", "Cash Withdrawal",
        }

    def test_account_filter_returns_only_that_account_sorted_desc(
        self, client, auth_headers
    ):
        acc_a, _ = _seed(client, auth_headers)
        data = _list(client, auth_headers, f"?account_id={acc_a}").json()
        assert data["total"] == 3
        assert all(t["account_id"] == acc_a for t in data["transactions"])
        assert [t["date"] for t in data["transactions"]] == [
            "2026-09-10", "2026-07-20", "2026-06-05",
        ]

    def test_account_filter_excludes_null_account_transactions(
        self, client, auth_headers
    ):
        acc_a, _ = _seed(client, auth_headers)
        data = _list(client, auth_headers, f"?account_id={acc_a}").json()
        descriptions = [t["description"] for t in data["transactions"]]
        assert "Cash Withdrawal" not in descriptions
        assert all(t["account_id"] is not None for t in data["transactions"])

    def test_foreign_account_returns_404(self, client, auth_headers, second_auth_headers):
        foreign_acc = _create_account(client, second_auth_headers, "Other User Account")
        res = _list(client, auth_headers, f"?account_id={foreign_acc}")
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."

    def test_nonexistent_account_returns_404(self, client, auth_headers):
        res = _list(client, auth_headers, "?account_id=999999")
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."

    def test_invalid_account_id_rejected(self, client, auth_headers):
        res = _list(client, auth_headers, "?account_id=abc")
        assert res.status_code == 422


class TestListFilterCombinations:
    def test_search_with_account_filter(self, client, auth_headers):
        acc_a, acc_b = _seed(client, auth_headers)
        data = _list(client, auth_headers, f"?account_id={acc_a}&search=coffee").json()
        assert data["total"] == 2
        assert {t["description"] for t in data["transactions"]} == {
            "Coffee Shop", "Coffee Beans",
        }

        data_b = _list(client, auth_headers, f"?account_id={acc_b}&search=coffee").json()
        assert data_b["total"] == 0

    def test_category_with_account_filter(self, client, auth_headers):
        acc_a, _ = _seed(client, auth_headers)
        data = _list(
            client, auth_headers, f"?account_id={acc_a}&category=Food%20%26%20Dining"
        ).json()
        assert data["total"] == 2
        assert all(t["category"] == "Food & Dining" for t in data["transactions"])

        data_none = _list(
            client, auth_headers, f"?account_id={acc_a}&category=Groceries"
        ).json()
        assert data_none["total"] == 0

    def test_date_filter_with_account_filter(self, client, auth_headers):
        acc_a, _ = _seed(client, auth_headers)
        data = _list(
            client, auth_headers,
            f"?account_id={acc_a}&start_date=2026-07-01&end_date=2026-07-31",
        ).json()
        assert data["total"] == 1
        assert data["transactions"][0]["description"] == "Coffee Beans"

    def test_pagination_with_account_filter(self, client, auth_headers):
        acc_a, _ = _seed(client, auth_headers)
        page1 = _list(client, auth_headers, f"?account_id={acc_a}&limit=2&page=1").json()
        assert page1["total"] == 3
        assert page1["pages"] == 2
        assert len(page1["transactions"]) == 2
        assert page1["transactions"][0]["description"] == "Coffee Shop"

        page2 = _list(client, auth_headers, f"?account_id={acc_a}&limit=2&page=2").json()
        assert page2["total"] == 3
        assert len(page2["transactions"]) == 1
        assert page2["transactions"][0]["description"] == "Salary Deposit"

    def test_amount_filter_with_account_filter(self, client, auth_headers):
        acc_a, _ = _seed(client, auth_headers)
        data = _list(
            client, auth_headers, f"?account_id={acc_a}&amount_min=250&amount_max=400"
        ).json()
        assert data["total"] == 1
        assert data["transactions"][0]["description"] == "Coffee Beans"


class TestExportAccountFilter:
    def test_export_without_account_id_includes_all_transactions(
        self, client, auth_headers
    ):
        _seed(client, auth_headers)
        res = client.get("/api/transactions/export", headers=auth_headers)
        assert res.status_code == 200
        for desc in ("Coffee Shop", "Salary Deposit", "Coffee Beans",
                     "Grocery Mart", "Cash Withdrawal"):
            assert desc in res.text

    def test_export_with_account_filter(self, client, auth_headers):
        acc_a, _ = _seed(client, auth_headers)
        res = client.get(
            f"/api/transactions/export?account_id={acc_a}", headers=auth_headers
        )
        assert res.status_code == 200
        for desc in ("Coffee Shop", "Salary Deposit", "Coffee Beans"):
            assert desc in res.text
        assert "Grocery Mart" not in res.text
        assert "Cash Withdrawal" not in res.text

    def test_export_with_search_and_account_filter(self, client, auth_headers):
        acc_a, _ = _seed(client, auth_headers)
        res = client.get(
            f"/api/transactions/export?account_id={acc_a}&search=coffee",
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert "Coffee Shop" in res.text
        assert "Coffee Beans" in res.text
        assert "Salary Deposit" not in res.text

    def test_export_foreign_account_returns_404(
        self, client, auth_headers, second_auth_headers
    ):
        foreign_acc = _create_account(client, second_auth_headers, "Other User Account")
        res = client.get(
            f"/api/transactions/export?account_id={foreign_acc}", headers=auth_headers
        )
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."

    def test_export_nonexistent_account_returns_404(self, client, auth_headers):
        res = client.get(
            "/api/transactions/export?account_id=999999", headers=auth_headers
        )
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."
