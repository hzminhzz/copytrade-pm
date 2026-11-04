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
and checks installed distribution entrypoints. Module-only capabilities are
listed explicitly. All entries have a conservative operation classification:
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
uv run --group dev copytrade-pm paper status
uv run --group dev copytrade-pm status
uv run --group dev copytrade-pm health
```

All responses are JSON. Registry-backed read operations use
`copytrade_read_result_v1` with query status, authority, source generation SHA,
observation clock, data, limitations, error code and false authorization/
qualification indicators. Exit code 2 represents unknown/failed selected
queries; an aggregate status may return successful partial diagnostics while
its individual components remain `UNKNOWN` or `BLOCKED`. `--asof` is
available for wallet and portfolio lookup (UTC offset); do not backdate
later-known aliases or mix portfolio namespaces. Source generations are
separate from Git HEAD and the installed pinned release.

`research list/show` returns `UNKNOWN` until a native source-owned run index
is available, rather than inventing executions by scanning files.
`wallets list` is similarly unavailable, while explicit alias lookup works.
Installed-release status is `UNKNOWN` in the aggregator: the existing
release verifier is a separate operator workflow. Market-provider health is
`UNKNOWN` without independent observations. A saved selection or zero indexed
paper runs never proves paper execution. Those are intentional, explicit
gaps, not fabricated success.

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

`tests/test_pm_agent_native.py` checks static capability routing, ownership,
read-only behavior and fail-closed output semantics. This is a deterministic
resolver/contract benchmark, **not** proof that an arbitrary LLM will select
the proper operation. Real agent tool-use must be evaluated separately,
including redundant searches, invented commands and unsafe mutations.
