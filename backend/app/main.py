import os
import logging
from dotenv import load_dotenv
load_dotenv()

from app.config import validate_startup
validate_startup()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.database.db import engine, Base
from app.routers import transactions, agent, auth, goals, savings_recommendations, reports, splits, recurring_calendar, notifications

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Finance Agent API",
    description="Backend for AI Finance Agent statement ingestion and categorization",
    version="1.0.0"
)

# --- Security Headers Middleware ---


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        if os.getenv("ENVIRONMENT", "development").lower() == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)

# --- Global Exception Handler ---


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


# --- CORS Setup ---

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    os.getenv("FRONTEND_URL", ""),
    "https://financeagent-sigma.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in ALLOWED_ORIGINS if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include router
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(transactions.router, prefix="/api", tags=["transactions"])
app.include_router(agent.router, prefix="/api", tags=["agent"])
from app.routers import forecast, budgets, receipts, anomalies, analytics, health
app.include_router(forecast.router, prefix="/api/forecast", tags=["forecast"])
app.include_router(budgets.router, prefix="/api", tags=["budgets"])
app.include_router(receipts.router, prefix="/api", tags=["receipts"])
app.include_router(anomalies.router, prefix="/api", tags=["anomalies"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(goals.router, prefix="/api", tags=["goals"])
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(savings_recommendations.router, prefix="/api", tags=["savings-recommendations"])
app.include_router(reports.router, prefix="/api", tags=["reports"])
app.include_router(splits.router, prefix="/api", tags=["splits"])
app.include_router(recurring_calendar.router, prefix="/api", tags=["recurring-calendar"])
app.include_router(notifications.router, prefix="/api", tags=["notifications"])

@app.get("/")
def read_root():
    return {"message": "Welcome to AI Finance Agent API. Go to /docs for API documentation."}
