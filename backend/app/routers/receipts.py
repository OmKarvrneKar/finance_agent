import os
import uuid
import shutil
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List

from app.database.db import get_db, PendingReceipt, Transaction
from app.models import schemas
from app.services import receipts

router = APIRouter()

UPLOAD_DIR = "uploads/receipts"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/receipts/upload", response_model=schemas.PendingReceiptResponse)
async def upload_receipt(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")
        
    ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        raw_text = receipts.extract_receipt_text(file_path)
    except Exception as e:
        pending = PendingReceipt(
            image_path=file_path,
            raw_text=None,
            merchant=None,
            amount=None,
            date=None,
            category=None
        )
        db.add(pending)
        db.commit()
        db.refresh(pending)
        return pending
        
    parsed = receipts.parse_receipt_with_ai(raw_text)
    
    dt = None
    if parsed.get("date"):
        try:
            dt = datetime.strptime(parsed["date"], "%Y-%m-%d").date()
        except:
            dt = None
            
    pending = PendingReceipt(
        image_path=file_path,
        raw_text=raw_text,
        merchant=parsed.get("merchant"),
        amount=parsed.get("amount"),
        date=dt,
        category=parsed.get("category")
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    
    return pending

@router.get("/receipts/pending-review", response_model=List[schemas.PendingReceiptResponse])
def get_pending_receipts(db: Session = Depends(get_db)):
    return db.query(PendingReceipt).all()

@router.post("/receipts/{receipt_id}/confirm")
def confirm_receipt(receipt_id: int, confirm_in: schemas.ReceiptConfirmRequest, force: bool = False, db: Session = Depends(get_db)):
    pending = db.query(PendingReceipt).filter(PendingReceipt.id == receipt_id).first()
    if not pending:
        raise HTTPException(status_code=404, detail="Pending receipt not found.")
        
    if not force:
        dup = db.query(Transaction).filter(
            Transaction.date == confirm_in.date,
            Transaction.amount == confirm_in.amount,
            Transaction.description == confirm_in.merchant,
            Transaction.source == "receipt_ocr"
        ).first()
        
        if dup:
            raise HTTPException(status_code=409, detail="Possible duplicate receipt detected. Confirm again to force save.", headers={"X-Duplicate-Flag": "true"})

    tx = Transaction(
        date=confirm_in.date,
        description=confirm_in.merchant,
        amount=confirm_in.amount,
        transaction_type="debit",
        category=confirm_in.category,
        raw_text=pending.raw_text,
        source="receipt_ocr",
        receipt_image_path=pending.image_path
    )
    db.add(tx)
    db.delete(pending)
    db.commit()
    
    return {"message": "Receipt confirmed and saved."}

@router.post("/receipts/{receipt_id}/discard")
def discard_receipt(receipt_id: int, db: Session = Depends(get_db)):
    pending = db.query(PendingReceipt).filter(PendingReceipt.id == receipt_id).first()
    if not pending:
        raise HTTPException(status_code=404, detail="Pending receipt not found.")
    
    if os.path.exists(pending.image_path):
        os.remove(pending.image_path)
        
    db.delete(pending)
    db.commit()
    return {"message": "Receipt discarded."}
