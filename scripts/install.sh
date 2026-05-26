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

if [[ ! -f "CLAUDE.md" ]]; then
  cat > CLAUDE.md <<'EOF'
# Project standards

Add your project's conventions, architecture notes, and constraints here.
Excalibur's nightly executor reads this file when implementing issues, so
anything you'd tell a new contributor belongs here.
EOF
  echo "created: CLAUDE.md (stub — fill it in with your project's standards)"
fi

if [[ ! -f "excalibur.yml" && ! -f "agent-os/linear-config.yml" ]]; then
  echo
  echo "Configuring excalibur.yml..."
  read -rp "  Linear team (name or id): " team
  while [[ -z "${team// }" ]]; do
    read -rp "  team is required — Linear team (name or id): " team
  done
  read -rp "  Linear project (name or id, optional — press enter to skip): " project

  {
    echo "team: $team"
    if [[ -n "${project// }" ]]; then
      echo "project: $project"
    fi
  } > excalibur.yml
  echo "created: excalibur.yml"
fi

echo
echo "Next:"
echo "  1. Ensure Linear MCP is registered as 'linear-server':"
echo "       claude mcp add --transport http --scope user linear-server https://mcp.linear.app/mcp"
echo "  2. In Claude Code:"
echo "       /excalibur:create-issue <blurb>"
echo "       /excalibur:update-issues"
