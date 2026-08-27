from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from datetime import date
import logging

from app.database.db import get_db, User
from app.auth import get_current_user
from app.services.report_service import get_monthly_report_data
from app.services.pdf_generator import generate_monthly_pdf

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/reports/monthly")
def get_monthly_report(
    year: int = Query(..., description="Year (YYYY)"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        date(year, month, 1)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid year or month.")

    report_data = get_monthly_report_data(db, current_user.id, year, month)
    pdf_bytes = generate_monthly_pdf(report_data)

    filename = f"financial_report_{year}_{month:02d}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
