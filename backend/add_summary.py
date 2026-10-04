from pathlib import Path

p = Path("app/routers/accounts.py")
s = p.read_text()
if "from decimal import Decimal" not in s:
    s = s.replace("from typing import List, Optional", "from typing import List, Optional\nfrom decimal import Decimal")
summary = '''

@router.get("/summary")
def get_accounts_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    accounts = crud.get_accounts(db, current_user.id)
    balances = crud.get_accounts_balances(db, current_user.id, accounts=accounts)
    res = []
    for a in accounts:
        res.append({
            "account_id": a.id,
            "name": a.name,
            "account_type": a.account_type,
            "currency": a.currency,
            "current_balance": balances.get(a.id, Decimal("0")),
            "total_credits": balances.get(f"{a.id}:credits", Decimal("0")),
            "total_debits": balances.get(f"{a.id}:debits", Decimal("0")),
            "transaction_count": balances.get(f"{a.id}:count", 0),
        })
    return res
'''
s += summary
p.write_text(s)
print("ok")
