"""Scheduler orchestration tests.

We mock the leaf-level modules (LinearClient, GitHubClient, WorkspaceManager,
group_issues, execute_group) and assert the scheduler does the right thing
with them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from excalibur import scheduler as sched_mod
from excalibur.executor import ExecutionResult
from excalibur.grouper import Group
from excalibur.linear import LinearIssue
from excalibur.scheduler import run_shipment


# --- shared fakes ---------------------------------------------------------


@dataclass
class FakeWorkspace:
    branch: str
    worktree_path: str = "/fake/wt"
    repo_root: str = "/fake/repo"


class FakeLinear:
    def __init__(self, *a, **kw): self.calls: list = []


class FakeGH:
    def __init__(self, *a, **kw):
        self.opened: list[dict] = []

    def open_pr(self, *, head, base, title, body, draft):
        self.opened.append({"head": head, "base": base, "title": title, "body": body, "draft": draft})
        return f"https://github.com/owner/repo/pull/{len(self.opened)}"


class FakeWM:
    def __init__(self, *a, **kw):
        self.created: list[str] = []
        self.cleaned: list[str] = []
        self.pushed: list[str] = []
        self.has_commits_map: dict[str, bool] = {}
        self.crash_group: str | None = None
        self.repo_root = "/fake/repo"

    def ensure_repo(self):
        pass

    def create_worktree(self, name: str):
        if self.crash_group == name:
            raise RuntimeError("simulated worktree failure")
        self.created.append(name)
        return FakeWorkspace(branch=f"excalibur/{name}-x")

    def cleanup_worktree(self, ws):
        self.cleaned.append(ws.branch)

    def has_commits(self, ws) -> bool:
        return self.has_commits_map.get(ws.branch.split("/", 1)[1].rsplit("-", 1)[0], True)

    def push(self, ws):
        self.pushed.append(ws.branch)


def _settings(**overrides) -> Any:
    """Minimal duck-typed settings; pydantic isn't needed here."""
    base = dict(
        anthropic_api_key="ak",
        github_token="gt",
        linear_api_key="lk",
        linear_team_id="team",
        linear_project_id=None,
        github_repo="owner/repo",
        excalibur_base_branch="dev",
        excalibur_max_issues_per_shipment=8,
        excalibur_token_budget_per_group=10000,
        excalibur_workdir="/tmp",
        excalibur_executor_timeout_seconds=3600,
        slack_webhook_url=None,
        model="claude-test",
    )
    base.update(overrides)
    return type("S", (), base)


def _issue(ident: str) -> LinearIssue:
    return LinearIssue(
        id=ident.lower(), identifier=ident, title=f"{ident} title",
        description="d", url=f"https://x/{ident}", git_branch_name=f"b-{ident}",
        label_ids=[],
    )


# --- the actual tests -----------------------------------------------------


@pytest.fixture
def patched(monkeypatch):
    """Replace external collaborators with fakes. Returns the fakes for assertion."""
    fake_linear = FakeLinear()
    fake_gh = FakeGH()
    fake_wm = FakeWM()

    monkeypatch.setattr(sched_mod, "LinearClient", lambda *a, **kw: fake_linear)
    monkeypatch.setattr(sched_mod, "GitHubClient", lambda *a, **kw: fake_gh)
    monkeypatch.setattr(sched_mod, "WorkspaceManager", lambda *a, **kw: fake_wm)

    return {"linear": fake_linear, "gh": fake_gh, "wm": fake_wm}


async def test_nothing_to_ship(patched, monkeypatch):
    monkeypatch.setattr(sched_mod, "harvest", lambda *_: [])
    await run_shipment(_settings(), dry_run=False)
    assert patched["wm"].created == []
    assert patched["gh"].opened == []


async def test_dry_run_groups_but_doesnt_execute(patched, monkeypatch):
    issues = [_issue("ISS-1"), _issue("ISS-2")]
    monkeypatch.setattr(sched_mod, "harvest", lambda *_: issues)
    grouped = [Group(name="g1", issues=issues, rationale="r")]

    async def fake_group(*a, **kw):
        return grouped
    monkeypatch.setattr(sched_mod, "group_issues", fake_group)

    called = {"n": 0}

    async def must_not_run(*a, **kw):
        called["n"] += 1
        return None
    monkeypatch.setattr(sched_mod, "execute_group", must_not_run)

    await run_shipment(_settings(), dry_run=True)
    assert called["n"] == 0
    assert patched["wm"].created == []


