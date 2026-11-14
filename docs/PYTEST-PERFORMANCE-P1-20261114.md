# Pytest P1 performance and isolation evidence (2026-11-14)

**Scope:** Engineering test acceleration only. No trading, Guardian, deployed services, financial evidence, or source checkpoint policy changes.

## Diagnosis

The highest aggregate core-test cost after P0 was repeated **AST traversal** in capability validation, not copying temporary repositories. In a cProfile run of the operations/group drift test (21 `validate()` calls), `ast.walk` accounted for approximately 22.4s of cumulative instrumented time; `_required_cli_args` traversed whole modules 861 times (16.6s cumulative), and the group-script inspector ran 819 times (8.6s cumulative). Twelve complete test repo clones consumed approximately 0.46s under the same profiler. Profiled times are diagnostic and are not comparable to unprofiled pytest wall-clock.

The CWSA six-portfolio checkpoint test took 10–13s because it **processes genuine historical waves**, including 577 `process_checkpoint` calls and thousands of SQLite journal restores. Its source SQLite snapshot is not the dominant cost. Do not prune the source history or bypass financial replay in pursuit of faster unit tests. Separate-process CLI tests likewise preserve necessary isolation and cold-start behavior.

## Implemented boundaries

- `pm_capabilities._required_cli_args_from_source` caches immutable required-argument tuples keyed by the **complete source string**. The public inspector returns a new list each time.
- `_inspect_group_script_source` caches inspected parser facts by exact source, script name and loop policy. Public callers receive independent copies. Missing files are checked **before** consulting either cache.
- No filename, mtime, global mutable fixture, database, or cross-test source state is treated as immutable.
- `scripts/ci.sh all` runs **core and market in separate pinned environments**, with **two `pytest-xdist` workers per leg** and `--dist=loadfile` to keep same-file fixtures local. The separate required adversarial run remains serial; Ruff, formatting, frontend, build, project binding and SHA-bound receipt gates remain mandatory.
- Pytest-xdist is pinned to `3.8.0` in the dev dependency group and `uv.lock`; no automatic worker count or new runtime dependency was introduced.

## Measured runs

All figures are **pytest-reported wall-clock seconds**, not end-to-end CI. Measurements occurred on the shared six-vCPU VPS under varying system load and filesystem cache states; they are observations, not controlled estimates of isolated speedup.

| Configuration | Core | Market | Results |
| --- | ---: | ---: | --- |
| P0 post-optimization serial reference | 102.89s | 121.90s | Core 2,139 pass / 49 skip; market 2,309 pass / 20 skip |
| P1 serial, standalone | 69.37s | 79.88s | Core 2,140 pass / 49 skip; market 2,310 pass / 20 skip |
| P1 xdist `-n 2 --dist=loadfile`, standalone | 42.60–48.08s | 47.17s | Core 2,140 pass / 46 reported skip; market 2,310 pass / 20 skip |
| P1 xdist, both legs concurrently | 45.85s | 50.98s | Both suites passed; 4 workers total |

One new regression test verifies that cached lists and parser facts cannot leak across callers, edited content invalidates cache entries, and deleted files fail closed. No existing tests or assertions were deleted.

**Skip reporting caveat:** Core xdist accounts for three collection-level module skips differently. A JUnit comparison of serial versus xdist executions showed **identical executable test identities and outcomes**; only three optional module-level collection records (`tests.test_pm_v4_fast_screen`, `tests.test_pm_v4_retrospective_k`, `tests.test_pm_vike_retro_ranking`) were omitted from the xdist report. Market counts match. Required adversarial tests still run separately in the exact-commit CI gate and cannot be counted as passes if skipped.

## Reproduction and interpretation

```bash
UV_PROJECT_ENVIRONMENT=.venv-ci-core uv sync --frozen --group dev --reinstall-package copytrade-pm
UV_PROJECT_ENVIRONMENT=.venv-ci-market uv sync --frozen --group dev --extra market --reinstall-package copytrade-pm
.venv-ci-core/bin/python -m pytest -q tests -n 2 --dist=loadfile --durations=50
.venv-ci-market/bin/python -m pytest -q tests -n 2 --dist=loadfile --durations=50
bash scripts/ci.sh all
```

For a trustworthy comparison, benchmark serial and parallel on the same revision with the same installed optional extras, in a clean test worktree with the frontend already built, and record actual host load. The `all` gate, its receipt and the independent `pm_ci_receipt verify` outcome are the release requirements. A standalone or synthetic timing result is not a CI acceptance receipt.

Further improvements should target measured functional hot paths only when their business/financial behavior can be preserved. Do not collapse genuine SQLite journal replay, remove subprocess proof, introduce global mutable database fixtures, or increase xdist workers without an additional contention and isolation study.
