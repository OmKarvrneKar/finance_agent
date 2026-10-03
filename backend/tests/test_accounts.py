"""Phase 4A: multi-account support (backend/data model).

Covers the account CRUD surface, ownership enforcement, balance derivation,
and the transaction<->account association. Also asserts that transactions which
predate Phase 4A keep working with a NULL account.
"""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, Account, Transaction, User


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
def user_a_auth(client):
    token = _register_and_login(client, "usera@test.com", "Pass123456789", "User A")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_b_auth(client):
    token = _register_and_login(client, "userb@test.com", "Pass123456789", "User B")
    return {"Authorization": f"Bearer {token}"}


def _user_id(email="usera@test.com"):
    db = TestingSessionLocal()
    try:
        return db.query(User).filter(User.email == email).first().id
    finally:
        db.close()


def _create_account(client, auth, **overrides):
    payload = {"name": "Salary Account", "account_type": "bank"}
    payload.update(overrides)
    res = client.post("/api/accounts", json=payload, headers=auth)
    assert res.status_code == 201, res.text
    return res.json()


def _seed_transaction(user_id, account_id=None, amount="1000.00", transaction_type="debit",
                     description="Test", tx_date="2026-05-01", category="Food"):
    db = TestingSessionLocal()
    try:
        tx = Transaction(
            user_id=user_id,
            date=date.fromisoformat(tx_date),
            description=description,
            amount=Decimal(amount),
            transaction_type=transaction_type,
            category=category,
            is_recurring=False,
            is_user_confirmed_recurring=False,
            source="bank_statement",
            account_id=account_id,
        )
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return tx.id
    finally:
        db.close()


# --- Schema ---

class TestSchema:
    def test_accounts_table_has_expected_columns(self):
        cols = {c["name"] for c in inspect(engine).get_columns("accounts")}
        assert {
            "id", "user_id", "name", "account_type", "institution_name", "last4",
            "currency", "opening_balance", "is_active", "created_at", "updated_at",
        } <= cols

    def test_transactions_account_id_is_nullable(self):
        insp = inspect(engine)
        col = next(c for c in insp.get_columns("transactions") if c["name"] == "account_id")
        assert col["nullable"] is True

    def test_accounts_table_has_no_full_account_number_column(self):
        cols = {c["name"] for c in inspect(engine).get_columns("accounts")}
        for forbidden in ("account_number", "card_number", "pan", "full_number", "number"):
            assert forbidden not in cols

    def test_last4_column_is_four_characters(self):
        col = next(c for c in inspect(engine).get_columns("accounts") if c["name"] == "last4")
        assert col["type"].length == 4

    def test_no_balance_column_is_stored_on_accounts(self):
        """The running balance must be derived, never duplicated in a column."""
        cols = {c["name"] for c in inspect(engine).get_columns("accounts")}
        assert "current_balance" not in cols
        assert "balance" not in cols


# --- Create ---

class TestCreateAccount:
    def test_create_account(self, client, user_a_auth):
        data = _create_account(client, user_a_auth, institution_name="HDFC Bank", last4="4321")
        assert data["id"] > 0
        assert data["name"] == "Salary Account"
        assert data["account_type"] == "bank"
        assert data["institution_name"] == "HDFC Bank"
        assert data["last4"] == "4321"
        assert data["is_active"] is True

    def test_currency_defaults_to_application_currency(self, client, user_a_auth):
        data = _create_account(client, user_a_auth)
        assert data["currency"] == "INR"

    def test_opening_balance_defaults_to_zero(self, client, user_a_auth):
        data = _create_account(client, user_a_auth)
        assert float(data["opening_balance"]) == 0.0
        assert float(data["current_balance"]) == 0.0

    def test_balance_nature_available_for_bank(self, client, user_a_auth):
        data = _create_account(client, user_a_auth, account_type="bank")
        assert data["balance_nature"] == "available"

    def test_balance_nature_owed_for_credit_card(self, client, user_a_auth):
        data = _create_account(client, user_a_auth, account_type="credit_card")
        assert data["balance_nature"] == "owed"

    @pytest.mark.parametrize(
        "account_type", ["bank", "credit_card", "cash", "wallet", "investment", "other"]
    )
    def test_every_documented_account_type_is_accepted(self, client, user_a_auth, account_type):
        data = _create_account(client, user_a_auth, account_type=account_type)
        assert data["account_type"] == account_type

    def test_duplicate_account_names_are_allowed(self, client, user_a_auth):
        """Two accounts at one bank is normal, so no uniqueness rule is imposed."""
        first = _create_account(client, user_a_auth, name="HDFC", account_type="bank")
        second = _create_account(client, user_a_auth, name="HDFC", account_type="bank")
        assert first["id"] != second["id"]
        res = client.get("/api/accounts", headers=user_a_auth)
        assert len(res.json()) == 2

    def test_opening_balance_can_be_negative_for_card_debt(self, client, user_a_auth):
        data = _create_account(
            client, user_a_auth, account_type="credit_card", opening_balance="-5000.00"
        )
        assert float(data["opening_balance"]) == -5000.0
        assert float(data["current_balance"]) == -5000.0


