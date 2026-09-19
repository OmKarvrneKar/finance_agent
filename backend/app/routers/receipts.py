import os
import io
import uuid
import shutil
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError

from app.database.db import get_db, PendingReceipt, Transaction
from app.models import schemas
from app.services import receipts

router = APIRouter()

UPLOAD_DIR = "uploads/receipts"
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_RECEIPT_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}

@router.post("/receipts/upload", response_model=schemas.PendingReceiptResponse)
async def upload_receipt(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1. Read file bytes
    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {str(e)}")
    
    # 2. Check file size
    if len(file_bytes) > MAX_RECEIPT_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size is {MAX_RECEIPT_SIZE // (1024*1024)}MB.")
    
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    
    # 3. Validate actual image content using Pillow
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
        # After verify(), we need to reopen to get format
        img = Image.open(io.BytesIO(file_bytes))
        img_format = img.format
    except DecompressionBombError:
        raise HTTPException(status_code=400, detail="Image file is too large or potentially malicious.")
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {str(e)}")
    
    # 4. Validate extension matches actual format
    if not img_format:
        raise HTTPException(status_code=400, detail="Could not determine image format.")
    
    format_to_ext = {
        'JPEG': 'jpg',
        'PNG': 'png',
        'GIF': 'gif',
        'WEBP': 'webp',
    }
    ext = format_to_ext.get(img_format, img_format.lower())
    
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Image format '{ext}' is not supported. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}")
    
    # 5. Generate random server-side filename
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    # 6. Write file to disk
    try:
        with open(file_path, "wb") as buffer:
            buffer.write(file_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save receipt image: {str(e)}")
    
    # 7. OCR extraction
    try:
        raw_text = receipts.extract_receipt_text(file_path)
    except Exception as e:
        # Still save the pending receipt even if OCR fails
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
        
    # 8. AI parsing
    parsed = receipts.parse_receipt_with_ai(raw_text)
    
    dt = None
    if parsed.get("date"):
        try:
            dt = datetime.strptime(parsed["date"], "%Y-%m-%d").date()
        except Exception:
            dt = None
            
    pending = PendingReceipt(
        image_path=file_path,
        raw_text=raw_text,
        merchant=parsed.get("merchant"),
        amount=Decimal(str(parsed["amount"])) if parsed.get("amount") is not None else None,
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
            Transaction.amount == Decimal(str(confirm_in.amount)),
            Transaction.description == confirm_in.merchant,
            Transaction.source == "receipt_ocr"
        ).first()
        
        if dup:
            raise HTTPException(status_code=409, detail="Possible duplicate receipt detected. Confirm again to force save.", headers={"X-Duplicate-Flag": "true"})

    tx = Transaction(
        date=confirm_in.date,
        description=confirm_in.merchant,
        amount=Decimal(str(confirm_in.amount)),
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
