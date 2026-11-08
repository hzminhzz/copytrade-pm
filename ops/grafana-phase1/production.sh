#!/usr/bin/env bash
# Read-only Grafana release lifecycle; never operates on Marimo or financial services.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$ROOT/ops/grafana-phase1/stage.sh"
SOCKET="unix:/run/copytrade-grafana-phase1/serve.sock"
case "${1:-}" in
  start)
    # A live, already healthy release is idempotent.
    if tailscale serve status 2>/dev/null | grep -Fq "$SOCKET" &&
      docker inspect copytrade-grafana-phase1-grafana-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true &&
      docker inspect copytrade-grafana-phase1-projection-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true &&
      docker inspect copytrade-grafana-phase1-ingress-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
      echo "Grafana already healthy; leaving running stack unchanged."
      exit 0
    fi
    # Never remove a different operator's HTTPS 8444 route.
    if tailscale serve status 2>/dev/null | grep -q ':8444' &&
      ! tailscale serve status 2>/dev/null | grep -Fq "$SOCKET"; then
      echo "REFUSE: HTTPS 8444 belongs to another service." >&2
      exit 2
    fi
    # Recovery after reboot: only our known staging route, socket and containers.
    bash "$STAGE" stop
    bash "$STAGE" start
    ;;
  stop)
    bash "$STAGE" stop
    ;;
  status)
    bash "$STAGE" status
    ;;
  *)
    echo "Usage: $0 start|stop|status" >&2
    exit 2
    ;;
esac