# --- List / get ---

class TestListAndGet:
    def test_list_accounts_returns_only_own_accounts(self, client, user_a_auth, user_b_auth):
        _create_account(client, user_a_auth, name="A account")
        _create_account(client, user_b_auth, name="B account")

        names = [a["name"] for a in client.get("/api/accounts", headers=user_a_auth).json()]
        assert names == ["A account"]

    def test_list_accounts_empty(self, client, user_a_auth):
        assert client.get("/api/accounts", headers=user_a_auth).json() == []

    def test_get_account(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        res = client.get(f"/api/accounts/{created['id']}", headers=user_a_auth)
        assert res.status_code == 200
        assert res.json()["id"] == created["id"]

    def test_get_missing_account_returns_404(self, client, user_a_auth):
        assert client.get("/api/accounts/99999", headers=user_a_auth).status_code == 404

    def test_list_can_filter_by_is_active(self, client, user_a_auth):
        _create_account(client, user_a_auth, name="Open")
        closed = _create_account(client, user_a_auth, name="Closed")
        client.patch(f"/api/accounts/{closed['id']}", json={"is_active": False}, headers=user_a_auth)

        active = client.get("/api/accounts", params={"is_active": True}, headers=user_a_auth).json()
        assert [a["name"] for a in active] == ["Open"]
        everything = client.get("/api/accounts", headers=user_a_auth).json()
        assert len(everything) == 2


# --- Update ---

class TestUpdateAccount:
    def test_update_single_field(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        res = client.patch(
            f"/api/accounts/{created['id']}", json={"name": "Renamed"}, headers=user_a_auth
        )
        assert res.status_code == 200
        assert res.json()["name"] == "Renamed"
        # Untouched fields survive a partial update.
        assert res.json()["account_type"] == created["account_type"]

    def test_update_account_type_and_currency(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        res = client.patch(
            f"/api/accounts/{created['id']}",
            json={"account_type": "wallet", "currency": "usd"},
            headers=user_a_auth,
        )
        assert res.status_code == 200
        assert res.json()["account_type"] == "wallet"
        assert res.json()["currency"] == "USD"

    def test_update_opening_balance(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        res = client.patch(
            f"/api/accounts/{created['id']}",
            json={"opening_balance": "2500.50"},
            headers=user_a_auth,
        )
        assert float(res.json()["opening_balance"]) == 2500.50
        assert float(res.json()["current_balance"]) == 2500.50

    def test_can_clear_last4(self, client, user_a_auth):
        created = _create_account(client, user_a_auth, last4="9999")
        res = client.patch(
            f"/api/accounts/{created['id']}", json={"last4": None}, headers=user_a_auth
        )
        assert res.status_code == 200
        assert res.json()["last4"] is None

    def test_update_with_no_fields_returns_400(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        res = client.patch(f"/api/accounts/{created['id']}", json={}, headers=user_a_auth)
        assert res.status_code == 400

    def test_update_unknown_field_is_rejected(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        res = client.patch(
            f"/api/accounts/{created['id']}", json={"iban": "DE89..."}, headers=user_a_auth
        )
        assert res.status_code == 422

    def test_update_missing_account_returns_404(self, client, user_a_auth):
        res = client.patch("/api/accounts/99999", json={"name": "x"}, headers=user_a_auth)
        assert res.status_code == 404


# --- Delete ---

class TestDeleteAccount:
    def test_delete_account(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        assert client.delete(f"/api/accounts/{created['id']}", headers=user_a_auth).status_code == 200
        assert client.get(f"/api/accounts/{created['id']}", headers=user_a_auth).status_code == 404
        assert client.get("/api/accounts", headers=user_a_auth).json() == []

    def test_delete_missing_account_returns_404(self, client, user_a_auth):
        assert client.delete("/api/accounts/99999", headers=user_a_auth).status_code == 404

    def test_delete_keeps_linked_transactions(self, client, user_a_auth):
        """Deleting an account must not delete or damage its transactions."""
        created = _create_account(client, user_a_auth)
        user_id = _user_id()
        tx_id = _seed_transaction(user_id, account_id=created["id"], amount="750.25")

        client.delete(f"/api/accounts/{created['id']}", headers=user_a_auth)

        db = TestingSessionLocal()
        try:
            tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
            assert tx is not None, "transaction was deleted with the account"
            assert float(tx.amount) == 750.25, "transaction amount changed"
            assert tx.category == "Food", "transaction category changed"
            assert tx.account_id is None, "deleted account left a dangling reference"
        finally:
            db.close()

    def test_delete_does_not_touch_other_users_accounts(self, client, user_a_auth, user_b_auth):
        mine = _create_account(client, user_a_auth, name="Mine")
        theirs = _create_account(client, user_b_auth, name="Theirs")

        client.delete(f"/api/accounts/{theirs['id']}", headers=user_a_auth)
        assert client.get(f"/api/accounts/{theirs['id']}", headers=user_b_auth).status_code == 200
        assert client.get(f"/api/accounts/{mine['id']}", headers=user_a_auth).status_code == 200


# --- Validation ---

class TestValidation:
    @pytest.mark.parametrize("bad_type", ["crypto", "bank_account", "", "BANK2", "savings"])
    def test_invalid_account_type_rejected(self, client, user_a_auth, bad_type):
        res = client.post(
            "/api/accounts",
            json={"name": "X", "account_type": bad_type},
            headers=user_a_auth,
        )
        assert res.status_code == 422

    def test_account_type_is_normalised(self, client, user_a_auth):
        data = _create_account(client, user_a_auth, account_type="CREDIT_CARD")
        assert data["account_type"] == "credit_card"

    def test_update_to_invalid_account_type_rejected(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        res = client.patch(
            f"/api/accounts/{created['id']}", json={"account_type": "crypto"}, headers=user_a_auth
        )
        assert res.status_code == 422

    @pytest.mark.parametrize(
        "bad_last4",
        [
            "1234567890123",   # a full card number
            "4111111111111111",
            "123",             # too short
            "12345",           # too long
            "abcd",            # not digits
            "12 4",
            "",
        ],
    )
    def test_full_account_numbers_are_rejected(self, client, user_a_auth, bad_last4):
        res = client.post(
            "/api/accounts",
            json={"name": "Card", "account_type": "credit_card", "last4": bad_last4},
            headers=user_a_auth,
        )
        assert res.status_code == 422, f"last4={bad_last4!r} was accepted"

    def test_valid_last4_accepted(self, client, user_a_auth):
        data = _create_account(client, user_a_auth, last4="0421")
        assert data["last4"] == "0421"

    def test_full_card_number_is_never_stored_anywhere(self, client, user_a_auth):
        card = "4111111111111111"
        client.post(
            "/api/accounts",
            json={"name": "Card", "account_type": "credit_card", "last4": card},
            headers=user_a_auth,
        )
        db = TestingSessionLocal()
        try:
            rows = db.execute(
                text("SELECT last4, institution_name, name FROM accounts")
            ).fetchall()
        finally:
            db.close()
        for last4, institution, name in rows:
            for value in (last4, institution, name):
                assert card not in (value or "")

    def test_blank_name_rejected(self, client, user_a_auth):
        res = client.post(
            "/api/accounts", json={"name": "   ", "account_type": "bank"}, headers=user_a_auth
        )
        assert res.status_code == 422

    def test_invalid_currency_rejected(self, client, user_a_auth):
        res = client.post(
            "/api/accounts",
            json={"name": "X", "account_type": "bank", "currency": "rupees"},
            headers=user_a_auth,
        )
        assert res.status_code == 422


# --- Authentication / isolation ---

class TestAuthenticationAndIsolation:
    def test_all_endpoints_require_authentication(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        client.cookies.clear()
        assert client.post("/api/accounts", json={"name": "X", "account_type": "bank"}).status_code == 401
        assert client.get("/api/accounts").status_code == 401
        assert client.get(f"/api/accounts/{created['id']}").status_code == 401
        assert client.patch(f"/api/accounts/{created['id']}", json={"name": "X"}).status_code == 401
        assert client.delete(f"/api/accounts/{created['id']}").status_code == 401

    def test_cannot_read_another_users_account(self, client, user_a_auth, user_b_auth):
        created = _create_account(client, user_a_auth)
        assert client.get(f"/api/accounts/{created['id']}", headers=user_b_auth).status_code == 404

    def test_cannot_update_another_users_account(self, client, user_a_auth, user_b_auth):
        created = _create_account(client, user_a_auth, name="Original")
        res = client.patch(
            f"/api/accounts/{created['id']}", json={"name": "Hijacked"}, headers=user_b_auth
        )
        assert res.status_code == 404
        assert client.get(f"/api/accounts/{created['id']}", headers=user_a_auth).json()["name"] == "Original"

    def test_cannot_delete_another_users_account(self, client, user_a_auth, user_b_auth):
        created = _create_account(client, user_a_auth)
        assert client.delete(f"/api/accounts/{created['id']}", headers=user_b_auth).status_code == 404
        assert client.get(f"/api/accounts/{created['id']}", headers=user_a_auth).status_code == 200

    def test_response_does_not_leak_other_users_data(self, client, user_a_auth, user_b_auth):
        _create_account(client, user_a_auth, name="Secret Account", last4="9876")
        body = client.get("/api/accounts", headers=user_b_auth).text
        assert "Secret Account" not in body
        assert "9876" not in body


# --- Derived balances ---

class TestDerivedBalance:
    def test_current_balance_includes_linked_transactions(self, client, user_a_auth):
        created = _create_account(client, user_a_auth, opening_balance="1000.00")
        user_id = _user_id()
        _seed_transaction(user_id, created["id"], amount="500.00", transaction_type="credit")
        _seed_transaction(user_id, created["id"], amount="200.00", transaction_type="debit")

        res = client.get(f"/api/accounts/{created['id']}", headers=user_a_auth)
        assert float(res.json()["current_balance"]) == 1300.00
        assert res.json()["transaction_count"] == 2

    def test_unlinked_transactions_do_not_affect_balance(self, client, user_a_auth):
        created = _create_account(client, user_a_auth, opening_balance="1000.00")
        _seed_transaction(_user_id(), None, amount="9999.00", transaction_type="debit")

        res = client.get(f"/api/accounts/{created['id']}", headers=user_a_auth)
        assert float(res.json()["current_balance"]) == 1000.00
        assert res.json()["transaction_count"] == 0

    def test_credit_card_balance_is_reported_as_amount_owed(self, client, user_a_auth):
        created = _create_account(
            client, user_a_auth, account_type="credit_card", opening_balance="0"
        )
        user_id = _user_id()
        # A purchase raises what is owed; a payment lowers it.
        _seed_transaction(user_id, created["id"], amount="3000.00", transaction_type="debit")
        _seed_transaction(user_id, created["id"], amount="1000.00", transaction_type="credit")

        res = client.get(f"/api/accounts/{created['id']}", headers=user_a_auth)
        assert float(res.json()["current_balance"]) == 2000.00
        assert res.json()["balance_nature"] == "owed"

    def test_bank_account_credit_increases_balance(self, client, user_a_auth):
        created = _create_account(client, user_a_auth, account_type="bank", opening_balance="500.00")
        _seed_transaction(_user_id(), created["id"], amount="2500.00", transaction_type="credit")

        res = client.get(f"/api/accounts/{created['id']}", headers=user_a_auth)
        assert float(res.json()["current_balance"]) == 3000.00
        assert res.json()["balance_nature"] == "available"

    def test_balance_is_not_stored_so_it_cannot_drift(self, client, user_a_auth):
        created = _create_account(client, user_a_auth, opening_balance="100.00")
        _seed_transaction(_user_id(), created["id"], amount="50.00", transaction_type="credit")

        db = TestingSessionLocal()
        try:
            row = db.query(Account).filter(Account.id == created["id"]).one()
            stored_columns = {c.name for c in Account.__table__.columns}
            assert "current_balance" not in stored_columns
            # Only opening_balance is persisted.
            assert float(row.opening_balance) == 100.00
        finally:
            db.close()

    def test_decimal_precision_preserved_in_balance(self, client, user_a_auth):
        created = _create_account(client, user_a_auth, opening_balance="0.00")
        user_id = _user_id()
        _seed_transaction(user_id, created["id"], amount="1500.25", transaction_type="credit")
        _seed_transaction(user_id, created["id"], amount="2000.75", transaction_type="credit")

        res = client.get(f"/api/accounts/{created['id']}", headers=user_a_auth)
        assert res.json()["current_balance"] == "3501.00"


# --- Transaction association ---

class TestTransactionAssociation:
    def test_associate_transaction_with_account(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        tx_id = _seed_transaction(_user_id(), None, amount="400.00")

        res = client.patch(
            f"/api/transactions/{tx_id}/account",
            json={"account_id": created["id"]},
            headers=user_a_auth,
        )
        assert res.status_code == 200
        assert res.json()["account_id"] == created["id"]

    def test_association_does_not_change_amount_or_category(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        tx_id = _seed_transaction(_user_id(), None, amount="1234.56", category="Travel")

        res = client.patch(
            f"/api/transactions/{tx_id}/account",
            json={"account_id": created["id"]},
            headers=user_a_auth,
        )
        assert float(res.json()["amount"]) == 1234.56
        assert res.json()["category"] == "Travel"
        assert res.json()["description"] == "Test"

    def test_association_updates_balance(self, client, user_a_auth):
        created = _create_account(client, user_a_auth, opening_balance="0.00")
        tx_id = _seed_transaction(_user_id(), None, amount="800.00", transaction_type="debit")

        before = client.get(f"/api/accounts/{created['id']}", headers=user_a_auth).json()
        assert float(before["current_balance"]) == 0.0

        client.patch(
            f"/api/transactions/{tx_id}/account",
            json={"account_id": created["id"]},
            headers=user_a_auth,
        )

        after = client.get(f"/api/accounts/{created['id']}", headers=user_a_auth).json()
        assert float(after["current_balance"]) == -800.00

    def test_detach_transaction_with_null(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        tx_id = _seed_transaction(_user_id(), created["id"], amount="100.00")

        res = client.patch(
            f"/api/transactions/{tx_id}/account", json={"account_id": None}, headers=user_a_auth
        )
        assert res.status_code == 200
        assert res.json()["account_id"] is None

    def test_reassociate_between_accounts(self, client, user_a_auth):
        first = _create_account(client, user_a_auth, name="First")
        second = _create_account(client, user_a_auth, name="Second")
        tx_id = _seed_transaction(_user_id(), first["id"], amount="100.00")

        res = client.patch(
            f"/api/transactions/{tx_id}/account",
            json={"account_id": second["id"]},
            headers=user_a_auth,
        )
        assert res.json()["account_id"] == second["id"]

        first_balance = client.get(f"/api/accounts/{first['id']}", headers=user_a_auth).json()
        second_balance = client.get(f"/api/accounts/{second['id']}", headers=user_a_auth).json()
        assert first_balance["transaction_count"] == 0
        assert second_balance["transaction_count"] == 1

    def test_cannot_attach_another_users_transaction(self, client, user_a_auth, user_b_auth):
        account = _create_account(client, user_b_auth, name="B account")
        tx_id = _seed_transaction(_user_id(), None, amount="100.00")

        res = client.patch(
            f"/api/transactions/{tx_id}/account",
            json={"account_id": account["id"]},
            headers=user_b_auth,
        )
        assert res.status_code == 404

        db = TestingSessionLocal()
        try:
            assert db.query(Transaction).filter(Transaction.id == tx_id).one().account_id is None
        finally:
            db.close()

    def test_cannot_attach_to_another_users_account(self, client, user_a_auth, user_b_auth):
        account = _create_account(client, user_b_auth, name="B account")
        tx_id = _seed_transaction(_user_id(), None, amount="100.00")

        res = client.patch(
            f"/api/transactions/{tx_id}/account",
            json={"account_id": account["id"]},
            headers=user_a_auth,
        )
        assert res.status_code == 404

        db = TestingSessionLocal()
        try:
            assert db.query(Transaction).filter(Transaction.id == tx_id).one().account_id is None
        finally:
            db.close()

    def test_cannot_associate_missing_account(self, client, user_a_auth):
        tx_id = _seed_transaction(_user_id(), None)
        res = client.patch(
            f"/api/transactions/{tx_id}/account",
            json={"account_id": 99999},
            headers=user_a_auth,
        )
        assert res.status_code == 404

    def test_cannot_associate_missing_transaction(self, client, user_a_auth):
        account = _create_account(client, user_a_auth)
        res = client.patch(
            "/api/transactions/99999/account",
            json={"account_id": account["id"]},
            headers=user_a_auth,
        )
        assert res.status_code == 404

    def test_association_requires_authentication(self, client, user_a_auth):
        created = _create_account(client, user_a_auth)
        tx_id = _seed_transaction(_user_id(), None)
        client.cookies.clear()
        res = client.patch(
            f"/api/transactions/{tx_id}/account", json={"account_id": created["id"]}
        )
        assert res.status_code == 401


# --- Backward compatibility ---

class TestBackwardCompatibility:
    def test_existing_transactions_have_null_account_id(self, client, user_a_auth):
        tx_id = _seed_transaction(_user_id(), None)
        db = TestingSessionLocal()
        try:
            assert db.query(Transaction).filter(Transaction.id == tx_id).one().account_id is None
        finally:
            db.close()

    def test_transaction_listing_still_works_with_null_account(self, client, user_a_auth):
        _seed_transaction(_user_id(), None, amount="500.00")
        _seed_transaction(_user_id(), None, amount="600.00")

        res = client.get("/api/transactions", headers=user_a_auth)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 2
        for tx in body["transactions"]:
            assert tx["account_id"] is None
            assert float(tx["amount"]) > 0

    def test_transaction_amounts_and_totals_are_unchanged(self, client, user_a_auth):
        _seed_transaction(_user_id(), None, amount="250.50")
        _seed_transaction(_user_id(), None, amount="749.50")

        res = client.get("/api/analytics/summary", headers=user_a_auth)
        assert res.status_code == 200
        assert float(res.json()["total_expenses"]) == 1000.00

    def test_savings_goals_are_unaffected_by_accounts(self, client, user_a_auth):
        _create_account(client, user_a_auth)
        res = client.post(
            "/api/goals",
            json={"name": "Emergency Fund", "target_amount": "10000"},
            headers=user_a_auth,
        )
        assert res.status_code == 200
        assert res.json()["id"] > 0

    def test_transaction_update_still_works(self, client, user_a_auth):
        tx_id = _seed_transaction(_user_id(), None, amount="100.00")
        res = client.put(
            f"/api/transactions/{tx_id}",
            json={"category": "Updated Category"},
            headers=user_a_auth,
        )
        assert res.status_code == 200
        assert res.json()["category"] == "Updated Category"

    def test_old_transactions_are_never_auto_assigned(self, client, user_a_auth):
        """Creating an account must not touch transactions that predate it."""
        _seed_transaction(_user_id(), None, amount="100.00")
        _create_account(client, user_a_auth)

        db = TestingSessionLocal()
        try:
            assert db.query(Transaction).filter(Transaction.user_id == _user_id()).one().account_id is None
        finally:
            db.close()