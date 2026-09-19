import io
import re
import pandas as pd
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

# Define common variations for each column type (lowercase, stripped)
DATE_COLS = {'date', 'txn date', 'transaction date', 'tran date', 'value date', 'post date', 'txndate'}
DESC_COLS = {'description', 'narration', 'transaction remarks', 'particulars', 'transaction description', 'remarks', 'particulars/narration'}
DEBIT_COLS = {'debit', 'withdrawal', 'withdrawal amt', 'withdrawal amt.', 'dr amt', 'debit amount', 'withdrawal amount', 'dr'}
CREDIT_COLS = {'credit', 'deposit', 'deposit amt', 'deposit amt.', 'cr amt', 'credit amount', 'deposit amount', 'cr'}

def parse_bank_csv(file_bytes: bytes) -> list:
    # Try decoding with utf-8, fallback to latin-1
    try:
        content = file_bytes.decode('utf-8')
    except UnicodeDecodeError:
        content = file_bytes.decode('latin-1')
        
    lines = content.splitlines()
    
    # We want to find the header row by scanning first 50 lines.
    # We check each line to see how many column categories it matches.
    best_row_idx = -1
    best_score = 0
    
    import csv
    reader = csv.reader(io.StringIO(content))
    rows = []
    try:
        for i, row in enumerate(reader):
            if i > 50:
                break
            rows.append(row)
    except Exception:
        # If csv reader fails, split by comma simple
        rows = [line.split(',') for line in lines[:50]]
        
    for idx, row in enumerate(rows):
        # clean tokens
        tokens = [str(cell).strip().lower() for cell in row]
        # check which categories are matched
        has_date = any(t in DATE_COLS or any(d in t for d in DATE_COLS) for t in tokens)
        has_desc = any(t in DESC_COLS or any(d in t for d in DESC_COLS) for t in tokens)
        has_debit = any(t in DEBIT_COLS or any(d in t for d in DEBIT_COLS) for t in tokens)
        has_credit = any(t in CREDIT_COLS or any(d in t for d in CREDIT_COLS) for t in tokens)
        
        score = sum([has_date, has_desc, has_debit, has_credit])
        if score > best_score:
            best_score = score
            best_row_idx = idx
            
    if best_score < 3: # Must match at least date, description, and one of debit/credit
        raise ValueError("Could not find a valid transaction table header in the CSV file.")

    # Now load df from the header row index
    df = pd.read_csv(io.BytesIO(file_bytes), skiprows=best_row_idx)
    
    # Let's clean the columns of the dataframe
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    # Find which column matches which concept
    date_col = None
    desc_col = None
    debit_col = None
    credit_col = None
    
    # Find matching columns in the dataframe
    for col in df.columns:
        if any(d in col for d in DATE_COLS) and not date_col:
            date_col = col
        elif any(d in col for d in DESC_COLS) and not desc_col:
            desc_col = col
        elif any(d in col for d in DEBIT_COLS) and not debit_col:
            debit_col = col
        elif any(d in col for d in CREDIT_COLS) and not credit_col:
            credit_col = col
            
    # If we didn't find debit or credit column, search for a single amount/amt column
    if not date_col or not desc_col:
        raise ValueError("Could not map Date or Description column in the CSV.")
        
    transactions = []
    
    # Helper to parse floats from currency string
    def clean_amount(val):
        if pd.isna(val):
            return Decimal('0.00')
        val_str = str(val).strip()
        # Remove currency symbols and commas, handle parentheses for negative amounts
        val_str = re.sub(r'[^\d\.\-\(\)]', '', val_str)
        if not val_str:
            return Decimal('0.00')
        if val_str.startswith('(') and val_str.endswith(')'):
            val_str = '-' + val_str[1:-1]
        try:
            return Decimal(val_str).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            return Decimal('0.00')

    # Helper to parse date formats
    def parse_date(val):
        if pd.isna(val):
            return None
        val_str = str(val).strip()
        formats = [
            '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d',
            '%d/%m/%y', '%d-%m-%y', '%d %b %Y',
            '%d %B %Y', '%d-%b-%Y', '%d-%B-%Y',
            '%Y/%m/%d', '%b %d, %Y', '%d/%m/%Y %H:%M:%S',
            '%d-%m-%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S'
        ]
        val_str_clean = re.sub(r'\s+', ' ', val_str)
        
        for fmt in formats:
            try:
                return datetime.strptime(val_str_clean, fmt).date()
            except ValueError:
                continue
        try:
            return pd.to_datetime(val_str_clean).date()
        except Exception:
            return None

    # Process rows
    for index, row in df.iterrows():
        # Read the raw text of the entire row (for record keeping)
        raw_text = ", ".join([f"{col}: {val}" for col, val in row.items() if not pd.isna(val)])
        
        # Parse date
        t_date = parse_date(row.get(date_col))
        if not t_date:
            continue
            
        desc = str(row.get(desc_col, '')).strip()
        if not desc or desc.lower() in ['nan', 'null', '']:
            continue
            
        debit_val = clean_amount(row.get(debit_col)) if debit_col else Decimal('0.00')
        credit_val = clean_amount(row.get(credit_col)) if credit_col else Decimal('0.00')
        
        amount = Decimal('0.00')
        t_type = 'debit'
        
        if debit_val > 0:
            amount = debit_val
            t_type = 'debit'
        elif credit_val > 0:
            amount = credit_val
            t_type = 'credit'
        else:
            # Fallback check for single "amount" column
            amt_col = None
            for col in df.columns:
                if 'amount' in col or 'amt' in col:
                    if col not in (debit_col, credit_col):
                        amt_col = col
                        break
            if amt_col:
                val = clean_amount(row.get(amt_col))
                amount = abs(val)
                t_type = 'debit' if val < 0 else 'credit'
                
                type_col = None
                for col in df.columns:
                    if 'type' in col or 'cr/dr' in col or 'cr_dr' in col:
                        type_col = col
                        break
                if type_col:
                    t_type_val = str(row.get(type_col)).strip().lower()
                    if 'dr' in t_type_val or 'debit' in t_type_val or 'w' in t_type_val:
                        t_type = 'debit'
                    elif 'cr' in t_type_val or 'credit' in t_type_val or 'd' in t_type_val:
                        t_type = 'credit'
            else:
                continue
                
        transactions.append({
            'date': t_date,
            'description': desc,
            'amount': amount,
            'transaction_type': t_type,
            'raw_text': raw_text
        })
        
    return transactions
