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

## Portfolio-contract EV evaluation (2026-11-05)

Use `copytrade-pm capabilities show research.contract_selector`, then
`copytrade-pm contracts compare --portfolio gemini.phase4/E6 --portfolio
gemini.phase4/E2`. Without complete synchronized net follower PnL, it
returns BLOCKED. With full owner-private portfolio tapes, it compares the
versioned A/B/C rules, evaluation/funded-stage risk scaling, realistic payout
path and chance-of-ruin across sampled 7-day joint PnL blocks. It never
promotes a simulated positive EV to qualification or broker authority.
[Full tool contract](CONTRACT-PORTFOLIO-EV-TOOL-20261105.md).

## Actuarial research extension (2026-11-05)

The reviewed read-only capability `research.actuary` owns a synthetic
challenge-to-funded-payout scenario CLI: `copytrade-pm-actuary --help`.
It never touches wallet identity, PM-03 accounting, protected paper workers,
broker credentials or live orders. It is not independently qualified follower
economics. Assumptions and 100,000-path examples are documented in
[contract actuarial research](CONTRACT-ACTUARY-RESEARCH-20261105.md).

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
of the worktree Git revision. Known protected P1/P14/watchdog units are checked
in both the **system** and **user** systemd managers without starting or
stopping them. Any active unit remains `DEGRADED`; missing system-manager
evidence returns `UNKNOWN`, never `NOT_RUNNING` based only on the user manager.
A unit's activity is not independent journal, heartbeat or paper-economic
qualification. The [guarded protected-operations runbook](FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md)
separates staged root unit candidates from actually installed protected workers.
Optional `--observer-state-root PRIVATE_DIR` verifies the native public observer source
and quote receipts via the existing observer watchdog; provider freshness and
executable market capacity remain `UNKNOWN`. Without observer evidence, market
status stays `UNKNOWN`. The public observer's independent watcher verifies a
single consistent read-only SQLite tape snapshot. A new heartbeat seals source,
quote and collateral chain-prefix heads; when additional fully verified
append-only receipts arrive during a subsequent epoch, status is still
`DEGRADED_OBSERVER_ONLY` with `UNATTESTED_TAPE_ADVANCE_AFTER_HEARTBEAT`, not
`PAPER_RUNNING`. A different, truncated or rewritten prefix stays `UNKNOWN`.
During idle pauses the observer may emit explicitly marked liveness-only
heartbeats without new source data or changed provider polling rates; any
stale source/quote receipts remain stale. See the
[public observer deployment guide](FORWARD-PAPER-PUBLIC-OBSERVER-SERVICE-20261105.md).
A saved selection or zero indexed paper runs never proves paper execution.

Native SQLite readers use `mode=ro` and do not change registry tables or
data bytes, though SQLite may create `-wal` or `-shm` coordination files; do
not use unsafe immutable snapshots against a potentially active WAL writer.

For verified pinned-release diagnostics, continue to use
`uv run --group dev python scripts/registry_release.py verify`. For a
specific paper account journal, use
`copytrade-pm-paper-status --db <private-path> --run-id <run-id>`.
For sealed Polars studies use the canonical `pm_offline_job` interface; it
may write immutable research cache evidence and is not a read-only command.

## Public observer unit (separate from financial paper)

`copytrade-pm capabilities show paper.public_unit` resolves the new
`copytrade-pm-public-observer-unit` command. Its default is a read-only
reviewed unit proposal; `--apply` writes one new quant-owned public-observer
user unit only after independently verifying the installed pinned release,
private journal path, source locator availability and optional public clients.
The parent CLI is conservatively classified `PROTECTED_MUTATION` because it
contains `--apply`. It never starts or stops units and cannot enable P1/P14
financial execution. See [the public observer deployment guide](FORWARD-PAPER-PUBLIC-OBSERVER-SERVICE-20261105.md).

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
resolver, but do **not** test live LLM tool selection.
The [P2 trace scorer](AGENT-TRACE-EVAL-20261105.md) now accepts
externally signed, independently captured host tool-event traces for 13
fixed tasks. It measures correct native-first routing, redundant and
off-target lookups, invented commands, unsafe attempts and structured final
status consistency. Synthetic and manually transcribed traces always remain
`UNVERIFIED_TOOL_TRACE`. In the absence of host-exported evidence the
empirical agent-effectiveness gate is `BLOCKED_NO_INDEPENDENT_HOST_TRACE`;
CLI parity tests alone do not demonstrate actual LLM tool selection.
