#!/usr/bin/env bash
# Fast, explicit Python development feedback. NEVER publishes a full CI receipt.
# Usage: scripts/ci_focused.sh tests/test_module.py [tests/test_other.py::test_case ...]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ "$#" -eq 0 ]]; then
    echo "Usage: scripts/ci_focused.sh tests/test_module.py [tests/test_other.py::test_case ...]" >&2
    exit 2
fi
for target in "$@"; do
    file="${target%%::*}"
    if [[ "$file" != tests/test_*.py && "$file" != tests/*/test_*.py ]] ||
       [[ ! -f "$file" || -L "$file" ]]; then
        echo "CI_FOCUSED_REJECTED_TARGET: $target" >&2
        exit 2
    fi
done
if ! command -v uv >/dev/null 2>&1; then
    echo "CI_BLOCKED: uv unavailable" >&2
    exit 2
fi

# A separate environment prevents focused checks from racing with full CI.
ENV_DIR="$ROOT/.venv-ci-focused"
UV_PROJECT_ENVIRONMENT="$ENV_DIR" uv sync --frozen --group dev --reinstall-package copytrade-pm
"$ENV_DIR/bin/python" -c '
import copytrade_pm
from pathlib import Path
import sys
if not Path(copytrade_pm.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve() / "src"):
    raise SystemExit("CI_FOCUSED_WRONG_WORKTREE_INSTALL")
' "$ROOT"
"$ENV_DIR/bin/python" -m pytest -q "$@"
"$ENV_DIR/bin/ruff" check src tests scripts
"$ENV_DIR/bin/ruff" format --check src tests
added_py=()
mapfile -t added_py < <(
    {
        if git -C "$ROOT" rev-parse --verify origin/main >/dev/null 2>&1; then
            git -C "$ROOT" diff --name-only --diff-filter=A origin/main...HEAD -- 'src/*.py' 'tests/*.py'
        fi
        git -C "$ROOT" diff --cached --name-only --diff-filter=A -- 'src/*.py' 'tests/*.py'
        git -C "$ROOT" ls-files --others --exclude-standard -- 'src/*.py' 'tests/*.py'
    } | awk 'NF' | sort -u
)
if ((${#added_py[@]} > 0)); then
    pyright_bin="$(command -v pyright || true)"
    [[ -n "$pyright_bin" ]] || pyright_bin="/home/quant/.hermes/node/bin/pyright"
    [[ -x "$pyright_bin" ]] || { echo 'pyright not executable for newly added Python files' >&2; exit 1; }
    env_python="$ENV_DIR/bin/python"
    [[ "$ENV_DIR" = /* ]] || env_python="$PWD/$ENV_DIR/bin/python"
    (cd "$ROOT" && "$pyright_bin" --pythonversion 3.14 --pythonpath "$env_python" "${added_py[@]}")
fi
printf 'CI_FOCUSED_PASS (NO_FULL_RECEIPT; NOT_ACCEPTANCE)\n'
