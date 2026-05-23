"""Run headless Claude Code in a worktree to implement a group of issues."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import structlog
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from excalibur.grouper import Group
from excalibur.prompts.executor import EXECUTOR_SYSTEM, build_executor_user_message
from excalibur.text_utils import scan_markers
from excalibur.worktree import Workspace

log = structlog.get_logger(__name__)


@dataclass
class ExecutionResult:
    group: Group
    workspace: Workspace | None
    done: list[str] = field(default_factory=list)
    blocked: dict[str, str] = field(default_factory=dict)
    transcript: str = ""
    tokens_used: int = 0
    halted_reason: str | None = None  # "token_budget" | "timeout" | "crash" | None
    error: str | None = None  # populated when halted_reason == "crash"

    @property
    def has_any_commits(self) -> bool:
        return bool(self.done)


async def execute_group(
    group: Group,
    workspace: Workspace,
    model: str,
    token_budget: int,
    *,
    timeout_seconds: float | None = None,
) -> ExecutionResult:
    options = ClaudeAgentOptions(
        system_prompt=EXECUTOR_SYSTEM,
        model=model,
        cwd=str(workspace.worktree_path),
        allowed_tools=["Glob", "Grep", "Read", "Edit", "Write", "Bash"],
        permission_mode="bypassPermissions",
        max_turns=200,
    )
    prompt = build_executor_user_message(group.name, group.issues)
    result = ExecutionResult(group=group, workspace=workspace)

    try:
        if timeout_seconds and timeout_seconds > 0:
            await asyncio.wait_for(
                _drive_client(options, prompt, group, token_budget, result),
                timeout=timeout_seconds,
            )
        else:
            await _drive_client(options, prompt, group, token_budget, result)
    except asyncio.TimeoutError:
        result.halted_reason = "timeout"
        result.transcript += (
            f"\n[excalibur] executor timed out after {timeout_seconds}s — halting\n"
        )
        log.warning("executor_timeout", group=group.name, timeout=timeout_seconds)
    except Exception as e:  # pragma: no cover - depends on SDK transport
        result.halted_reason = "crash"
        result.error = str(e)
        result.transcript += f"\n[excalibur] executor crashed: {e}\n"
        log.error("executor_crashed", group=group.name, err=str(e))

    return result


async def _drive_client(
    options: ClaudeAgentOptions,
    prompt: str,
    group: Group,
    token_budget: int,
    result: ExecutionResult,
) -> None:
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for msg in client.receive_response():
            usage = getattr(msg, "usage", None)
            if usage:
                result.tokens_used += getattr(usage, "input_tokens", 0) + getattr(
                    usage, "output_tokens", 0
                )
                if result.tokens_used > token_budget:
                    result.halted_reason = "token_budget"
                    result.transcript += (
                        "\n[excalibur] token budget exceeded — halting\n"
                    )
                    log.warning(
                        "token_budget_exceeded",
                        group=group.name,
                        tokens=result.tokens_used,
                        budget=token_budget,
                    )
                    break

            for block in getattr(msg, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    result.transcript += text
                    scan_markers(text, result.done, result.blocked)
