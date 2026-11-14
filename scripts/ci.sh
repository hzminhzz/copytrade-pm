#!/usr/bin/env bash
# One local CI gate. Full runs publish exact-HEAD verification receipts under Git dir.
# Usage: scripts/ci.sh [core|market|all]
set -euo pipefail

LEG="${1:-all}"
case "$LEG" in core|market|all) ;; *) echo 'Usage: scripts/ci.sh [core|market|all]' >&2; exit 2 ;; esac
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Ensure inherited git hook environment variables cannot redirect git calls
# inside CI checks or isolated temporary repositories during pytest runs.
while IFS= read -r git_var; do
    [[ -n "$git_var" ]] && unset "$git_var"
done < <(git rev-parse --local-env-vars 2>/dev/null || true)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY \
    GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX \
    GIT_IMPLICIT_WORK_TREE GIT_GRAFT_FILE GIT_SHALLOW_FILE \
    GIT_NO_REPLACE_OBJECTS GIT_REPLACE_REF_BASE GIT_CONFIG \
    GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT GIT_NAMESPACE || true
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
# Frontend installation/build is independent of the Python suites. Stage its
# output outside ops/control-center/dist so Vite never deletes dist/ while
# pytest HTTP tests are reading it concurrently.
(cd ops/control-center && npm ci --no-audit --no-fund && npm run typecheck &&
    npx vite build --outDir "$LOGS/frontend-dist" &&
    printf 'CI_TYPES_DONE\nCI_FRONTEND_DONE\n') >"$LOGS/frontend.log" 2>&1 &
frontend_pid=$!
if [[ ! -f ops/control-center/dist/index.html ]]; then
    wait "$frontend_pid" || failed=1
    if [[ -d "$LOGS/frontend-dist" ]]; then
        rm -rf ops/control-center/dist
        mv "$LOGS/frontend-dist" ops/control-center/dist
    fi
fi

run_leg() {
    local name="$1"
    shift
    (
        local_env="$ROOT/.venv-ci-$name"
        printf '[%s]\n' "$name"
        # Worktrees can inherit an editable install pointing at an older release.
        # Force only this small package to rebind; leave dependency caches warm.
        UV_PROJECT_ENVIRONMENT="$local_env" uv sync --frozen --group dev --reinstall-package copytrade-pm "$@"
        "$ROOT/.venv-ci-$name/bin/python" -c '
import copytrade_pm
from pathlib import Path
import sys
expected = Path(sys.argv[1]).resolve() / "src"
actual = Path(copytrade_pm.__file__).resolve()
if not actual.is_relative_to(expected):
    raise SystemExit(f"CI_WRONG_PROJECT_INSTALL: {actual} expected under {expected}")
' "$ROOT"
        echo 'CI_PROJECT_BINDING_DONE'
        # Keep same-file mutable fixtures on one worker and cap each leg at two
        # processes: core and market already run concurrently (four workers total).
        # Adversarial receipt requirements continue to run separately, serially.
        "$local_env/bin/python" -m pytest -q tests -n 2 --dist=loadfile
        echo 'CI_PYTEST_DONE'
        "$local_env/bin/ruff" check src tests
        echo 'CI_RUFF_DONE'
        "$local_env/bin/ruff" format --check src tests
        echo 'CI_FORMAT_DONE'
        "$local_env/bin/python" -c '
import copytrade_pm
from pathlib import Path
import sys
if not Path(copytrade_pm.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve() / "src"):
    raise SystemExit("CI_WRONG_PROJECT_INSTALL_AFTER_TESTS")
' "$ROOT"
        echo 'CI_PROJECT_BINDING_AFTER_TESTS_DONE'
        printf 'CI_%s_DONE\n' "$(echo "$name" | tr '[:lower:]' '[:upper:]')"
    ) >"$LOGS/$name.log" 2>&1
}
pids=()
if [[ "$LEG" == "core" || "$LEG" == "all" ]]; then run_leg core & pids+=("$!"); fi
if [[ "$LEG" == "market" || "$LEG" == "all" ]]; then run_leg market --extra market & pids+=("$!"); fi
for pid in "${pids[@]}"; do wait "$pid" || failed=1; done
wait "$frontend_pid" || failed=1
if [[ -d "$LOGS/frontend-dist" ]]; then
    rm -rf ops/control-center/dist
    mv "$LOGS/frontend-dist" ops/control-center/dist
fi

if [[ "$LEG" == "all" ]]; then
    # The required test roster has one native owner in pm_ci_receipt. A skipped
    # adversarial test is not an acceptance pass even if pytest exits zero.
    if mapfile -t required_tests < <("$ROOT/.venv-ci-core/bin/python" -m copytrade_pm.pm_ci_receipt required-tests); then
        if (
            "$ROOT/.venv-ci-core/bin/python" -m pytest -q "${required_tests[@]}"
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
    CI_GIT_DIR="$(git rev-parse --absolute-git-dir)"
    SHA="$(git rev-parse HEAD)"
    RECEIPT="$CI_GIT_DIR/local-ci/$SHA-$(date -u +%Y%m%dT%H%M%SZ)-$$.json"
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
