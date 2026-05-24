# The bundled Claude Code CLI in claude-agent-sdk refuses to run with
# --dangerously-skip-permissions (== our bypassPermissions mode) as root.
# Railway's Nixpacks default user is root, which is why we need a Dockerfile
# with an explicit non-root user.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# git for cloning target repos + managing per-group worktrees.
# ca-certificates so https calls work without warnings.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Non-root bot identity. /app must be pre-chowned because WORKDIR creates
# the dir as root and --chown on COPY only chowns the *contents*, not the
# directory itself — so `uv sync` would later fail with "Permission denied"
# trying to create /app/.venv.
RUN useradd --create-home --uid 10001 excalibur \
 && mkdir -p /app \
 && chown excalibur:excalibur /app

WORKDIR /app
COPY --chown=excalibur:excalibur . /app

USER excalibur

# Per-group worktrees land under $HOME so the non-root user owns them.
# Railway can override this with the EXCALIBUR_WORKDIR env var if needed.
ENV EXCALIBUR_WORKDIR=/home/excalibur/workspaces

# Pre-resolve deps at build time so the image is ready to run.
RUN uv sync --frozen

CMD ["uv", "run", "excalibur", "ship"]
