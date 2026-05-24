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
                _surface_block(block, group, result)


# --- Per-block surfacing ------------------------------------------------------
#
# Railway only captures what we explicitly log via structlog — the bundled
# Claude CLI's own stdout (tool calls, transcripts, typecheck output) doesn't
# come through. To make headless runs debuggable post-mortem, every meaningful
# block the SDK yields gets a structured log line here.


_TEXT_LOG_CHARS = 2000
_TOOL_INPUT_CHARS = 400
_TOOL_RESULT_CHARS = 1500


def _surface_block(block, group: Group, result: ExecutionResult) -> None:
    """Translate one SDK message block into a structlog event + state update."""
    # 1. Text block — assistant narrative + markers.
    text = getattr(block, "text", None)
    if text:
        result.transcript += text
        scan_markers(text, result.done, result.blocked)
        log.info(
            "executor_text",
            group=group.name,
            text=_truncate(text, _TEXT_LOG_CHARS),
        )
        return

    # 2. Tool use block — what the executor is about to do.
    tool_name = getattr(block, "name", None)
    if tool_name:
        log.info(
            "executor_tool",
            group=group.name,
            tool=tool_name,
            input=_summarize_tool_input(tool_name, getattr(block, "input", None)),
        )
        return

    # 3. Tool result block — what came back. Often a list of {type,text} dicts.
    content = getattr(block, "content", None)
    if content is not None:
        is_error = bool(getattr(block, "is_error", False))
        summary = _summarize_tool_result(content)
        if is_error:
            log.warning("executor_tool_error", group=group.name, content=summary)
        else:
            log.debug("executor_tool_result", group=group.name, content=summary)


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[:n] + f"…[+{len(s) - n} chars]"


def _summarize_tool_input(tool: str, inp) -> dict | None:
    """Compact view of a tool call's arguments — the bits a human would want
    in the log to recognize what the executor was doing."""
    if not isinstance(inp, dict):
        return None
    if tool == "Bash":
        return {"command": _truncate(str(inp.get("command", "")), _TOOL_INPUT_CHARS)}
    if tool in ("Read", "Edit", "Write"):
        return {
            "file_path": inp.get("file_path") or inp.get("path"),
            **(
                {"old_string": _truncate(str(inp["old_string"]), 200)}
                if "old_string" in inp
                else {}
            ),
        }
    if tool in ("Glob", "Grep"):
        return {"pattern": inp.get("pattern"), "path": inp.get("path")}
    # Unknown tool — just show the keys + truncated values.
    return {k: _truncate(str(v), _TOOL_INPUT_CHARS) for k, v in inp.items()}


def _summarize_tool_result(content) -> str:
    """Tool results are typically a list of {type, text} dicts or a plain string."""
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and "text" in c:
                parts.append(str(c["text"]))
            else:
                parts.append(str(c))
        joined = "\n".join(parts)
    else:
        joined = str(content)
    return _truncate(joined, _TOOL_RESULT_CHARS)
