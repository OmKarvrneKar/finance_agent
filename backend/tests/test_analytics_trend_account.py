"""Phase 5D-1: account-scoped spending_trend in GET /api/analytics/summary."""


def _payload(**overrides):
    payload = {
        "date": "2026-09-10",
        "description": "Some Expense",
        "amount": 100.00,
        "transaction_type": "debit",
        "category": "Shopping",
    }
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
    """Account A: 2 debits across 2 months + 1 credit; Account B: 1 debit; NULL: 1 debit."""
    acc_a = _create_account(client, headers, "Primary Checking")
    acc_b = _create_account(client, headers, "Credit Card")

    _create_tx(client, headers, date="2026-08-10", description="A Coffee",
               amount=100.00, account_id=acc_a)
    _create_tx(client, headers, date="2026-09-10", description="A Grocery",
               amount=300.00, account_id=acc_a)
    _create_tx(client, headers, date="2026-09-15", description="Salary",
               amount=5000.00, transaction_type="credit",
               category="Salary/Income", account_id=acc_a)
    _create_tx(client, headers, date="2026-09-05", description="B Shopping",
               amount=500.00, account_id=acc_b)
    _create_tx(client, headers, date="2026-09-01", description="Cash Withdrawal",
               amount=200.00)
    return acc_a, acc_b


def _trend(data):
    return [(t["month"], float(t["amount"])) for t in data["spending_trend"]]


class TestSpendingTrendAccountFilter:
    def test_selected_account_trend_excludes_other_and_null_accounts(
        self, client, auth_headers
    ):
        acc_a, _ = _seed(client, auth_headers)
        res = client.get(
            f"/api/analytics/summary?account_id={acc_a}", headers=auth_headers
        )
        assert res.status_code == 200
        data = res.json()
        assert _trend(data) == [("2026-08", 100.0), ("2026-09", 300.0)]
        # 2026-09 must be only account A: excludes account B (500) and NULL account (200)
        assert float(data["spending_trend"][1]["amount"]) == 300.0
        # main summary remains scoped as before
        assert float(data["total_expenses"]) == 400.0
        assert float(data["total_income"]) == 5000.0
        assert data["transaction_count"] == 3

    def test_unfiltered_trend_includes_all_accounts_and_null_account(
        self, client, auth_headers
    ):
        _seed(client, auth_headers)
        res = client.get("/api/analytics/summary", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        # 2026-09 = 300 (A) + 500 (B) + 200 (NULL)
        assert _trend(data) == [("2026-08", 100.0), ("2026-09", 1000.0)]
        assert float(data["total_expenses"]) == 1100.0
        assert data["transaction_count"] == 5

    def test_second_account_trend_only(self, client, auth_headers):
        _, acc_b = _seed(client, auth_headers)
        res = client.get(
            f"/api/analytics/summary?account_id={acc_b}", headers=auth_headers
        )
        assert res.status_code == 200
        assert _trend(res.json()) == [("2026-09", 500.0)]

    def test_foreign_account_returns_404(
        self, client, auth_headers, second_auth_headers
    ):
        foreign_acc = _create_account(client, second_auth_headers, "Other User Account")
        res = client.get(
            f"/api/analytics/summary?account_id={foreign_acc}", headers=auth_headers
        )
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."

    def test_nonexistent_account_returns_404(self, client, auth_headers):
        res = client.get("/api/analytics/summary?account_id=999999", headers=auth_headers)
        assert res.status_code == 404
        assert res.json()["detail"] == "Account not found."

    def test_user_isolation_other_users_trend_not_visible(
        self, client, auth_headers, second_auth_headers
    ):
        acc_a, _ = _seed(client, auth_headers)
        other_acc = _create_account(client, second_auth_headers, "Other Checking")
        _create_tx(client, second_auth_headers, date="2026-09-20",
                   description="Other User Expense", amount=999.00,
                   account_id=other_acc)

        scoped = client.get(
            f"/api/analytics/summary?account_id={acc_a}", headers=auth_headers
        ).json()
        assert _trend(scoped) == [("2026-08", 100.0), ("2026-09", 300.0)]
        assert all(t["amount"] != 999.0 for t in scoped["spending_trend"])

        unfiltered = client.get("/api/analytics/summary", headers=auth_headers).json()
        assert _trend(unfiltered) == [("2026-08", 100.0), ("2026-09", 1000.0)]
        assert unfiltered["transaction_count"] == 5

    def test_date_range_with_account_still_scopes_trend(
        self, client, auth_headers
    ):
        acc_a, _ = _seed(client, auth_headers)
        res = client.get(
            f"/api/analytics/summary?account_id={acc_a}"
            "&start_date=2026-09-01&end_date=2026-09-30",
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert _trend(res.json()) == [("2026-09", 300.0)]
