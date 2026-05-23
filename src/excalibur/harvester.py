"""Pull shippable issues from Linear."""

import structlog

from excalibur.linear import LinearClient, LinearIssue

log = structlog.get_logger(__name__)

AGENT_READY_LABEL = "agent-ready"
SHIPPED_LABEL = "excalibur-shipped"
BLOCKED_LABEL = "excalibur-blocked"
FAILED_LABEL = "excalibur-failed"


def harvest(linear: LinearClient, max_issues: int) -> list[LinearIssue]:
    ready_id = linear.ensure_label(AGENT_READY_LABEL, color="#26B5CE")
    shipped_id = linear.ensure_label(SHIPPED_LABEL, color="#5E6AD2")
    linear.ensure_label(BLOCKED_LABEL, color="#F2C94C")
    linear.ensure_label(FAILED_LABEL, color="#EB5757")

    issues = linear.shippable_issues(
        agent_ready_label_id=ready_id, shipped_label_id=shipped_id
    )
    log.info("harvested", count=len(issues))
    return issues[:max_issues]
