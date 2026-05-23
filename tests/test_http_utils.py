from __future__ import annotations

from itertools import count

import httpx
import pytest

from excalibur import http_utils
from excalibur.http_utils import request_with_retry


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Make retry delays instantaneous so tests stay fast."""
    monkeypatch.setattr(http_utils.time, "sleep", lambda _s: None)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")


def test_returns_on_first_success():
    calls = count()
    def handler(req):
        next(calls)
        return httpx.Response(200, text="ok")
    c = _client(handler)
    r = request_with_retry(c, "GET", "/")
    assert r.status_code == 200
    assert next(calls) == 1  # exactly one call


def test_retries_then_succeeds():
    counter = iter([500, 503, 200])
    seen = []
    def handler(req):
        code = next(counter)
        seen.append(code)
        return httpx.Response(code, text=str(code))
    c = _client(handler)
    r = request_with_retry(c, "GET", "/", max_attempts=4)
    assert r.status_code == 200
    assert seen == [500, 503, 200]


def test_gives_up_after_max_attempts_and_returns_last_response():
    def handler(req):
        return httpx.Response(503, text="nope")
    c = _client(handler)
    r = request_with_retry(c, "GET", "/", max_attempts=3)
    assert r.status_code == 503


def test_does_not_retry_on_non_retryable_4xx():
    seen = []
    def handler(req):
        seen.append(1)
        return httpx.Response(400, json={"error": "bad"})
    c = _client(handler)
    r = request_with_retry(c, "GET", "/", max_attempts=3)
    assert r.status_code == 400
    assert sum(seen) == 1


def test_retries_on_transport_error():
    counter = iter([httpx.ConnectError("boom"), httpx.Response(200, text="ok")])
    def handler(req):
        item = next(counter)
        if isinstance(item, BaseException):
            raise item
        return item
    c = _client(handler)
    r = request_with_retry(c, "GET", "/", max_attempts=3)
    assert r.status_code == 200


def test_honors_retry_after_seconds(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(http_utils.time, "sleep", lambda s: slept.append(s))
    counter = iter([
        httpx.Response(429, headers={"Retry-After": "0.25"}, text="wait"),
        httpx.Response(200, text="ok"),
    ])
    def handler(req):
        return next(counter)
    c = _client(handler)
    r = request_with_retry(c, "GET", "/", max_attempts=3)
    assert r.status_code == 200
    assert slept == [0.25]
