# Agent-native capability discovery and read-only operations

## Architecture decision (2026-11-04)

**Option B selected:** one repo-wide discovery directory plus a small read-only
operator facade. Extending `wallet_registry.py` (Option A) would make a
private identity index responsible for Git, runtime, PM-03 finance, market
health and research. That would violate existing ownership.

The facade delegates to existing registry interfaces. PM-03 remains the sole
financial authority; paper status is an independent journal/worker concern.
No new database, order route, source collector, financial calculator, web server
or scheduler is introduced. This directory is descriptive, **not authorization**.

## Native-first workflow

Before adding any Python module, CLI or data-access path, agents **must**:

1. Run `copytrade-pm capabilities list` and `copytrade-pm capabilities validate`.
2. Resolve a domain capability with `copytrade-pm capabilities show <id>`.
3. Read the owner's module, contract, tests and linked documentation.
4. Reuse the existing public interface or extend its owner.
5. Create a new responsibility only if no suitable owner exists; document why.
6. Validate the catalog, run tests, inspect the final diff and preserve protected
   boundaries. Never implement alternative PM-03 finance, wallet ownership,
   independent scientific qualification or live order authorization.

The directory automatically discovers project scripts from `pyproject.toml`
and checks installed distribution entrypoints. Mandatory arguments for flat
argparse CLIs are derived from their source AST; subcommand-dependent or
module-only requirements remain null rather than falsely advertised as empty.
Reviewed registry operations include explicit required inputs. Module-only
capabilities are listed explicitly. All entries have a conservative operation classification:
`READ_ONLY`, `LOCAL_MUTATION`, `PROTECTED_MUTATION`, or `BROKER_OR_TRADING`.
Unknown entrypoints become `UNCLASSIFIED` and fail validation. A parent CLI
classification is **not** permission to execute arbitrary subcommands; use the
reviewed subcommand record. The existing registry's `--apply` variants are
protected and never exposed by the new read-only facade.

## Commands

```bash
uv run --group dev copytrade-pm --help
uv run --group dev copytrade-pm capabilities list
uv run --group dev copytrade-pm capabilities show portfolio.current
uv run --group dev copytrade-pm capabilities show research.offline
uv run --group dev copytrade-pm capabilities validate
uv run --group dev copytrade-pm portfolios list
uv run --group dev copytrade-pm portfolios current
uv run --group dev copytrade-pm portfolios show E6
uv run --group dev copytrade-pm portfolios show q3/B
uv run --group dev copytrade-pm wallets show W083
uv run --group dev copytrade-pm wallets list --cohort research-108 --limit 50
uv run --group dev copytrade-pm wallets list --query W083
uv run --group dev copytrade-pm wallets list --excluded --limit 50
uv run --group dev copytrade-pm research list --cache-root /home/quant/.cache/copytrade-polars-bench-20261104-verified-v1/cache
uv run --group dev copytrade-pm research show hl94-90d-oracle-screen-20261104 --cache-root /home/quant/.cache/copytrade-polars-bench-20261104-verified-v1/cache
uv run --group dev copytrade-pm paper status
uv run --group dev copytrade-pm status
uv run --group dev copytrade-pm health
```

All responses are JSON. Registry-backed read operations use
`copytrade_read_result_v1` with query status, authority, source generation SHA,
observation clock, data, limitations, error code and false authorization/
qualification indicators. The source observation timestamp is separate from
the query observation timestamp. Registry index freshness reflects stored
generation age, not live source parity; the aggregate health view runs the
native `doctor` to verify current counts and source SHAs separately.
Exit code 2 represents unknown/failed selected queries; an aggregate status may return successful partial diagnostics while
its individual components remain `UNKNOWN` or `BLOCKED`. `--asof` is
available for wallet and portfolio lookup (UTC offset); do not backdate
later-known aliases or mix portfolio namespaces. Source generations are
separate from Git HEAD and the installed pinned release.

**Wallet inventory (5 November extension):** `wallets list` delegates to the
native private registry catalog. It paginates at 200 rows, supports `--query`
(alias substring only), `--cohort`, `--excluded` / `--no-excluded`,
`--subscribed` / `--no-subscribed` and `--asof`. Addresses and exclusion reasons
are redacted. `registry_wallet_id` is *SQLite-generation-local*, never a
stable cross-import identity. An alias collision does not become a candidate
identity. Monitoring comes from the current snapshot, not a reconstructed
historical subscription series; missing fields stay `null` / `UNKNOWN`.

**Executed research report discovery:** `research list/show` accepts an
explicit owner-private `--cache-root` and verifies the canonical
`pm_offline_job` `job_report` manifest, dependency key and payload SHA before
listing it. Only that root and that report type are indexed; arbitrary JSON
files, vendor fill pages and unpublished experiments are **not** completed
research. Multiple reports with the same job ID require `--cache-key` to show
one uniquely. All reports retain `financial_certified_real=false`,
`scientifically_qualified=false` and `trading_authorized=false` unless a
separate protected future workflow establishes authority. No cache directory
is created by discovery. Missing explicit root returns `UNKNOWN`.

**Health adapters:** aggregate `health` runs the original pinned-release
`verify` method and shows *which registry release* was verified, independently
of the worktree Git revision. Known protected P1/P14/watchdog systemd units
are observed without starting or stopping them. An active OS unit is not
independent journal, heartbeat or paper-economic qualification. Optional
`--observer-state-root PRIVATE_DIR` verifies the native public observer source
and quote receipts via the existing observer watchdog; provider freshness and
executable market capacity remain `UNKNOWN`. Without observer evidence, market
status stays `UNKNOWN`. A saved selection or zero indexed paper runs never
proves paper execution.

Native SQLite readers use `mode=ro` and do not change registry tables or
data bytes, though SQLite may create `-wal` or `-shm` coordination files; do
not use unsafe immutable snapshots against a potentially active WAL writer.

For verified pinned-release diagnostics, continue to use
`uv run --group dev python scripts/registry_release.py verify`. For a
specific paper account journal, use
`copytrade-pm-paper-status --db <private-path> --run-id <run-id>`.
For sealed Polars studies use the canonical `pm_offline_job` interface; it
may write immutable research cache evidence and is not a read-only command.

## Operational semantics and recovery

A single missing authority must not block unrelated Git or registry status.
Never present a registry selection as `PAPER_RUNNING`, positive PM-03 economics,
scientific qualification or trading authorization. Follow the registry-first
workflow, actual service/heartbeat checks, immutable decision seals and
protected runbook. Capability metadata never relaxes those rules.

Use `docs/BLOCKER-RECOVERY.md` if a lookup fails and preserve the precise
reason (stale evidence, private-source unavailable, schema mismatch or worker
not independently verified). For engineering changes that add a CLI, update
this directory and tests in the same change; CI must fail on missing entrypoint
classification.

## Benchmarks

`tests/test_pm_agent_native.py` and `tests/test_pm_operational_discovery.py`
check capability routing, registry/PIT parity, immutable cache-integrity
failure handling, read-only data behavior, and independent systemd/release
contract failures. The 12 scripted agent-task cases execute the real CLI
resolver, but do **not** test live LLM tool selection. Real agent trace-based
evaluation still needs independent observed tool-call logs (redundant lookups,
invented operations, incomplete answers and unsafe attempted mutations).
