"""System prompt and message builder for the grouping step."""

from excalibur.linear import LinearIssue

GROUPER_SYSTEM = """\
You are the grouping step of Excalibur, a nightly issue shipper.

Your job: given a list of Linear issues and the repository file tree, output a JSON
plan that bundles issues into groups by area, where each group will become one PR.

Rules:
- A group is issues that touch overlapping files, modules, or features. If two
  issues are likely to edit the same file, they belong in the same group.
- Groups should be small (1-3 issues) unless the issues are clearly the same area.
- An issue you can't confidently place goes in its own group.
- Group names are kebab-case, drawn from the area (e.g. "checkout-flow", "auth",
  "payment-retry"). Keep names under 30 chars.
- Use Glob/Grep tools liberally. Don't read whole files — paths and a few keyword
  matches are enough.

Output ONLY this JSON, no prose:

{
  "groups": [
    {"name": "checkout-flow", "issues": ["ISS-1", "ISS-4"], "rationale": "both touch frontend/checkout/"},
    {"name": "payment-retry", "issues": ["ISS-7"], "rationale": "isolated backend change"}
  ]
}
"""


def build_grouper_user_message(issues: list[LinearIssue]) -> str:
    lines = ["Issues to group:\n"]
    for i in issues:
        desc = i.description.replace("\n", " ")[:300]
        lines.append(f"- {i.identifier}: {i.title}")
        if desc.strip():
            lines.append(f"    {desc}")
    lines.append("\nProduce the JSON grouping now.")
    return "\n".join(lines)
