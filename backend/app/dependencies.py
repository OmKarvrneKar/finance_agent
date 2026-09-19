"""
Rate limiting dependency for FastAPI.

IMPORTANT: This is an in-memory, IP-based rate limiter.
It is NOT suitable for production deployments with multiple backend instances,
as each instance maintains its own state. For production, use a distributed
rate limiter backed by Redis or similar.
"""

import time
from collections import defaultdict
from fastapi import HTTPException, Request

# In-memory store — per-process, not shared across instances
_rate_store: dict[str, list[float]] = defaultdict(list)

# Configuration
WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 10


async def rate_limit_dependency(request: Request):
    """
    FastAPI dependency that limits requests per IP within a time window.
    Apply this to specific endpoints via Depends(rate_limit_dependency).
    
    Usage:
        @router.post("/agent/ask", dependencies=[Depends(rate_limit_dependency)])
        def ask_agent(...):
            ...
    """
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Clean up old entries outside the window
    _rate_store[client_ip] = [
        t for t in _rate_store[client_ip] if now - t < WINDOW_SECONDS
    ]
    
    # Check limit
    if len(_rate_store[client_ip]) >= MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later."
        )
    
    # Record this request
    _rate_store[client_ip].append(now)
