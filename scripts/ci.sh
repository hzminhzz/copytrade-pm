#!/usr/bin/env bash
# One local CI gate. Full runs publish exact-HEAD verification receipts under Git dir.
# Usage: scripts/ci.sh [core|market|all]
set -euo pipefail

LEG="${1:-all}"
case "$LEG" in core|market|all) ;; *) echo 'Usage: scripts/ci.sh [core|market|all]' >&2; exit 2 ;; esac
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if ! command -v npm >/dev/null 2>&1; then
    echo 'CI_BLOCKED: npm unavailable for ops frontend build' >&2
    exit 2
fi
if ! command -v uv >/dev/null 2>&1; then
    echo 'CI_BLOCKED: uv unavailable' >&2
    exit 2
fi
# SHA-bound evidence requires a committed tree, not an agent's uncommitted code.
# For partial debugging runs an uncommitted tree remains permitted, but unverified.
if [[ "$LEG" == "all" ]] && [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
    echo 'CI_BLOCKED: full SHA-bound receipt requires a clean committed tree' >&2
    exit 2
fi

LOGS="$(mktemp -d)"
trap 'rm -rf "$LOGS"' EXIT
failed=0
if (cd ops/control-center && npm ci --no-audit --no-fund && npm run build &&
    printf 'CI_TYPES_DONE\nCI_FRONTEND_DONE\n') >"$LOGS/frontend.log" 2>&1; then
    :
else
    failed=1
fi

run_leg() {
    local name="$1"
    shift
    (
        export UV_PROJECT_ENVIRONMENT="$ROOT/.venv-ci-$name"
        printf '[%s]\n' "$name"
        uv sync --frozen --group dev "$@"
        uv run --frozen --group dev "$@" python -m pytest -q tests
        echo 'CI_PYTEST_DONE'
        uv run --frozen --group dev "$@" ruff check src tests
        echo 'CI_RUFF_DONE'
        uv run --frozen --group dev "$@" ruff format --check src tests
        echo 'CI_FORMAT_DONE'
        printf 'CI_%s_DONE\n' "$(echo "$name" | tr '[:lower:]' '[:upper:]')"
    ) >"$LOGS/$name.log" 2>&1
}
pids=()
if [[ "$LEG" == "core" || "$LEG" == "all" ]]; then run_leg core & pids+=("$!"); fi
if [[ "$LEG" == "market" || "$LEG" == "all" ]]; then run_leg market --extra market & pids+=("$!"); fi
for pid in "${pids[@]}"; do wait "$pid" || failed=1; done

if [[ "$LEG" == "all" ]]; then
    # The required test roster has one native owner in pm_ci_receipt. A skipped
    # adversarial test is not an acceptance pass even if pytest exits zero.
    if mapfile -t required_tests < <("$ROOT/.venv-ci-core/bin/python" -m copytrade_pm.pm_ci_receipt required-tests); then
        if (
            export UV_PROJECT_ENVIRONMENT="$ROOT/.venv-ci-core"
            uv run --frozen --group dev python -m pytest -q "${required_tests[@]}"
            echo 'CI_ADVERSARIAL_DONE'
        ) >"$LOGS/adversarial.log" 2>&1; then
            :
        else
            failed=1
        fi
    else
        failed=1
    fi
fi

if uv build >"$LOGS/build.log" 2>&1; then
    echo 'CI_BUILD_DONE' >>"$LOGS/build.log"
else
    failed=1
fi

for log in "$LOGS"/*.log; do
    printf '\n=== %s ===\n' "$(basename "$log")"
    cat "$log"
done

if [[ "$LEG" == "all" ]]; then
    GIT_DIR="$(git rev-parse --absolute-git-dir)"
    SHA="$(git rev-parse HEAD)"
    RECEIPT="$GIT_DIR/local-ci/$SHA-$(date -u +%Y%m%dT%H%M%SZ)-$$.json"
    status=PASS
    if [[ "$failed" != 0 ]]; then status=FAIL; fi
    if ! "$ROOT/.venv-ci-core/bin/python" -m copytrade_pm.pm_ci_receipt create \
        --root "$ROOT" --output "$RECEIPT" --status "$status" \
        --core-log "$LOGS/core.log" --market-log "$LOGS/market.log" \
        --adversarial-log "$LOGS/adversarial.log" \
        --frontend-log "$LOGS/frontend.log" --build-log "$LOGS/build.log"; then
        failed=1
    fi
    if [[ "$failed" == 0 ]]; then
        printf '\nCI_PASS leg=all sha=%s receipt=%s\n' "$SHA" "$RECEIPT"
        exit 0
    fi
fi
if [[ "$failed" != 0 ]]; then
    printf '\nCI_FAIL leg=%s\n' "$LEG" >&2
    exit 1
fi
printf '\nCI_PASS leg=%s sha=%s (NO_FULL_RECEIPT)\n' "$LEG" "$(git rev-parse HEAD)"
