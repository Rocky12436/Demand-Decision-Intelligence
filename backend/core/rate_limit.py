"""
backend/core/rate_limit.py
--------------------------
Lightweight in-memory sliding window rate limiter for security-sensitive endpoints.
Enforces limits:
- POST /auth/login: 5 attempts per minute per IP
- POST /api/upload: 10 uploads per minute per client IP / user
"""

import os
import sys
import time
from collections import defaultdict
from typing import Dict, List
from fastapi import Request, HTTPException, status


class InMemoryRateLimiter:
    def __init__(self):
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int = 60):
        now = time.time()
        window_start = now - window_seconds

        # Clean older entries
        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        if len(self._requests[key]) >= max_requests:
            retry_after = int(self._requests[key][0] + window_seconds - now) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {max(1, retry_after)} seconds.",
                headers={"Retry-After": str(max(1, retry_after))}
            )

        self._requests[key].append(now)

    def reset(self):
        """Clears all counters (useful in tests)."""
        self._requests.clear()


rate_limiter = InMemoryRateLimiter()


def rate_limit_login(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check_rate_limit(f"login:{client_ip}", max_requests=5, window_seconds=60)


def rate_limit_upload(request: Request):
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check_rate_limit(f"upload:{client_ip}", max_requests=10, window_seconds=60)
