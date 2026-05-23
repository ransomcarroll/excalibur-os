from __future__ import annotations

from excalibur.harvester import (
    AGENT_READY_LABEL,
    BLOCKED_LABEL,
    FAILED_LABEL,
    SHIPPED_LABEL,
    harvest,
)
from excalibur.linear import LinearIssue


class FakeLinear:
    def __init__(self, issues: list[LinearIssue]):
        self._issues = issues
        self.ensured: list[str] = []

    def ensure_label(self, name: str, color: str = "#888888") -> str:
        self.ensured.append(name)
        return f"LBL-{name}"

    def shippable_issues(self, agent_ready_label_id: str, shipped_label_id: str):
        assert agent_ready_label_id == f"LBL-{AGENT_READY_LABEL}"
        assert shipped_label_id == f"LBL-{SHIPPED_LABEL}"
        return self._issues


def _issue(ident: str) -> LinearIssue:
    return LinearIssue(
        id=ident.lower(), identifier=ident, title=ident, description="",
        url=f"https://x/{ident}", git_branch_name="b", label_ids=[],
    )


def test_harvest_ensures_all_excalibur_labels():
    lin = FakeLinear(issues=[])
    harvest(lin, max_issues=10)
    assert AGENT_READY_LABEL in lin.ensured
    assert SHIPPED_LABEL in lin.ensured
    assert BLOCKED_LABEL in lin.ensured
    assert FAILED_LABEL in lin.ensured


def test_harvest_caps_at_max_issues():
    lin = FakeLinear(issues=[_issue(f"ISS-{i}") for i in range(20)])
    out = harvest(lin, max_issues=5)
    assert len(out) == 5
    assert [i.identifier for i in out] == [f"ISS-{i}" for i in range(5)]


def test_harvest_returns_all_when_under_cap():
    lin = FakeLinear(issues=[_issue("ISS-1"), _issue("ISS-2")])
    out = harvest(lin, max_issues=10)
    assert len(out) == 2
