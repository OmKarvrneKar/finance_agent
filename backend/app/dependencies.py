"""
Rate limiting dependencies for FastAPI.

IMPORTANT: This is an in-memory, IP-based rate limiter.
It is NOT suitable for production deployments with multiple backend instances,
as each instance maintains its own state. For production, use a distributed
rate limiter backed by Redis or similar.
"""

import os
import time
from collections import defaultdict
from fastapi import HTTPException, Request

# In-memory store — per-process, not shared across instances
_rate_store: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

# Configurable limits via environment variables
WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
AUTH_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_AUTH_MAX", "10"))
REGISTER_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_REGISTER_MAX", "5"))
UPLOAD_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_UPLOAD_MAX", "10"))
AGENT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_AGENT_MAX", "10"))


def _make_rate_limiter(max_requests: int, window: int = WINDOW_SECONDS):
    """
    Factory that returns a FastAPI dependency limiting requests per IP
    within a time window.
    """
    async def rate_limit_dependency(request: Request):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        key = f"{client_ip}:{max_requests}"

        # Clean up old entries outside the window
        _rate_store[key][client_ip] = [
            t for t in _rate_store[key][client_ip] if now - t < window
        ]

        # Check limit
        if len(_rate_store[key][client_ip]) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
            )

        # Record this request
        _rate_store[key][client_ip].append(now)

    return rate_limit_dependency


# Pre-built dependencies for common endpoints
auth_rate_limit = _make_rate_limiter(AUTH_MAX_REQUESTS)
register_rate_limit = _make_rate_limiter(REGISTER_MAX_REQUESTS)
upload_rate_limit = _make_rate_limiter(UPLOAD_MAX_REQUESTS)
rate_limit_dependency = _make_rate_limiter(AGENT_MAX_REQUESTS)
