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
"$ENV_DIR/bin/ruff" check src tests
"$ENV_DIR/bin/ruff" format --check src tests
printf 'CI_FOCUSED_PASS (NO_FULL_RECEIPT; NOT_ACCEPTANCE)\n'
