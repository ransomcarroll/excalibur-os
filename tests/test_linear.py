from __future__ import annotations

import json

import httpx
import pytest

from excalibur import http_utils
from excalibur.linear import LinearClient


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(http_utils.time, "sleep", lambda _s: None)


class _Recorder:
    """Programmable mock transport: hands out responses in order, captures payloads."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        payload = json.loads(req.content.decode("utf-8")) if req.content else {}
        self.calls.append({"path": req.url.path, "payload": payload})
        return self._responses.pop(0)


def _client(transport: _Recorder) -> LinearClient:
    inner = httpx.Client(
        transport=httpx.MockTransport(transport),
        base_url="https://api.linear.app",
        headers={"Authorization": "test"},
    )
    return LinearClient(api_key="test", team_id="TEAM", client=inner)


def _gql_ok(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


def test_shippable_issues_parses_nodes():
    t = _Recorder([
        _gql_ok({
            "issues": {
                "nodes": [
                    {
                        "id": "abc",
                        "identifier": "ISS-1",
                        "title": "do the thing",
                        "description": "details",
                        "url": "https://linear.app/team/issue/ISS-1",
                        "branchName": "iss-1-do-the-thing",
                        "labels": {"nodes": [{"id": "L1"}, {"id": "L2"}]},
                    }
                ]
            }
        })
    ])
    c = _client(t)
    issues = c.shippable_issues("ready", "shipped")
    assert len(issues) == 1
    assert issues[0].identifier == "ISS-1"
    assert issues[0].label_ids == ["L1", "L2"]


def test_find_label_id_case_insensitive():
    t = _Recorder([
        _gql_ok({"team": {"labels": {"nodes": [{"id": "L9", "name": "Agent-Ready"}]}}})
    ])
    c = _client(t)
    assert c.find_label_id("agent-ready") == "L9"


def test_find_label_id_returns_none_when_missing():
    t = _Recorder([
        _gql_ok({"team": {"labels": {"nodes": []}}})
    ])
    c = _client(t)
    assert c.find_label_id("agent-ready") is None


def test_ensure_label_idempotent_when_present():
    t = _Recorder([
        _gql_ok({"team": {"labels": {"nodes": [{"id": "L9", "name": "agent-ready"}]}}}),
    ])
    c = _client(t)
    assert c.ensure_label("agent-ready") == "L9"
    assert len(t.calls) == 1  # didn't issue a create mutation


def test_ensure_label_creates_when_missing():
    t = _Recorder([
        _gql_ok({"team": {"labels": {"nodes": []}}}),
        _gql_ok({"issueLabelCreate": {"issueLabel": {"id": "NEW"}}}),
    ])
    c = _client(t)
    assert c.ensure_label("needs-triage") == "NEW"
    assert len(t.calls) == 2


def test_add_label_skips_when_already_present():
    t = _Recorder([
        _gql_ok({"issue": {"labels": {"nodes": [{"id": "L1"}]}}}),
    ])
    c = _client(t)
    assert c.add_label("issue-id", "L1") is False
    assert len(t.calls) == 1  # no mutation issued


def test_add_label_unions_existing_labels():
    t = _Recorder([
        _gql_ok({"issue": {"labels": {"nodes": [{"id": "L1"}]}}}),
        _gql_ok({"issueUpdate": {"success": True}}),
    ])
    c = _client(t)
    assert c.add_label("issue-id", "L2") is True
    second = t.calls[1]
    label_ids = second["payload"]["variables"]["labelIds"]
    assert set(label_ids) == {"L1", "L2"}


def test_graphql_error_raises():
    t = _Recorder([
        httpx.Response(200, json={"errors": [{"message": "bad query"}]}),
    ])
    c = _client(t)
    with pytest.raises(RuntimeError) as ex:
        c.find_label_id("x")
    assert "Linear GraphQL error" in str(ex.value)


def test_retries_on_5xx_then_succeeds():
    t = _Recorder([
        httpx.Response(503, text="busy"),
        _gql_ok({"team": {"labels": {"nodes": []}}}),
    ])
    c = _client(t)
    assert c.find_label_id("x") is None
    assert len(t.calls) == 2  # one retry
