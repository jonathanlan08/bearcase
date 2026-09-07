"""In-memory token-bucket rate limiter for the routes that cost the most.

One bucket per key: a signed-in user id, or the client address before sign-in. A bucket holds
`rate_limit_per_minute` tokens and refills continuously at that rate, so a short burst is fine and a sustained
flood is refused with 429 and a Retry-After header. State lives in this process only: with several API
processes each one enforces its own budget, and a public deployment still needs a shared limiter and body-size
limits at the ingress.

Authenticated routes are matched in `bearcase.api.deps.current_user` against RATE_LIMITED_ROUTES; routes without a
user (demo start, and sign-in if wired) take the explicit `rate_limited` dependency, keyed by client address.
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from bearcase.config import get_settings

# Method and path of every route that parses a file, runs analysis, seeds a deal, or calls a model. Reads and
# plain row writes are not listed: they are cheap and the deal is owner-scoped anyway.
RATE_LIMITED_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("POST", re.compile(r"^/api/demo/(session|reset)$")),
    ("POST", re.compile(r"^/api/deals/[^/]+/documents$")),
    ("POST", re.compile(r"^/api/deals/[^/]+/documents/[^/]+/reprocess$")),
    ("POST", re.compile(r"^/api/deals/[^/]+/process$")),
    ("POST", re.compile(r"^/api/deals/[^/]+/chat$")),
    ("POST", re.compile(r"^/api/deals/[^/]+/ask$")),
    ("POST", re.compile(r"^/api/deals/[^/]+/report$")),
)

_PRUNE_ABOVE = 10_000  # buckets kept before idle ones are dropped
_IDLE_SECONDS = 60.0  # a bucket idle this long is full again, so forgetting it changes nothing


@dataclass
class _Bucket:
    tokens: float
    updated: float


class TokenBucketLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str, per_minute: int) -> float | None:
        """Take one token for `key`. Returns None when the request may proceed, otherwise the seconds to wait."""
        capacity = max(1, per_minute)
        rate = capacity / 60.0
        now = self._clock()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= _PRUNE_ABOVE:
                    self._prune(now)  # idle buckets are full again, so forgetting them changes nothing
                bucket = self._buckets[key] = _Bucket(tokens=float(capacity), updated=now)
            else:
                bucket.tokens = min(float(capacity), bucket.tokens + (now - bucket.updated) * rate)
                bucket.updated = now
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return None
            if len(self._buckets) > _PRUNE_ABOVE:
                self._prune(now)
            return (1.0 - bucket.tokens) / rate

    def _prune(self, now: float) -> None:
        for key in [k for k, b in self._buckets.items() if now - b.updated > _IDLE_SECONDS]:
            del self._buckets[key]

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def __len__(self) -> int:
        return len(self._buckets)


limiter = TokenBucketLimiter()


def client_key(request: Request) -> str:
    """Bucket key for a request without a signed-in user: the client address."""
    host = request.client.host if request.client else "unknown"
    if get_settings().trust_proxy_headers:
        # The rightmost hop was appended by the proxy in front of us; earlier hops are client-supplied.
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
        if forwarded:
            host = forwarded
    return f"ip:{host}"


def user_key(user_id: object) -> str:
    return f"user:{user_id}"


def is_rate_limited_route(request: Request) -> bool:
    path = request.url.path
    return any(request.method == method and pattern.match(path) for method, pattern in RATE_LIMITED_ROUTES)


def enforce(request: Request, key: str) -> None:
    """Charge one request to `key`; raise 429 with Retry-After when the budget is spent. No-op when disabled."""
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return
    wait = limiter.acquire(key, settings.rate_limit_per_minute)
    if wait is None:
        return
    seconds = max(1, math.ceil(wait))
    raise HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many requests. Try again in {seconds} second{'s' if seconds != 1 else ''}.",
        headers={"Retry-After": str(seconds)},
    )


def rate_limited(request: Request) -> None:
    """Dependency for routes that run before sign-in (demo start; sign-in and registration if added)."""
    enforce(request, client_key(request))


RateLimited = Annotated[None, Depends(rate_limited)]
