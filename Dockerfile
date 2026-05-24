# The bundled Claude Code CLI in claude-agent-sdk refuses to run with
# --dangerously-skip-permissions (== our bypassPermissions mode) as root.
# Railway's Nixpacks default user is root, which is why we need a Dockerfile
# with an explicit non-root user.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Tools the executor needs while running headless in a worktree:
#   git              — clone target repos + manage per-group worktrees
#   ca-certificates  — outbound https without warnings
#   curl + gnupg     — bootstrap NodeSource + PostgreSQL apt repos
#   nodejs           — so the executor can run npm run typecheck/lint/build
#                       on TS/JS projects. Pinned to v22 LTS (Next 15 / React 19).
#   postgresql-18    — local DB so Prisma scripts (db:push, db:migrate, seeds)
#                       work like they do on a Frama-Tech dev machine. Cluster
#                       is initialized at build, started by entrypoint, and is
#                       ephemeral per container (every shipment gets a fresh
#                       empty `ftpm` DB; executor runs prisma migrate deploy
#                       to bring it current as part of its work).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates curl gnupg \
 # NodeSource apt repo (Node 22)
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 # PostgreSQL apt repo (PG 18, matches the user's local dev setup)
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends nodejs postgresql-18 \
 && rm -rf /var/lib/apt/lists/* \
 && node --version && npm --version && /usr/lib/postgresql/18/bin/postgres --version

# Postgres tools on PATH so initdb / pg_ctl / psql / createdb work without
# absolute paths (and so the executor's Bash inherits the same).
ENV PATH=/usr/lib/postgresql/18/bin:${PATH}

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

# Pre-resolve Python deps at build time so the image is ready to run.
# ft-hana-cli is vendored under /app/vendor (private upstream — see
# vendor/ft-hana-cli/VENDORED.txt for the upstream commit). Installing it
# into the same .venv means `ft-hana-cli` lands on PATH whenever `uv run …`
# (or anything inside the venv) is the entrypoint.
#
# excalibur-write-env-local is a shell helper the executor calls from a
# worktree to materialize .env.local from the worker's process env so npm
# scripts using dotenv-cli (db:push, hana:test, the seed/migrate scripts)
# work without committing secrets. Symlinked into .venv/bin so it shares
# PATH with the rest of our tools.
RUN chmod +x /app/docker/entrypoint.sh /app/docker/excalibur-write-env-local \
 && uv sync --frozen \
 && uv pip install /app/vendor/ft-hana-cli \
 && ln -sf /app/docker/excalibur-write-env-local /app/.venv/bin/excalibur-write-env-local

# Pre-init the Postgres cluster owned by the excalibur user. We create the
# empty `ftpm` database here so the executor doesn't pay createdb cost per
# shipment; bringing it to current schema is the executor's job (via
# `npx prisma migrate deploy` from the target project's worktree).
RUN initdb \
        -D /home/excalibur/pgdata \
        -U postgres \
        --auth-local=trust \
        --auth-host=trust \
        --no-instructions \
 && pg_ctl -D /home/excalibur/pgdata -l /tmp/pg-init.log -w start \
 && psql -h localhost -U postgres -d postgres -c "ALTER ROLE postgres WITH PASSWORD 'postgres';" \
 && createdb -h localhost -U postgres ftpm \
 && pg_ctl -D /home/excalibur/pgdata -m fast stop

# Entrypoint writes ~/.ft-hana/hana.env, starts the prebaked Postgres, sets
# DATABASE_URL, then execs the CMD.
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uv", "run", "excalibur", "ship"]
