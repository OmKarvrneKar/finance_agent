"""Ad-hoc check: migrate a database that already has data, then reverse it.

Run with DATABASE_URL pointed at a scratch SQLite file.
"""
import os
import sqlite3
import subprocess
import sys

DB = os.environ["DATABASE_URL"].replace("sqlite:///", "")
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(*args):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND, capture_output=True, text=True, env=os.environ,
    )
    if result.returncode != 0:
        print(result.stdout[-2000:])
        print(result.stderr[-3000:])
        raise SystemExit(f"alembic {args} failed")
    return result.stdout


def columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def scalar(conn, sql):
    return conn.execute(sql).fetchone()[0]


if os.path.exists(DB):
    os.remove(DB)

# --- 1. Migrate to 007, i.e. the schema as it was before accounts existed ---
run("upgrade", "007")

conn = sqlite3.connect(DB)
conn.execute(
    "INSERT INTO users (email, hashed_password, full_name, is_active, created_at)"
    " VALUES ('legacy@test.com', 'hash', 'Legacy User', 1, '2026-01-01 00:00:00')"
)
conn.execute(
    "INSERT INTO transactions (user_id, date, description, amount, transaction_type,"
    " category, is_recurring, is_user_confirmed_recurring, source, created_at)"
    " VALUES (1, '2026-01-15', 'Grocery', 2500.50, 'debit', 'Food', 0, 0,"
    " 'bank_statement', '2026-01-15 10:00:00')"
)
conn.execute(
    "INSERT INTO transactions (user_id, date, description, amount, transaction_type,"
    " category, is_recurring, is_user_confirmed_recurring, source, created_at)"
    " VALUES (1, '2026-02-15', 'Salary', 90000.00, 'credit', 'Income', 0, 0,"
    " 'bank_statement', '2026-02-15 10:00:00')"
)
conn.commit()

before_count = scalar(conn, "SELECT COUNT(*) FROM transactions")
before_amounts = [
    r[0] for r in conn.execute("SELECT amount FROM transactions ORDER BY id")
]
assert "account_id" not in columns(conn, "transactions"), "007 must not have account_id"
conn.close()
print(f"pre-existing transactions: {before_count}, amounts={before_amounts}")

# --- 2. Upgrade to head: data must be untouched, column must be NULL ---
run("upgrade", "head")

conn = sqlite3.connect(DB)
assert "accounts" in {
    r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
}, "accounts table missing after upgrade"
assert "account_id" in columns(conn, "transactions"), "account_id column missing"

after_count = scalar(conn, "SELECT COUNT(*) FROM transactions")
after_amounts = [r[0] for r in conn.execute("SELECT amount FROM transactions ORDER BY id")]
null_links = scalar(conn, "SELECT COUNT(*) FROM transactions WHERE account_id IS NULL")

assert after_count == before_count, f"row count changed {before_count} -> {after_count}"
assert after_amounts == before_amounts, f"amounts changed {before_amounts} -> {after_amounts}"
assert null_links == before_count, f"expected every legacy row unassigned, got {null_links - before_count} assigned"
print(f"after upgrade: {after_count} transactions, amounts preserved={after_amounts}, all account_id NULL")

# last4 is length-constrained at the storage layer
conn.execute(
    "INSERT INTO accounts (user_id, name, account_type, currency, opening_balance,"
    " is_active, created_at, updated_at)"
    " VALUES (1, 'Salary Account', 'bank', 'INR', 1000.00, 1,"
    " '2026-03-01 00:00:00', '2026-03-01 00:00:00')"
)
conn.commit()
try:
    conn.execute(
        "INSERT INTO accounts (user_id, name, account_type, last4, currency,"
        " opening_balance, is_active, created_at, updated_at)"
        " VALUES (1, 'Too Long', 'bank', '1234567890123', 'INR', 0, 1,"
        " '2026-03-01 00:00:00', '2026-03-01 00:00:00')"
    )
    conn.commit()
    raise SystemExit("FAIL: DB accepted a 13-digit last4")
except sqlite3.Error as exc:
    print(f"13-digit last4 rejected by the database itself: {type(exc).__name__}")

try:
    conn.execute(
        "INSERT INTO accounts (user_id, name, account_type, currency,"
        " opening_balance, is_active, created_at, updated_at)"
        " VALUES (1, 'Bad Type', 'crypto_wallet', 'INR', 0, 1,"
        " '2026-03-01 00:00:00', '2026-03-01 00:00:00')"
    )
    conn.commit()
    raise SystemExit("FAIL: DB accepted an unknown account_type")
except sqlite3.Error as exc:
    print(f"unknown account_type rejected by the database itself: {type(exc).__name__}")

# link a transaction, then reverse
conn.execute("UPDATE transactions SET account_id = 1 WHERE id = 1")
conn.commit()
conn.close()

# --- 3. Downgrade: column and table go, transactions survive ---
run("downgrade", "007")

conn = sqlite3.connect(DB)
assert "account_id" not in columns(conn, "transactions"), "account_id survived downgrade"
assert "accounts" not in {
    r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
}, "accounts table survived downgrade"
reversed_count = scalar(conn, "SELECT COUNT(*) FROM transactions")
reversed_amounts = [r[0] for r in conn.execute("SELECT amount FROM transactions ORDER BY id")]
assert reversed_count == before_count, f"rows lost on downgrade: {reversed_count}"
assert reversed_amounts == before_amounts, "amounts changed on downgrade"
conn.close()
print(f"after downgrade: {reversed_count} transactions, amounts preserved={reversed_amounts}")

# --- 4. Re-upgrade so the scratch db is consistent, then clean up ---
run("upgrade", "head")
conn = sqlite3.connect(DB)
assert "account_id" in columns(conn, "transactions")
conn.close()
os.remove(DB)
print("PASS: upgrade preserves data, downgrade is reversible, re-upgrade works")