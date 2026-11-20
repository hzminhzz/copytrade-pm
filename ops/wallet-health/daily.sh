#!/usr/bin/env bash
# Read-only daily Hyperliquid wallet-health capture; no private order transport.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLI="$ROOT/.venv/bin/copytrade-pm"
DATA="$HOME/.local/share/copytrade/health-research"
if [[ ! -x "$CLI" ]]; then
    echo "FAIL: pinned release copytrade-pm unavailable" >&2
    exit 2
fi
if [[ ! -d "$DATA" ]]; then
    echo "FAIL: preconfigured private output directory required" >&2
    exit 2
fi
if [[ "$(stat -c %a "$DATA")" != 700 ]]; then
    echo "FAIL: raw capture root must be private mode 0700" >&2
    exit 2
fi
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
GEN="g${STAMP}-$(openssl rand -hex 6)"
exec "$CLI" facts capture-health --apply \
    --roster-db "$HOME/.local/share/copytrade/roster.sqlite" \
    --store "$HOME/.local/share/copytrade/facts" \
    --generation "$DATA/$GEN" \
    --max-wallets 512 --deep-wallets 12 --weight-per-minute 600
