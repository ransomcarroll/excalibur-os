"""Small retry helper shared by the Linear and GitHub clients.

External APIs flake. We retry on 429 and 5xx with bounded exponential backoff.
Anything else (4xx besides 429, network errors) propagates immediately.
"""

from __future__ import annotations

import random
import time
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)


RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_attempts: int = 4,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    label: str = "http",
    **kwargs: Any,
) -> httpx.Response:
    """Issue a request, retrying retryable failures with exponential backoff + jitter.

    Honors `Retry-After` (seconds or HTTP date) when present on a 429/5xx. The caller
    is still responsible for `raise_for_status()` — we only retry; we don't decide
    whether a 4xx is fatal in the caller's domain.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            r = client.request(method, url, **kwargs)
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last_exc = e
            delay = _backoff(attempt, base_delay, max_delay)
            log.warning(
                "http_retry_transport",
                label=label,
                attempt=attempt,
                max_attempts=max_attempts,
                err=str(e),
                sleep=delay,
            )
            if attempt == max_attempts:
                raise
            time.sleep(delay)
            continue

        if r.status_code not in RETRYABLE_STATUSES or attempt == max_attempts:
            return r

        delay = _retry_after(r) or _backoff(attempt, base_delay, max_delay)
        log.warning(
            "http_retry_status",
            label=label,
            attempt=attempt,
            max_attempts=max_attempts,
            status=r.status_code,
            sleep=delay,
        )
        time.sleep(delay)

    # Unreachable: the loop either returns or raises before falling out.
    raise RuntimeError(f"unreachable: retry loop fell through ({last_exc})")


def _backoff(attempt: int, base: float, ceiling: float) -> float:
    raw = base * (2 ** (attempt - 1))
    jitter = random.uniform(0.0, base)
    return min(raw + jitter, ceiling)


def _retry_after(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None  # HTTP-date form is rare for these APIs; fall back to backoff.
