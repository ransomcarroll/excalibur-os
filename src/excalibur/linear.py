"""Linear GraphQL client. Just the queries the shipper needs."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

from excalibur.http_utils import request_with_retry

log = structlog.get_logger(__name__)


@dataclass
class LinearIssue:
    id: str
    identifier: str  # e.g. "ISS-123"
    title: str
    description: str
    url: str
    git_branch_name: str
    label_ids: list[str]


class LinearClient:
    def __init__(
        self,
        api_key: str,
        team_id: str,
        *,
        client: httpx.Client | None = None,
    ):
        self._client = client or httpx.Client(
            base_url="https://api.linear.app",
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            timeout=30.0,
        )
        self.team_id = team_id

    def _gql(self, query: str, variables: dict | None = None) -> dict:
        r = request_with_retry(
            self._client,
            "POST",
            "/graphql",
            json={"query": query, "variables": variables or {}},
            label="linear",
        )
        if r.status_code >= 400:
            # Surface the response body so caller can see the actual GraphQL error,
            # not just "400 Bad Request".
            try:
                body_preview = r.text[:1000]
            except Exception:
                body_preview = "<unreadable>"
            raise RuntimeError(
                f"Linear HTTP {r.status_code} for query "
                f"{query.strip().splitlines()[0][:80]!r}: {body_preview}"
            )
        body = r.json()
        if "errors" in body:
            raise RuntimeError(f"Linear GraphQL error: {body['errors']}")
        return body["data"]

    def shippable_issues(
        self, agent_ready_label_id: str, shipped_label_id: str
    ) -> list[LinearIssue]:
        """Issues labeled agent-ready, not shipped, no open PR linked."""
        q = """
        query Shippable($teamId: ID!, $readyId: ID!, $shippedId: ID!) {
          issues(
            filter: {
              team: { id: { eq: $teamId } }
              labels: { id: { eq: $readyId } }
              and: [{ labels: { id: { neq: $shippedId } } }]
              state: { type: { nin: ["completed", "canceled"] } }
            }
            first: 50
          ) {
            nodes {
              id
              identifier
              title
              description
              url
              branchName
              labels { nodes { id } }
            }
          }
        }
        """
        data = self._gql(
            q,
            {
                "teamId": self.team_id,
                "readyId": agent_ready_label_id,
                "shippedId": shipped_label_id,
            },
        )
        return [
            LinearIssue(
                id=n["id"],
                identifier=n["identifier"],
                title=n["title"],
                description=n.get("description") or "",
                url=n["url"],
                git_branch_name=n["branchName"],
                label_ids=[lab["id"] for lab in n["labels"]["nodes"]],
            )
            for n in data["issues"]["nodes"]
        ]

    def find_label_id(self, name: str) -> str | None:
        q = """
        query Labels($teamId: String!) {
          team(id: $teamId) { labels(first: 250) { nodes { id name } } }
        }
        """
        data = self._gql(q, {"teamId": self.team_id})
        for lab in data["team"]["labels"]["nodes"]:
            if lab["name"].lower() == name.lower():
                return lab["id"]
        return None

    def ensure_label(self, name: str, color: str = "#888888") -> str:
        existing = self.find_label_id(name)
        if existing:
            return existing
        q = """
        mutation Create($teamId: String!, $name: String!, $color: String!) {
          issueLabelCreate(input: { teamId: $teamId, name: $name, color: $color }) {
            issueLabel { id }
          }
        }
        """
        data = self._gql(q, {"teamId": self.team_id, "name": name, "color": color})
        return data["issueLabelCreate"]["issueLabel"]["id"]

    def add_label(self, issue_id: str, label_id: str) -> bool:
        """Add `label_id` to `issue_id` if not already present.

        Returns True if a write happened, False if the label was already on the issue.
        Linear's issueUpdate replaces the label set, so we union before writing.
        """
        cur = self._gql(
            "query Q($id: String!) { issue(id: $id) { labels { nodes { id } } } }",
            {"id": issue_id},
        )
        existing = {lab["id"] for lab in cur["issue"]["labels"]["nodes"]}
        if label_id in existing:
            return False
        ids = list(existing | {label_id})
        q = """
        mutation Add($issueId: String!, $labelIds: [String!]!) {
          issueUpdate(id: $issueId, input: { labelIds: $labelIds }) { success }
        }
        """
        self._gql(q, {"issueId": issue_id, "labelIds": ids})
        return True

    def comment(self, issue_id: str, body: str) -> None:
        q = """
        mutation Comment($issueId: String!, $body: String!) {
          commentCreate(input: { issueId: $issueId, body: $body }) { success }
        }
        """
        self._gql(q, {"issueId": issue_id, "body": body})
