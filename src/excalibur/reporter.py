"""Post PR URLs back to Linear and optionally Slack."""

from __future__ import annotations

import httpx
import structlog

from excalibur.executor import ExecutionResult
from excalibur.harvester import BLOCKED_LABEL, FAILED_LABEL, SHIPPED_LABEL
from excalibur.linear import LinearClient

log = structlog.get_logger(__name__)


def report_group(
    linear: LinearClient,
    result: ExecutionResult,
    pr_url: str | None,
) -> None:
    shipped_id = linear.ensure_label(SHIPPED_LABEL)
    blocked_id = linear.ensure_label(BLOCKED_LABEL)
    failed_id = linear.ensure_label(FAILED_LABEL)

    by_ident = {i.identifier: i for i in result.group.issues}

    for ident in result.done:
        issue = by_ident.get(ident)
        if not issue:
            continue
        linear.add_label(issue.id, shipped_id)
        if pr_url:
            linear.comment(issue.id, f"Shipped by Excalibur in {pr_url}")

    for ident, reason in result.blocked.items():
        issue = by_ident.get(ident)
        if not issue:
            continue
        linear.add_label(issue.id, blocked_id)
        linear.comment(issue.id, f"Excalibur blocked: {reason}")

    for issue in result.group.issues:
        if issue.identifier in result.done or issue.identifier in result.blocked:
            continue
        # No marker emitted — treat as failure.
        linear.add_label(issue.id, failed_id)
        linear.comment(
            issue.id,
            "Excalibur didn't emit a status marker for this issue. "
            "Either the executor crashed or it skipped. Check the worker logs.",
        )


def slack_summary(
    webhook: str | None,
    results: list[ExecutionResult],
    pr_urls: dict[str, str | None],
) -> None:
    if not webhook:
        return
    total_done = sum(len(r.done) for r in results)
    total_blocked = sum(len(r.blocked) for r in results)
    lines = [
        f"*Excalibur shipment* — {len(results)} groups, "
        f"{total_done} shipped, {total_blocked} blocked"
    ]
    for r in results:
        url = pr_urls.get(r.group.name)
        if url:
            lines.append(f"• <{url}|{r.group.name}>: {len(r.done)} shipped, {len(r.blocked)} blocked")
        else:
            lines.append(f"• {r.group.name}: no PR opened ({len(r.blocked)} blocked)")
    try:
        httpx.post(webhook, json={"text": "\n".join(lines)}, timeout=10.0).raise_for_status()
    except Exception as e:
        log.warning("slack_post_failed", err=str(e))
