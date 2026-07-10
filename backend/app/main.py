from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database.db import engine, Base
from app.routers import transactions, agent

# Initialize tables on startup
Base.metadata.create_all(bind=engine)

# Auto-migrate: add new columns to transactions if they don't exist
try:
    with engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("ALTER TABLE transactions ADD COLUMN source VARCHAR DEFAULT 'bank_statement' NOT NULL"))
except Exception:
    pass

try:
    with engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("ALTER TABLE transactions ADD COLUMN receipt_image_path VARCHAR"))
except Exception:
    pass

app = FastAPI(
    title="Finance Agent API",
    description="Backend for AI Finance Agent statement ingestion and categorization",
    version="1.0.0"
)

import os

# CORS setup
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    os.getenv("FRONTEND_URL", ""),
    "https://financeagent-sigma.vercel.app",  # your stable production URL, hardcoded as backup
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in ALLOWED_ORIGINS if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include router
app.include_router(transactions.router, prefix="/api", tags=["transactions"])
app.include_router(agent.router, prefix="/api", tags=["agent"])
from app.routers import forecast, budgets, receipts, anomalies
app.include_router(forecast.router, prefix="/api/forecast", tags=["forecast"])
app.include_router(budgets.router, prefix="/api", tags=["budgets"])
app.include_router(receipts.router, prefix="/api", tags=["receipts"])
app.include_router(anomalies.router, prefix="/api", tags=["anomalies"])

@app.get("/")
def read_root():
    return {"message": "Welcome to AI Finance Agent API. Go to /docs for API documentation."}
