"""Cluster issues by area using a single Claude Agent SDK call."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from excalibur.linear import LinearIssue
from excalibur.prompts.grouper import GROUPER_SYSTEM, build_grouper_user_message
from excalibur.text_utils import extract_json, slugify

log = structlog.get_logger(__name__)


@dataclass
class Group:
    name: str
    issues: list[LinearIssue]
    rationale: str = ""


async def group_issues(
    issues: list[LinearIssue],
    repo_root: Path,
    model: str,
) -> list[Group]:
    """Returns one Group per cluster. Issues that don't cluster get their own group."""
    if not issues:
        return []
    if len(issues) == 1:
        i = issues[0]
        return [Group(name=slugify(i.title), issues=[i], rationale="only issue")]

    options = ClaudeAgentOptions(
        system_prompt=GROUPER_SYSTEM,
        model=model,
        cwd=str(repo_root),
        allowed_tools=["Glob", "Grep", "Read"],
        permission_mode="bypassPermissions",  # read-only tools allowlisted, can't escape
        max_turns=15,
    )

    user_msg = build_grouper_user_message(issues)
    raw = await _run_and_collect(options, user_msg)

    plan = extract_json(raw)
    by_id = {i.identifier: i for i in issues}
    groups: list[Group] = []
    seen: set[str] = set()
    for g in plan.get("groups", []):
        members = [by_id[x] for x in g.get("issues", []) if x in by_id]
        if not members:
            continue
        groups.append(Group(name=g["name"], issues=members, rationale=g.get("rationale", "")))
        seen.update(m.identifier for m in members)

    # Fallback: any issue not placed gets its own group.
    for i in issues:
        if i.identifier not in seen:
            groups.append(Group(name=slugify(i.title), issues=[i], rationale="ungrouped"))

    log.info("grouped", group_count=len(groups), issue_count=len(issues))
    return groups


async def _run_and_collect(options: ClaudeAgentOptions, prompt: str) -> str:
    chunks: list[str] = []
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for msg in client.receive_response():
            for block in getattr(msg, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    chunks.append(text)
    return "".join(chunks)
