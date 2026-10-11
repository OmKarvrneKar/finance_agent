"""Phase 5C.1: search and date-range query params on GET /api/transactions."""

def _payload(**overrides):
    payload = {
        "date": "2026-09-10",
        "description": "Coffee Shop",
        "amount": 100.00,
        "transaction_type": "debit",
        "category": "Food & Dining",
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
    """Account A: 3 txs, Account B: 1 tx, NULL account: 1 tx."""
    acc_a = _create_account(client, headers, "Primary Checking")
    acc_b = _create_account(client, headers, "Credit Card")

    _create_tx(client, headers, date="2026-09-10", description="Coffee Shop",
               amount=100.00, category="Food & Dining", account_id=acc_a)
    _create_tx(client, headers, date="2026-06-05", description="Rent Payment",
               amount=1000.00, category="Bills & Utilities", account_id=acc_a)
    _create_tx(client, headers, date="2026-07-20", description="Coffee Beans",
               amount=300.00, category="Food & Dining", account_id=acc_a)
    _create_tx(client, headers, date="2026-08-15", description="Coffee Ground",
               amount=50.00, category="Food & Dining", account_id=acc_b)
    _create_tx(client, headers, date="2026-09-01", description="Coffee Cash",
               amount=200.00, category="Food & Dining")
    return acc_a, acc_b


def _get(client, headers, **params):
    return client.get("/api/transactions", params=params, headers=headers)


class TestSearchFilterAffectsResults:
    def test_search_filters_results_sorted_desc(self, client, auth_headers):
        _seed(client, auth_headers)
        res = _get(client, auth_headers, search="coffee")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 4
        assert [t["description"] for t in data["transactions"]] == [
            "Coffee Shop", "Coffee Cash", "Coffee Ground", "Coffee Beans",
        ]
        assert "Rent Payment" not in [t["description"] for t in data["transactions"]]

    def test_search_is_case_insensitive(self, client, auth_headers):
        _seed(client, auth_headers)
        data = _get(client, auth_headers, search="RENT").json()
        assert data["total"] == 1
        assert data["transactions"][0]["description"] == "Rent Payment"

    def test_search_without_matches_returns_empty(self, client, auth_headers):
        _seed(client, auth_headers)
        data = _get(client, auth_headers, search="zzzzz").json()
        assert data["total"] == 0
        assert data["transactions"] == []

    def test_search_affects_pagination_counts(self, client, auth_headers):
        _seed(client, auth_headers)
        data = _get(client, auth_headers, search="coffee", limit=2, page=1).json()
        assert data["total"] == 4
        assert data["pages"] == 2
        assert len(data["transactions"]) == 2


class TestDateRangeFiltersAffectResults:
    def test_start_date_excludes_earlier_transactions(self, client, auth_headers):
        _seed(client, auth_headers)
        data = _get(client, auth_headers, start_date="2026-07-01").json()
        assert data["total"] == 4
        assert "Rent Payment" not in [t["description"] for t in data["transactions"]]
        assert all(t["date"] >= "2026-07-01" for t in data["transactions"])

    def test_end_date_excludes_later_transactions(self, client, auth_headers):
        _seed(client, auth_headers)
        data = _get(client, auth_headers, end_date="2026-07-31").json()
        assert data["total"] == 2
        assert {t["description"] for t in data["transactions"]} == {
            "Rent Payment", "Coffee Beans",
        }

    def test_start_and_end_date_form_a_range(self, client, auth_headers):
        _seed(client, auth_headers)
        data = _get(
            client, auth_headers, start_date="2026-07-01", end_date="2026-08-31"
        ).json()
        assert data["total"] == 2
        assert {t["description"] for t in data["transactions"]} == {
            "Coffee Beans", "Coffee Ground",
        }

    def test_empty_date_params_do_not_filter(self, client, auth_headers):
        _seed(client, auth_headers)
        data = _get(client, auth_headers, start_date="", end_date="").json()
        assert data["total"] == 5


class TestSearchAndDatesCombinedWithAccount:
    def test_search_with_account_id(self, client, auth_headers):
        acc_a, _ = _seed(client, auth_headers)
        data = _get(client, auth_headers, account_id=acc_a, search="coffee").json()
        assert data["total"] == 2
        assert {t["description"] for t in data["transactions"]} == {
            "Coffee Shop", "Coffee Beans",
        }

    def test_date_range_with_account_id(self, client, auth_headers):
        acc_a, _ = _seed(client, auth_headers)
        data = _get(
            client, auth_headers,
            account_id=acc_a, start_date="2026-07-01", end_date="2026-07-31",
        ).json()
        assert data["total"] == 1
        assert data["transactions"][0]["description"] == "Coffee Beans"

    def test_search_dates_and_account_id_combined(self, client, auth_headers):
        acc_a, _ = _seed(client, auth_headers)
        data = _get(
            client, auth_headers,
            account_id=acc_a, search="coffee", start_date="2026-08-01",
        ).json()
        assert data["total"] == 1
        assert data["transactions"][0]["description"] == "Coffee Shop"

    def test_search_and_dates_without_account_still_scoped_to_user(
        self, client, auth_headers, second_auth_headers
    ):
        _seed(client, auth_headers)
        _seed(client, second_auth_headers)
        data = _get(client, auth_headers, search="coffee").json()
        assert data["total"] == 4
        data_dates = _get(
            client, auth_headers, start_date="2026-07-01", end_date="2026-08-31"
        ).json()
        assert data_dates["total"] == 2
