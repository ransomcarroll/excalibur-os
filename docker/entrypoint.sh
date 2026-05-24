#!/bin/sh
# Excalibur worker entrypoint.
#
# Runs once per Railway deploy. Materializes the SAP HANA credential file
# from Railway secrets so `ft-hana-cli` (which reads ~/.ft-hana/hana.env
# by default) finds them, then execs the original CMD.
#
# Idempotent: re-running just overwrites the env file with the same values.

set -eu

if [ -n "${HANA_HOST:-}" ] && [ -n "${HANA_USER:-}" ] && [ -n "${HANA_PASSWORD:-}" ]; then
  mkdir -p "$HOME/.ft-hana"
  # printf '%s' on the value side avoids shell expansion, so a password
  # containing $ or backticks is preserved verbatim.
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

exec "$@"
