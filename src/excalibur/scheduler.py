"""Orchestrate a full shipment: harvest → group → execute → push → PR → report."""

from __future__ import annotations

import structlog

from excalibur.config import Settings
from excalibur.executor import ExecutionResult, execute_group
from excalibur.github_client import GitHubClient
from excalibur.grouper import Group, group_issues
from excalibur.harvester import harvest
from excalibur.linear import LinearClient
from excalibur.reporter import report_group, slack_summary
from excalibur.worktree import WorkspaceManager

log = structlog.get_logger(__name__)


async def run_shipment(
    settings: Settings,
    *,
    dry_run: bool = False,
    only: list[str] | None = None,
) -> None:
    linear = LinearClient(
        settings.linear_api_key, settings.linear_team_id, settings.linear_project_id
    )
    gh = GitHubClient(settings.github_token, settings.github_repo)
    wm = WorkspaceManager(
        workdir=settings.excalibur_workdir,
        github_repo=settings.github_repo,
        github_token=settings.github_token,
        base_branch=settings.excalibur_base_branch,
    )

    issues = harvest(linear, settings.excalibur_max_issues_per_shipment)
    if only:
        wanted = {x.strip() for x in only}
        issues = [i for i in issues if i.identifier in wanted]

    if not issues:
        log.info("nothing_to_ship")
        return

    wm.ensure_repo()
    groups = await group_issues(issues, wm.repo_root, settings.model)
    log.info(
        "groups_planned",
        groups=[{"name": g.name, "issues": [i.identifier for i in g.issues]} for g in groups],
    )

    if dry_run:
        return

    results: list[ExecutionResult] = []
    pr_urls: dict[str, str | None] = {}
    for g in groups:
        result, pr_url = await _ship_group(g, wm, gh, settings)
        results.append(result)
        pr_urls[g.name] = pr_url

    for r in results:
        try:
            report_group(linear, r, pr_urls.get(r.group.name))
        except Exception as e:
            log.error("report_failed", group=r.group.name, err=str(e))

    slack_summary(settings.slack_webhook_url, results, pr_urls)


async def _ship_group(
    g: Group,
    wm: WorkspaceManager,
    gh: GitHubClient,
    settings: Settings,
) -> tuple[ExecutionResult, str | None]:
    """Run one group end-to-end. Never raises — failures land on the result."""
    try:
        ws = wm.create_worktree(g.name)
    except Exception as e:
        log.error("worktree_failed", group=g.name, err=str(e))
        result = ExecutionResult(
            group=g, workspace=None, halted_reason="crash", error=f"worktree: {e}"
        )
        return result, None

    try:
        result = await execute_group(
            g,
            ws,
            settings.model,
            settings.excalibur_token_budget_per_group,
            timeout_seconds=settings.excalibur_executor_timeout_seconds,
        )
        pr_url: str | None = None

        if not wm.has_commits(ws):
            log.warning("no_commits", group=g.name)
            return result, None

        try:
            wm.push(ws)
            pr_url = gh.open_pr(
                head=ws.branch,
                base=settings.excalibur_base_branch,
                title=_pr_title(g),
                body=_pr_body(g, result),
                draft=True,
            )
            log.info("pr_opened", group=g.name, url=pr_url)
        except Exception as e:
            log.error("push_or_pr_failed", group=g.name, err=str(e))
            if result.halted_reason is None:
                result.halted_reason = "crash"
                result.error = f"push/pr: {e}"

        return result, pr_url
    finally:
        try:
            wm.cleanup_worktree(ws)
        except Exception as e:
            log.warning("worktree_cleanup_failed", group=g.name, err=str(e))


def _pr_title(group: Group) -> str:
    n = len(group.issues)
    return f"Shipment: {group.name} ({n} issue{'s' if n != 1 else ''})"


def _pr_body(group: Group, result: ExecutionResult) -> str:
    lines = [
        f"Excalibur shipment of group `{group.name}`.",
        "",
        f"**Rationale:** {group.rationale or 'n/a'}",
        "",
        "## Issues",
        "",
    ]
    for i in group.issues:
        if i.identifier in result.done:
            status = "shipped"
        elif i.identifier in result.blocked:
            status = f"blocked: {result.blocked[i.identifier]}"
        else:
            status = "unknown"
        lines.append(f"- Closes {i.identifier} — {i.title} _({status})_")

    if result.halted_reason:
        lines.append("")
        lines.append(f"**Executor halted early:** `{result.halted_reason}`")
        if result.error:
            lines.append(f"> {result.error}")

    tail = _executor_tail(result)
    if tail:
        lines.append("")
        lines.append("## From the executor")
        lines.append("")
        lines.append("Tail of the executor transcript — read this for caveats the bot wants you to know about (e.g. `npm run typecheck` not being available, BLOCKED reasons, missing context):")
        lines.append("")
        lines.append("```")
        lines.append(tail)
        lines.append("```")

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(f"Generated by excalibur. Review per-issue commits. Tokens used: {result.tokens_used}.")
    return "\n".join(lines)


def _executor_tail(result: ExecutionResult, max_chars: int = 2000) -> str:
    """Last `max_chars` of the executor transcript, prefixed with an ellipsis
    if truncated. Empty string if transcript is empty so the caller can skip
    the section cleanly."""
    t = (result.transcript or "").strip()
    if not t:
        return ""
    if len(t) <= max_chars:
        return t
    return "…" + t[-max_chars:]
