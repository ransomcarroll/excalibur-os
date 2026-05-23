#!/usr/bin/env bash
# Manually trigger one shipment, e.g. for testing on Railway via Run command.
set -euo pipefail
exec uv run excalibur ship "$@"
