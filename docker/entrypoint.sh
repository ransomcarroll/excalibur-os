#!/bin/sh
# Excalibur worker entrypoint.
#
# Runs once per Railway deploy. Does three things in order, then execs CMD:
#
#   1. Materializes ~/.ft-hana/hana.env from Railway HANA_* secrets so the
#      vendored ft-hana-cli reads them via its default credential lookup.
#   2. Starts the prebaked ephemeral Postgres cluster at /home/excalibur/pgdata
#      (data is reset per container — every shipment gets an empty `ftpm` DB
#      that the executor brings to current schema via `npx prisma migrate
#      deploy` if it needs to validate Prisma changes).
#   3. Exports DATABASE_URL so target-project npm scripts and the
#      excalibur-write-env-local helper see the same local Postgres.
#
# All three steps are best-effort: if a step's prerequisites aren't met
# (e.g. HANA secrets unset, or pg_ctl not on PATH), we log a warning and
# continue so non-dependent shipments still work.

set -eu

# ---- 1. HANA credentials -------------------------------------------------
if [ -n "${HANA_HOST:-}" ] && [ -n "${HANA_USER:-}" ] && [ -n "${HANA_PASSWORD:-}" ]; then
  mkdir -p "$HOME/.ft-hana"
  {
    printf 'HANA_HOST=%s\n'     "$HANA_HOST"
    printf 'HANA_PORT=%s\n'     "${HANA_PORT:-30015}"
    printf 'HANA_USER=%s\n'     "$HANA_USER"
    printf 'HANA_PASSWORD=%s\n' "$HANA_PASSWORD"
    printf 'HANA_SCHEMA=%s\n'   "${HANA_SCHEMA:-FTPROD2}"
  } > "$HOME/.ft-hana/hana.env"
  chmod 600 "$HOME/.ft-hana/hana.env"
else
  echo "[entrypoint] HANA_* env vars not all set; skipping ~/.ft-hana/hana.env. ft-hana-cli will not work this run." >&2
fi

# ---- 2. Ephemeral Postgres ----------------------------------------------
PGDATA=/home/excalibur/pgdata
if [ -d "$PGDATA" ] && command -v pg_ctl >/dev/null 2>&1; then
  if pg_ctl -D "$PGDATA" -l /tmp/pg.log -w -t 30 start; then
    # ---- 3. DATABASE_URL ------------------------------------------------
    : "${DATABASE_URL:=postgresql://postgres:postgres@localhost:5432/ftpm}"
    export DATABASE_URL
    echo "[entrypoint] postgres up; DATABASE_URL=$DATABASE_URL" >&2
  else
    echo "[entrypoint] WARNING: pg_ctl start failed (see /tmp/pg.log); db scripts will not work this run." >&2
  fi
else
  echo "[entrypoint] postgres not installed or pgdata missing; db scripts will not work this run." >&2
fi

exec "$@"
