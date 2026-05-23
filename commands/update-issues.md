# Update Issues (Excalibur)

Walk Linear issues that aren't ready for the worker yet and interview them into shape. This is the only Excalibur slash command that runs a real conversation — everything else is one-shot.

## Usage

```
/excalibur:update-issues                  # walk needs-triage issues in the configured team
/excalibur:update-issues --all            # also include unlabeled candidates
/excalibur:update-issues --limit 5        # cap how many issues to walk this session
/excalibur:update-issues --only ISS-123   # triage one specific issue
```

## Arguments

- `--all` — include issues that have none of the Excalibur labels at all (still skip `human-only`, `agent-ready`, `excalibur-shipped/blocked/failed`).
- `--limit N` — process at most N issues this session. Default: 10.
- `--only <id1,id2,...>` — restrict to specific issue identifiers (e.g. `ISS-123`). Overrides other filters.

## Process

### 1. Load Linear config

Same as `/excalibur:create-issue`: read `excalibur.yml` for `team` (required) and `project` (optional).

### 2. Fetch candidates

Use `mcp__linear-server__list_issues` with:

- `team`: from config
- `state`: not `Completed`, not `Canceled`
- One query for issues labeled `needs-triage`.
- If `--all`, a second query for issues with NONE of: `agent-ready`, `human-only`, `needs-triage`, `excalibur-shipped`, `excalibur-blocked`, `excalibur-failed`.
- If `--only`, ignore both queries and fetch the named identifiers directly.

Combine results, dedupe by `id`, order: `needs-triage` first (oldest updatedAt → newest), then unlabeled (oldest → newest). Truncate to `--limit`.

If the resulting list is empty, print `nothing to triage.` and stop.

### 3. Announce the batch

One line:

```
Triaging N issue(s): ISS-101, ISS-104, ISS-110, …
```

Do not preview each issue's body up front — handle them one at a time so the user isn't reading ahead.

### 4. Per-issue loop

For each issue in order:

#### 4a. Show context

Print:

```
─── ISS-123: <title> ───
<full description, indented 2 spaces>
labels: needs-triage, …
url: <issue url>
```

#### 4b. Light orientation

Spend ~15 seconds, no more than a handful of tool calls:

- Glob for files implied by the title.
- Grep for any symbol/feature name in the description.
- **Do not Read whole files.** You're sharpening scope, not implementing.

#### 4c. Decide the question(s) to ask

You may ask up to 3 questions via `AskUserQuestion`. Prefer one bundle of focused questions over a back-and-forth. Common questions worth asking:

- Which file area / surface should this touch? (when 2+ candidates exist)
- What's the success criterion? (when the blurb says "improve" / "fix" without a target)
- Is this scoped to one ticket, or should it split? (when 2+ behaviors are mixed)
- Is this still relevant? (for stale issues — offer "close it" as an option)

DO NOT ask:
- Anything you can derive from the description or a `Read` of the obvious file.
- Anything about priority, type, or assignee.
- "Should I proceed?" — just proceed.

If the issue is already crisp on inspection (no orientation surprises, end-state is clear), skip the interview and go straight to step 4d with the resolution `promote` and a one-line rewrite explanation.

#### 4d. Resolve

Pick exactly one resolution based on the answers:

| Resolution | What it means | Linear action |
|---|---|---|
| `promote` | Now bounded and unambiguous. Worker can ship it. | Rewrite description; replace labels with `[agent-ready]`. |
| `human-only` | Needs a human (design call, cross-team decision, customer convo). | Replace labels with `[human-only]`. Add a one-paragraph comment summarizing why. |
| `defer` | Still un-shippable but not for human-only reasons (waiting on something, low priority). | Keep `needs-triage`. Add a comment explaining what we're waiting on. |
| `split` | This is 2+ tickets. | Create child issues via `mcp__linear-server__create_issue` (one per chunk, label `agent-ready` or `needs-triage` per the `/excalibur:create-issue` rubric). Mark the original `human-only` with a comment pointing at the children. |
| `close` | Stale or no longer relevant. | Update issue state to `Canceled` via `mcp__linear-server__update_issue`. Add a one-line comment. |

For `promote`, the rewrite should follow `/excalibur:create-issue` step 5 structure (What / Why / Pointers). Keep the original phrasing where it was already sharp; tighten only what the interview clarified.

#### 4e. Apply

Call `mcp__linear-server__update_issue` with the new title (if changed), description, and labels. For `split`, also call `create_issue` per child. For `close`, set state via `update_issue`.

#### 4f. Report one line per issue

```
ISS-123: promote → agent-ready
ISS-104: human-only (cross-team API change)
ISS-110: split → ISS-201, ISS-202
ISS-115: close (stale, superseded by ISS-198)
ISS-118: defer (waiting on infra ticket)
```

### 5. Final summary

After the loop, one block:

```
Triage session complete.
  promoted:    3   (ISS-101, ISS-104, ISS-110)
  human-only:  1   (ISS-115)
  split:       1   (ISS-118 → ISS-201, ISS-202)
  closed:      0
  deferred:    2   (ISS-122, ISS-130)
```

## Notes

- This command never edits code or opens PRs. It only talks to Linear.
- Labels created on demand: if `needs-triage`, `agent-ready`, or `human-only` don't exist in the team, create them via `mcp__linear-server__create_label`.
- Standards live in `CLAUDE.md`. This command does not load them; the worker does that itself when it picks up an `agent-ready` issue.
- If the user wants to triage in bulk without the interview, point them at the Linear UI; this command is opinionated about going one at a time.
