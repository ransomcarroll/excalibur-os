from __future__ import annotations


from excalibur.executor import ExecutionResult
from excalibur.grouper import Group
from excalibur.harvester import BLOCKED_LABEL, FAILED_LABEL, SHIPPED_LABEL
from excalibur.linear import LinearIssue
from excalibur.reporter import report_group


class FakeLinear:
    def __init__(self):
        self.added: list[tuple[str, str]] = []
        self.comments: list[tuple[str, str]] = []

    def ensure_label(self, name: str, color: str = "#888888") -> str:
        return f"LBL-{name}"

    def add_label(self, issue_id: str, label_id: str) -> bool:
        self.added.append((issue_id, label_id))
        return True

    def comment(self, issue_id: str, body: str) -> None:
        self.comments.append((issue_id, body))


def _issue(ident: str) -> LinearIssue:
    return LinearIssue(
        id=ident.lower(), identifier=ident, title=ident,
        description="", url=f"https://x/{ident}", git_branch_name="b",
        label_ids=[],
    )


def _result(group: Group, done=(), blocked=None):
    return ExecutionResult(
        group=group, workspace=None,
        done=list(done), blocked=dict(blocked or {}),
    )


def test_done_issues_get_shipped_label_and_comment():
    lin = FakeLinear()
    g = Group(name="g", issues=[_issue("A-1")])
    r = _result(g, done=["A-1"])
    report_group(lin, r, pr_url="https://github.com/o/r/pull/3")

    assert ("a-1", f"LBL-{SHIPPED_LABEL}") in lin.added
    assert any("https://github.com/o/r/pull/3" in body for _, body in lin.comments)


def test_blocked_issues_get_blocked_label_and_reason():
    lin = FakeLinear()
    g = Group(name="g", issues=[_issue("A-1")])
    r = _result(g, blocked={"A-1": "needs design"})
    report_group(lin, r, pr_url=None)

    assert ("a-1", f"LBL-{BLOCKED_LABEL}") in lin.added
    assert any("needs design" in body for _, body in lin.comments)


def test_unhandled_issues_get_failed_label():
    lin = FakeLinear()
    g = Group(name="g", issues=[_issue("A-1"), _issue("A-2")])
    # A-1 done, A-2 has no marker at all (executor crashed mid-stream).
    r = _result(g, done=["A-1"])
    report_group(lin, r, pr_url="https://x")

    failed_calls = [c for c in lin.added if c[1] == f"LBL-{FAILED_LABEL}"]
    assert failed_calls == [("a-2", f"LBL-{FAILED_LABEL}")]


def test_no_pr_url_means_no_shipped_comment_link():
    lin = FakeLinear()
    g = Group(name="g", issues=[_issue("A-1")])
    r = _result(g, done=["A-1"])
    report_group(lin, r, pr_url=None)
    # Issue still gets the shipped label but no PR-link comment.
    assert ("a-1", f"LBL-{SHIPPED_LABEL}") in lin.added
    assert lin.comments == []  # no PR url → no shipped-by-PR comment
