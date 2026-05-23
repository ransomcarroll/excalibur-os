"""Pure text helpers used by grouper/executor. No SDK deps so they're trivially testable."""

import json
import re


def extract_json(raw: str) -> dict:
    """Pull a JSON object out of a model response, tolerating code fences and prose."""
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON found in: {raw[:500]}")
    return json.loads(m.group(0))


def slugify(text: str, max_len: int = 30) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len] or "shipment"


DONE_RE = re.compile(r"DONE\[(?P<id>[A-Z][A-Z0-9_-]+-\d+)\]")
BLOCKED_RE = re.compile(
    r"BLOCKED\[(?P<id>[A-Z][A-Z0-9_-]+-\d+)\]\s*:\s*(?P<reason>[^\n]+)"
)


def scan_markers(text: str, done: list[str], blocked: dict[str, str]) -> None:
    """Update done/blocked in place from a chunk of executor stdout."""
    for m in DONE_RE.finditer(text):
        ident = m.group("id")
        if ident not in done:
            done.append(ident)
    for m in BLOCKED_RE.finditer(text):
        blocked[m.group("id")] = m.group("reason").strip()
