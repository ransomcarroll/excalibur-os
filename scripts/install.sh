#!/usr/bin/env bash
# Install Excalibur's local slash command into a project.
# Run from the project root: ~/excalibur/scripts/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXCALIBUR_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ ! -d ".git" ]]; then
  echo "error: run from a project root (no .git here)" >&2
  exit 1
fi

mkdir -p .claude/commands/excalibur
for cmd in create-issue update-issues; do
  cp "$EXCALIBUR_ROOT/commands/${cmd}.md" ".claude/commands/excalibur/${cmd}.md"
  echo "installed: .claude/commands/excalibur/${cmd}.md"
done

echo
echo "Next:"
echo "  1. Ensure Linear MCP is registered as 'linear-server':"
echo "       claude mcp add --transport http --scope user linear-server https://mcp.linear.app/mcp"
echo "  2. Create excalibur.yml in the project root:"
echo "       team: <your team>"
echo "       project: <your project>   # optional"
echo "  3. In Claude Code:"
echo "       /excalibur:create-issue <blurb>"
echo "       /excalibur:update-issues"
