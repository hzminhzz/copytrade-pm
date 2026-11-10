#!/usr/bin/env bash
# Read-only daily Hyperliquid wallet-health capture; no private order transport.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$ROOT/.venv/bin/python"
DATA="$HOME/.local/share/copytrade/health-research"
REDACTED="$HOME/.local/share/copytrade-grafana-health"
if [[ ! -x "$PY" ]]; then
    echo "FAIL: pinned release Python unavailable" >&2
    exit 2
fi
if [[ ! -d "$DATA" || ! -d "$REDACTED" ]]; then
    echo "FAIL: preconfigured private/redacted output directories required" >&2
    exit 2
fi
if [[ "$(stat -c %a "$DATA")" != 700 ]]; then
    echo "FAIL: raw capture root must be private mode 0700" >&2
    exit 2
fi
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
GEN="g${STAMP}-$(openssl rand -hex 6)"
exec "$PY" -m copytrade_pm.wallet_health_official \
    --db "$HOME/.local/share/copytrade/registry/wallet_registry.sqlite" \
    --generation "$DATA/$GEN" \
    --max-wallets 512 --deep-wallets 12 --weight-per-minute 600 \
    --publish-dir "$REDACTED"
