import sqlite3
import os
import shutil
from datetime import datetime

db_path = 'finance.db'
backup_path = f'finance_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

if not os.path.exists(db_path):
    print('Database file not found')
    exit(1)

# Backup
shutil.copy2(db_path, backup_path)
print(f'Backup created: {backup_path}')
print(f'Database size: {os.path.getsize(db_path)} bytes')

conn = sqlite3.connect(db_path)
c = conn.cursor()

# List tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print(f'Tables: {[t[0] for t in tables]}')

# Count records
for table in tables:
    tname = table[0]
    c.execute(f'SELECT COUNT(*) FROM {tname}')
    count = c.fetchone()[0]
    print(f'  {tname}: {count} rows')

# Sample monetary values from transactions
c.execute('SELECT id, amount, category, transaction_type FROM transactions LIMIT 10')
rows = c.fetchall()
print('Sample transactions (first 10):')
for r in rows:
    print(f'  id={r[0]}, amount={r[1]} (type={type(r[1]).__name__}), category={r[2]}, tx_type={r[3]}')

# Check amount types
c.execute('SELECT typeof(amount), COUNT(*) FROM transactions GROUP BY typeof(amount)')
types = c.fetchall()
print(f'Amount column types: {types}')

# Total amounts
c.execute('SELECT SUM(amount) FROM transactions WHERE transaction_type="debit"')
total_debit = c.fetchone()[0]
c.execute('SELECT SUM(amount) FROM transactions WHERE transaction_type="credit"')
total_credit = c.fetchone()[0]
print(f'Total debit: {total_debit} (type={type(total_debit).__name__})')
print(f'Total credit: {total_credit} (type={type(total_credit).__name__})')

# Budget goals
c.execute('SELECT id, category, monthly_cap FROM budget_goals')
budgets = c.fetchall()
print(f'Budget goals: {len(budgets)}')
for b in budgets:
    print(f'  id={b[0]}, category={b[1]}, cap={b[2]} (type={type(b[2]).__name__})')

# Savings goals
c.execute('SELECT id, name, target_amount FROM savings_goals')
goals = c.fetchall()
print(f'Savings goals: {len(goals)}')
for g in goals:
    print(f'  id={g[0]}, name={g[1]}, target={g[2]} (type={type(g[2]).__name__})')

conn.close()
