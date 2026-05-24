# The bundled Claude Code CLI in claude-agent-sdk refuses to run with
# --dangerously-skip-permissions (== our bypassPermissions mode) as root.
# Railway's Nixpacks default user is root, which is why we need a Dockerfile
# with an explicit non-root user.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Tools the executor needs while running headless in a worktree:
#   git           — clone target repos + manage per-group worktrees
#   ca-certificates — outbound https without warnings
#   curl + gnupg  — bootstrap the NodeSource apt repo for nodejs
#   nodejs        — so the executor can run `npm run typecheck`/lint/build
#                   on TS/JS projects it ships changes for. Pinned to v22
#                   LTS to match what Next 15 / React 19 expect.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        git ca-certificates curl gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && node --version && npm --version

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

# Pre-resolve deps at build time so the image is ready to run. ft-hana-cli is
# vendored under /app/vendor (private upstream — see vendor/ft-hana-cli/VENDORED.txt
# for the upstream commit). Installing it into the same .venv means `ft-hana-cli`
# lands on PATH whenever `uv run …` (or anything inside the venv) is the entrypoint.
RUN chmod +x /app/docker/entrypoint.sh \
 && uv sync --frozen \
 && uv pip install /app/vendor/ft-hana-cli

# Entrypoint writes ~/.ft-hana/hana.env from HANA_* env vars so ft-hana-cli finds
# its credentials, then execs the CMD.
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uv", "run", "excalibur", "ship"]
