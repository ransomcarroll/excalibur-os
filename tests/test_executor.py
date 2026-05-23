"""Executor tests with a fake ClaudeSDKClient so we can drive arbitrary
message streams (usage frames, marker text, etc.) without an Anthropic key."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Iterable


from excalibur import executor as exec_mod
from excalibur.executor import execute_group
from excalibur.grouper import Group
from excalibur.linear import LinearIssue


@dataclass
class FakeWS:
    branch: str = "excalibur/test-x"
    worktree_path: str = "/tmp/wt"
    repo_root: str = "/tmp/repo"


def _msg(text: str = "", input_tokens: int = 0, output_tokens: int = 0):
    blocks = [SimpleNamespace(text=text)] if text else []
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens) if (input_tokens or output_tokens) else None
    return SimpleNamespace(content=blocks, usage=usage)


class FakeClient:
    """Mimics ClaudeSDKClient's async-context-manager + receive_response shape."""

    def __init__(self, messages: Iterable):
        self._messages = list(messages)
        self.queries: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def query(self, prompt: str):
        self.queries.append(prompt)

    async def receive_response(self):
        for m in self._messages:
            yield m


def _issue(ident: str) -> LinearIssue:
    return LinearIssue(
        id=ident.lower(), identifier=ident, title=ident, description="d",
        url=f"https://x/{ident}", git_branch_name="b", label_ids=[],
    )


def _group(*idents: str) -> Group:
    return Group(name="test", issues=[_issue(i) for i in idents])


async def test_done_marker_recorded(monkeypatch):
    client = FakeClient([_msg("PLAN[ISS-1]: go\nDONE[ISS-1]\n")])
    monkeypatch.setattr(exec_mod, "ClaudeSDKClient", lambda options: client)

    result = await execute_group(_group("ISS-1"), FakeWS(), model="m", token_budget=10_000)
    assert result.done == ["ISS-1"]
    assert result.halted_reason is None
    assert client.queries  # the prompt was sent


async def test_token_budget_halts_executor(monkeypatch):
    msgs = [
        _msg(text="PLAN[ISS-1]: start"),
        _msg(input_tokens=600, output_tokens=600),  # 1200 > 1000 budget
        _msg(text="DONE[ISS-1]"),  # must not reach this
    ]
    client = FakeClient(msgs)
    monkeypatch.setattr(exec_mod, "ClaudeSDKClient", lambda options: client)

    result = await execute_group(_group("ISS-1"), FakeWS(), model="m", token_budget=1000)
    assert result.halted_reason == "token_budget"
    assert result.tokens_used == 1200
    assert result.done == []  # halted before reaching the DONE marker


async def test_blocked_marker_with_reason(monkeypatch):
    msgs = [_msg("BLOCKED[ISS-1]: tests fail and I can't fix them")]
    client = FakeClient(msgs)
    monkeypatch.setattr(exec_mod, "ClaudeSDKClient", lambda options: client)

    result = await execute_group(_group("ISS-1"), FakeWS(), model="m", token_budget=10_000)
    assert result.blocked == {"ISS-1": "tests fail and I can't fix them"}
    assert result.done == []


async def test_crash_in_client_is_captured(monkeypatch):
    class BrokenClient(FakeClient):
        async def query(self, prompt):
            raise RuntimeError("transport blew up")

    monkeypatch.setattr(exec_mod, "ClaudeSDKClient", lambda options: BrokenClient([]))

    result = await execute_group(_group("ISS-1"), FakeWS(), model="m", token_budget=10_000)
    assert result.halted_reason == "crash"
    assert "transport blew up" in (result.error or "")
