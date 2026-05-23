from __future__ import annotations

import httpx
import pytest

from excalibur import http_utils
from excalibur.github_client import GitHubClient


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(http_utils.time, "sleep", lambda _s: None)


class _Recorder:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append({"method": req.method, "url": str(req.url)})
        return self.handler(req)


def _client(handler) -> GitHubClient:
    inner = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.github.com",
    )
    return GitHubClient(token="t", repo="owner/repo", client=inner)


def test_open_pr_returns_html_url():
    def handler(req):
        assert req.method == "POST"
        assert req.url.path == "/repos/owner/repo/pulls"
        return httpx.Response(201, json={"html_url": "https://github.com/owner/repo/pull/1"})

    c = _client(handler)
    url = c.open_pr(head="b", base="dev", title="t", body="b")
    assert url == "https://github.com/owner/repo/pull/1"


def test_open_pr_reuses_when_already_exists():
    state = {"phase": "post"}

    def handler(req):
        if state["phase"] == "post":
            state["phase"] = "list"
            return httpx.Response(
                422,
                json={
                    "message": "Validation Failed",
                    "errors": [{"message": "A pull request already exists for owner:b."}],
                },
            )
        # list call
        assert req.method == "GET"
        assert "/pulls" in req.url.path
        assert "head=owner%3Ab" in str(req.url) or "owner:b" in str(req.url)
        return httpx.Response(200, json=[{"html_url": "https://github.com/owner/repo/pull/7"}])

    c = _client(handler)
    url = c.open_pr(head="b", base="dev", title="t", body="b")
    assert url == "https://github.com/owner/repo/pull/7"


def test_open_pr_raises_on_other_422():
    def handler(req):
        return httpx.Response(
            422,
            json={"message": "Validation Failed", "errors": [{"message": "No commits between dev and b"}]},
        )

    c = _client(handler)
    with pytest.raises(RuntimeError) as ex:
        c.open_pr(head="b", base="dev", title="t", body="b")
    assert "PR open rejected" in str(ex.value)


def test_open_pr_retries_on_503():
    state = {"count": 0}

    def handler(req):
        state["count"] += 1
        if state["count"] == 1:
            return httpx.Response(503, text="busy")
        return httpx.Response(201, json={"html_url": "https://github.com/owner/repo/pull/9"})

    c = _client(handler)
    url = c.open_pr(head="b", base="dev", title="t", body="b")
    assert url.endswith("/9")
    assert state["count"] == 2


def test_get_pr_for_branch_returns_none_when_empty():
    def handler(req):
        return httpx.Response(200, json=[])

    c = _client(handler)
    assert c.get_pr_for_branch("never-pushed") is None
