# Excalibur

A nightly shipper for Linear issues. File tickets during the day with vanilla
Claude Code; a Railway worker bundles `agent-ready` issues by area at 6pm,
implements them with headless Claude Code, and opens one PR per group.

## How it works

```
[ your laptop ]                              [ Railway worker, nightly cron ]
/excalibur:create-issue "fix retry"   ─►     harvester:  Linear → agent-ready
   ↓ Linear MCP                                  ↓
   files ISS-123 with                        grouper:    Claude clusters by area
   agent-ready OR needs-triage                   ↓
                                             executor:   per group, fresh worktree,
/excalibur:update-issues             ─►                  headless Claude Code,
   walks needs-triage, interviews,                       commit per issue, push
   flips to agent-ready                          ↓
                                             reporter:   PR opened, Linear comment per issue
```

The local side is two slash commands. The remote side does the work.

### Labels Excalibur manages

| Label | Set by | Meaning |
|---|---|---|
| `agent-ready` | `/excalibur:create-issue` (sharp blurbs), `/excalibur:update-issues` (after triage) | Worker picks this up nightly. |
| `needs-triage` | `/excalibur:create-issue` when scope is uncertain | Sits until you run `/excalibur:update-issues`. |
| `human-only` | Either command, for issues that need a person | Worker skips entirely. |
| `excalibur-shipped` | Worker | PR opened for this issue. |
| `excalibur-blocked` | Worker | Executor emitted `BLOCKED[…]` — needs a human. |
| `excalibur-failed` | Worker | No marker emitted; executor crashed or skipped. |

## Local install

From inside a project (any git repo where you use Claude Code), run the
install script. Next time you start a Claude Code session in that directory,
`/excalibur:create-issue` and `/excalibur:update-issues` will be available.

```bash
git clone git@github.com:ransomcarroll/excalibur-os.git ~/excalibur-os
cd /path/to/your/project
~/excalibur-os/scripts/install.sh
```

The script creates:

- `.claude/commands/excalibur/{create-issue,update-issues}.md` — the slash
  commands themselves.
- `CLAUDE.md` — only if one doesn't already exist. Excalibur reads it for
  project standards but doesn't manage its contents; fill it in yourself.
- `excalibur.yml` — only if neither it nor `agent-os/linear-config.yml`
  already exists. The script prompts you for your Linear team (required)
  and project (optional) and writes them here.

## Usage

```
/excalibur:create-issue Add retry to eBiz payment timeouts
/excalibur:create-issue --quick frontend table is sluggish on >1k rows
/excalibur:update-issues                  # walk needs-triage issues
/excalibur:update-issues --all --limit 5  # also walk unlabeled, cap at 5
/excalibur:update-issues --only ISS-123   # triage one specific issue
```

`create-issue` does ~30s of file orientation and writes a short description
with pointers. `--quick` skips even that — title and description verbatim. In
either mode it labels the issue:

- `agent-ready` when the blurb is concrete and bounded;
- `needs-triage` when scope is uncertain (long, vague, multi-area, or design
  decisions left to make);
- `human-only` when the blurb itself contains open questions.

`update-issues` is the one Excalibur command that actually interviews. It
walks `needs-triage` issues, asks up to a few focused questions per ticket,
then either promotes them, marks `human-only`, splits them, defers them, or
closes them. Run it before the cron fires.

## Remote (worker) install

Deploy to Railway:

```bash
cd ~/excalibur
railway up
```

Set env vars in Railway:

| Var | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude Agent SDK |
| `GITHUB_TOKEN` | Fine-grained PAT, scoped to FTCPM-DEV/* with repo/PR write |
| `LINEAR_API_KEY` | Linear personal API key (Settings → API) |
| `LINEAR_TEAM_ID` | Which team to harvest from |
| `GITHUB_REPO` | `FTCPM-DEV/your-project` |
| `EXCALIBUR_BASE_BRANCH` | Default `dev` |
| `EXCALIBUR_MAX_ISSUES_PER_SHIPMENT` | Default `8` |
| `EXCALIBUR_TOKEN_BUDGET_PER_GROUP` | Default `2000000` |
| `SLACK_WEBHOOK_URL` | Optional, posts shipment summary |

The cron schedule lives in `railway.toml`.

## Manual run

```bash
uv run excalibur ship                       # full shipment now
uv run excalibur ship --dry-run             # harvest + group, don't execute
uv run excalibur ship --only ISS-42,ISS-50  # ship just these
```

## What it doesn't do

- **No interview at filing time.** `create-issue` decides a label and moves
  on. Interviews happen in `update-issues`, deliberately.
- **No plan mode anywhere.** Both slash commands run in normal mode.
- **No standards injection ceremony.** Standards ride along via `CLAUDE.md`.
- **No automatic merging.** PRs are draft until you mark ready and merge.
- **No spec folders.** If the executor needs to leave notes, it leaves them
  in the PR body.

## Status

Worker is wired against the Claude Agent SDK; the prompts will need real
tuning against your repo before the first live shipment is trustworthy.
Run `uv run excalibur ship --dry-run` first to inspect grouping output
before turning on the cron.
