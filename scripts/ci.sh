#!/usr/bin/env bash
# Local CI: the gates the retired GitHub Actions workflow ran, credential-free.
# Usage: scripts/ci.sh [core|market|all]
set -euo pipefail

LEG="${1:-all}"
case "$LEG" in
    core|market|all) ;;
    *) printf 'Usage: %s [core|market|all]\n' "$0" >&2; exit 2 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
LOGS="$(mktemp -d)"
trap 'rm -rf "$LOGS"' EXIT

# One venv per leg so the legs run concurrently like the retired matrix; uv sync
# is exact, so each venv matches its own dependency set.
run_leg() {
    local name="$1"
    shift
    (
        export UV_PROJECT_ENVIRONMENT="$ROOT/.venv-ci-$name"
        printf '[%s]\n' "$name"
        uv sync --frozen --group dev "$@"
        uv run --frozen --group dev "$@" python -m pytest -q tests
        uv run --frozen --group dev "$@" ruff check src tests
        uv run --frozen --group dev "$@" ruff format --check src tests
    ) >"$LOGS/$name.log" 2>&1
}

pids=()
if [[ "$LEG" == "core" || "$LEG" == "all" ]]; then run_leg core & pids+=("$!"); fi
if [[ "$LEG" == "market" || "$LEG" == "all" ]]; then run_leg market --extra market & pids+=("$!"); fi

failed=0
for pid in "${pids[@]}"; do wait "$pid" || failed=1; done
for log in "$LOGS"/*.log; do cat "$log"; done
if [[ "$failed" != 0 ]]; then
    printf '\nCI_FAIL leg=%s\n' "$LEG" >&2
    exit 1
fi

uv build
printf '\nCI_PASS leg=%s sha=%s\n' "$LEG" "$(git rev-parse HEAD)"
