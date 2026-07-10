from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services import forecasting
from datetime import datetime

router = APIRouter()

@router.get("/summary")
def get_forecast_summary(month: str = Query(None, description="YYYY-MM format"), db: Session = Depends(get_db)):
    if not month:
        month = datetime.today().strftime("%Y-%m")
    
    forecast_data = forecasting.forecast_month_end_spend(None, month, db)
    hist_data = forecasting.get_historical_average(None, db, num_past_months=3, exclude_month=month)
    
    return {
        "month": month,
        "forecast": forecast_data,
        "historical": hist_data
    }

@router.get("/alerts")
def get_forecast_alerts(month: str = Query(None, description="YYYY-MM format"), db: Session = Depends(get_db)):
    if not month:
        month = datetime.today().strftime("%Y-%m")
    return forecasting.generate_overspend_alerts(db, month)

@router.get("/category/{category_name}")
def get_category_forecast(category_name: str, month: str = Query(None, description="YYYY-MM format"), db: Session = Depends(get_db)):
    if not month:
        month = datetime.today().strftime("%Y-%m")
        
    forecast_data = forecasting.forecast_month_end_spend(category_name, month, db)
    hist_data = forecasting.get_historical_average(category_name, db, num_past_months=3, exclude_month=month)
    
    return {
        "category": category_name,
        "month": month,
        "forecast": forecast_data,
        "historical": hist_data
    }
