"""Minimal GitHub API wrapper for PR creation."""

from __future__ import annotations

import httpx
import structlog

from excalibur.http_utils import request_with_retry

log = structlog.get_logger(__name__)


class GitHubClient:
    def __init__(self, token: str, repo: str, *, client: httpx.Client | None = None):
        self.repo = repo  # "owner/name"
        self._client = client or httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    def _owner(self) -> str:
        return self.repo.split("/", 1)[0]

    def get_pr_for_branch(self, head: str) -> str | None:
        """Return the html_url of an open PR for `head`, or None."""
        r = request_with_retry(
            self._client,
            "GET",
            f"/repos/{self.repo}/pulls",
            params={"head": f"{self._owner()}:{head}", "state": "open"},
            label="github",
        )
        r.raise_for_status()
        prs = r.json()
        if not prs:
            return None
        return prs[0]["html_url"]

    def open_pr(
        self,
        head: str,
        base: str,
        title: str,
        body: str,
        draft: bool = True,
    ) -> str:
        """Open a draft PR. If one already exists for `head`, return its URL.

        Returns the PR URL. Raises RuntimeError for non-recoverable 422s
        (e.g. "no commits between …") so the scheduler can mark the group failed.
        """
        r = request_with_retry(
            self._client,
            "POST",
            f"/repos/{self.repo}/pulls",
            json={"head": head, "base": base, "title": title, "body": body, "draft": draft},
            label="github",
        )
        if r.status_code == 422:
            payload = r.json()
            if _is_already_exists(payload):
                url = self.get_pr_for_branch(head)
                if url:
                    log.info("pr_already_open", head=head, url=url)
                    return url
            raise RuntimeError(f"PR open rejected: {payload}")
        r.raise_for_status()
        return r.json()["html_url"]


def _is_already_exists(payload: dict) -> bool:
    msg = (payload.get("message") or "").lower()
    if "already exists" in msg or "a pull request already exists" in msg:
        return True
    for err in payload.get("errors") or []:
        text = " ".join(str(v) for v in err.values()).lower()
        if "already exists" in text:
            return True
    return False