async def test_only_filter_restricts_issues(patched, monkeypatch):
    issues = [_issue("ISS-1"), _issue("ISS-2"), _issue("ISS-3")]
    monkeypatch.setattr(sched_mod, "harvest", lambda *_: issues)

    seen_in_grouper: list[str] = []

    async def fake_group(issues_in, *a, **kw):
        seen_in_grouper.extend(i.identifier for i in issues_in)
        return []
    monkeypatch.setattr(sched_mod, "group_issues", fake_group)

    await run_shipment(_settings(), dry_run=True, only=["ISS-2"])
    assert seen_in_grouper == ["ISS-2"]


async def test_happy_path_one_group_one_issue(patched, monkeypatch):
    issues = [_issue("ISS-1")]
    monkeypatch.setattr(sched_mod, "harvest", lambda *_: issues)
    monkeypatch.setattr(sched_mod, "report_group", lambda *a, **kw: None)
    grouped = [Group(name="g1", issues=issues, rationale="r")]

    async def fake_group(*a, **kw):
        return grouped
    monkeypatch.setattr(sched_mod, "group_issues", fake_group)

    async def fake_exec(group, ws, model, budget, *, timeout_seconds=None):
        return ExecutionResult(
            group=group, workspace=ws, done=[i.identifier for i in group.issues],
        )
    monkeypatch.setattr(sched_mod, "execute_group", fake_exec)

    await run_shipment(_settings(), dry_run=False)
    assert patched["wm"].created == ["g1"]
    assert patched["wm"].pushed == ["excalibur/g1-x"]
    assert len(patched["gh"].opened) == 1
    assert patched["wm"].cleaned == ["excalibur/g1-x"]


async def test_no_commits_skips_pr(patched, monkeypatch):
    issues = [_issue("ISS-1")]
    monkeypatch.setattr(sched_mod, "harvest", lambda *_: issues)
    monkeypatch.setattr(sched_mod, "report_group", lambda *a, **kw: None)

    grouped = [Group(name="empty", issues=issues, rationale="r")]

    async def fake_group(*a, **kw):
        return grouped
    monkeypatch.setattr(sched_mod, "group_issues", fake_group)

    patched["wm"].has_commits_map = {"empty": False}

    async def fake_exec(group, ws, model, budget, *, timeout_seconds=None):
        return ExecutionResult(group=group, workspace=ws, done=[])
    monkeypatch.setattr(sched_mod, "execute_group", fake_exec)

    await run_shipment(_settings(), dry_run=False)
    assert patched["wm"].pushed == []
    assert patched["gh"].opened == []
    assert patched["wm"].cleaned == ["excalibur/empty-x"]


async def test_one_group_crash_does_not_kill_shipment(patched, monkeypatch):
    issues = [_issue("ISS-1"), _issue("ISS-2")]
    monkeypatch.setattr(sched_mod, "harvest", lambda *_: issues)
    monkeypatch.setattr(sched_mod, "report_group", lambda *a, **kw: None)

    grouped = [
        Group(name="bad", issues=[issues[0]], rationale="r"),
        Group(name="good", issues=[issues[1]], rationale="r"),
    ]

    async def fake_group(*a, **kw):
        return grouped
    monkeypatch.setattr(sched_mod, "group_issues", fake_group)
    patched["wm"].crash_group = "bad"

    async def fake_exec(group, ws, model, budget, *, timeout_seconds=None):
        return ExecutionResult(
            group=group, workspace=ws, done=[i.identifier for i in group.issues],
        )
    monkeypatch.setattr(sched_mod, "execute_group", fake_exec)

    await run_shipment(_settings(), dry_run=False)
    # The crashing group never created a worktree, so "good" is the only one created.
    assert patched["wm"].created == ["good"]
    assert len(patched["gh"].opened) == 1
    assert patched["gh"].opened[0]["head"] == "excalibur/good-x"
