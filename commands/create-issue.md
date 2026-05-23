# Create Issue (Excalibur)

File a Linear issue with minimal ceremony. No plan mode. No preflight. No interview unless a question genuinely must be asked.

## Usage

```
/excalibur:create-issue <blurb>
/excalibur:create-issue --quick <blurb>
```

## Arguments

- Everything after the command is the blurb.
- If `--quick` is the first token, strip it and skip the orientation step.

## Process

### 1. Parse

Read the args. If the first token is `--quick`, set `quick = true` and the blurb is the rest. Otherwise `quick = false` and the blurb is everything.

### 2. Load Linear config

Read `excalibur.yml` (preferred) or `agent-os/linear-config.yml` (fallback) from the project root. Expected shape:

```yaml
team: <team name or id>
project: <project name or id>     # optional
```

If neither file exists, ask the user once for the team. Don't ask again next time — save it to `excalibur.yml`.

### 3. Quick mode

If `quick`, skip to step 6 with:

- **Title:** the blurb, lightly polished to imperative form, < 80 chars. Don't add detail the user didn't write.
- **Description:** the blurb verbatim.

### 4. Default mode — light orientation

Spend at most ~30 seconds and a handful of tool calls:

- One or two Glob calls to find candidate files.
- One or two Grep calls if the blurb mentions a specific symbol or feature name.
- **Do not Read whole files.** Paths are enough.

### 5. Draft

Write a Linear issue with these sections, omitting any that would be empty:

```
## What
<1-2 sentences from the blurb>

## Why
<the implicit motivation, if obvious — otherwise skip>

## Pointers
- `path/to/file.ts` — what to look at
- `path/to/other.py` — what to look at
```

Title: imperative, < 80 chars.

### 6. Decide labels

Pick exactly one label. Be honest about uncertainty — `needs-triage` is the safe default when the blurb won't survive a headless run. Quick-mode blurbs default to `needs-triage` unless they pass the `agent-ready` bar below; the user opted out of orientation, not out of triage.

- **`agent-ready`** — only when ALL hold:
  - The blurb names a concrete, bounded change (one file area, one behavior).
  - You can describe the expected end-state in one sentence.
  - There are no design or product decisions left to make.
  - No scope-smell phrases: "improve", "clean up", "rethink", "figure out", "look into", "we should probably", "maybe", "or something", "etc".

- **`needs-triage`** — when the blurb is real work but you can't confidently say it ships unaided. Apply when ANY hold:
  - Blurb is long (3+ sentences) or spans more than one feature area.
  - End-state is ambiguous (e.g. "make X better" with no target).
  - Blurb implies a design decision (which surface? which library? which schema shape?).
  - Multiple modules referenced that don't obviously belong together.
  - Acceptance criteria are missing and not derivable from context.
  - You'd want to ask 2+ questions before starting.

- **`human-only`** — when the blurb contains explicit open questions the human flagged (`?`, "TBD", "need to decide", "design needed", "thoughts?", "want your take"). These sit for the human; the worker won't touch them.

Don't classify priority, type, or source label — those are out of scope here. Use Linear's UI for them.

### 7. Do not interview here

This command stays fast. Do not call `AskUserQuestion` to disambiguate scope — if the blurb isn't sharp enough for `agent-ready`, label it `needs-triage` and move on. `/excalibur:update-issues` is where interviews happen.

The single exception: if the blurb has a typo or contradiction that makes it literally unparseable (you cannot tell what the user is asking for at all), ask one yes/no clarifying question via `AskUserQuestion`. Otherwise: decide and file.

### 8. File the issue

Call `mcp__linear-server__create_issue` with:

- `title`: from step 3 or 5
- `team`: from config
- `project`: from config (if present)
- `description`: the drafted markdown
- `labels`: `[<the one label from step 6>]`
- `assignee`: `"me"`
- `state`: `"Touched"` if it exists, else leave default

### 9. Report

One line, matching the label you applied:

```
Filed <ID>: <title> — agent-ready  →  <issue URL>
Filed <ID>: <title> — needs-triage  →  <issue URL>
Filed <ID>: <title> — human-only  →  <issue URL>
```

If you labeled `needs-triage`, append a second line naming the top reason in 6 words or fewer (e.g. `triage: spans frontend + backend`). No further commentary.

## Notes

- Standards belong in `CLAUDE.md` (project memory). This command does not load standards explicitly.
- This command does NOT create branches, draft PRs, or run preflight checks. Excalibur's worker does that nightly.
- If the user wants to talk through a tricky issue, they should use vanilla Claude Code without this command.
