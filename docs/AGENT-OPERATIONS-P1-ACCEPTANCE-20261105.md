# Agent-native operational discovery P1 — acceptance and safety (2026-11-05)

Scope: native-first discovery and **read-only** operations in `copytrade-pm`.
This extension is not a live strategy, accounting engine, market data collector,
new source of truth, or paper-trading authorization.

## Verified deployment boundary

The reviewed merged P0 release `8bdaf1e352193554c052167bc8e13e6a66033a95`
was installed via the existing on-demand registry release controller. Its
previous pointer was `29156de99cd2a670f48757fea283bc6a5aa109d5`.
The preactivation SQLite backup passed integrity checks, the pinned installed
release returned `ACTIVE_READ_ONLY_VERIFIED`, source SHA was unchanged, and
tracker/ensemble/Source-ABC PIDs stayed `2050126`, `2050137`, `2180745`
at the cutover. This is a dated checkpoint, not a perpetual liveness claim.

The P1 implementation on `feat/ops-wallet-research-health-20261105` is
a **separate code change** and is not installed by the above P0 cutover unless
a new reviewed SHA is activated and independently verified.

## Authoritative extensions

| Query | Reused owner | Scope | Not evidence of |
| --- | --- | --- | --- |
| `wallets list` | private `wallet_registry_catalog` | as-of alias/cohort/exclusion/monitoring snapshots, redacted, bounded | current equity, retrospective first-known, admission |
| `research list/show --cache-root` | `pm_offline_job` and `ImmutableCache` | SHA-verified canonical `job_report` objects under explicitly selected owner-private root only | all historical studies, positive alpha, financial qualification |
| `health` release | existing `scripts/registry_release.py verify` | pinned, checksum-verified on-demand *registry* release | running trading services |
| `health` protected units | `systemctl --user show` | named protected paper P1/P14/watchdog OS units | journal integrity/heartbeat/financial PASS |
| `health --observer-state-root` | native public-observer heartbeat inspector | locally verified observer receipts | market-provider health, executable liquidity, whole NAV |

No unreviewed CSV, raw fill file, research manifest without a sealed report,
or arbitrary JSON file can masquerade as a completed study. A duplicate
`job_id` must be disambiguated by an immutable cache key.

## Read-only operator examples

```bash
copytrade-pm capabilities validate --json
copytrade-pm wallets list --cohort research-108 --limit 50
copytrade-pm wallets list --query W083
copytrade-pm wallets list --excluded --limit 50
copytrade-pm portfolios show E6
copytrade-pm research list --cache-root /home/quant/.cache/copytrade-polars-bench-20261104-verified-v1/cache
copytrade-pm research show hl94-90d-oracle-screen-20261104 --cache-root /home/quant/.cache/copytrade-polars-bench-20261104-verified-v1/cache
copytrade-pm health
```

From the pinned installed release, use
`uv run --project "$HOME/.local/share/copytrade/registry/release-control/current" --offline --frozen --no-dev copytrade-pm ...`.
Do not invoke these new P1 commands there until the P1 SHA is installed.

## Engineering and scientific evidence separation

The deterministic regression suite covers bounded private inventory and PIT
alias lookup, collision rejection, cache key/payload tamper detection,
duplicate-study ambiguity, read-only SQLite bytes, controlled owner verification,
OS-unit-only degradation and 12 scripted agent discovery tasks. The scripted
cases exercise the real CLI parser and owner lookup, **not a live LLM choosing
tools**. Real LLM behaviour (redundant calls, invented commands, attempted
unsafe mutations, tool availability) remains unmeasured without independently
captured traces.

A GitHub merge or green tests neither deploys a package nor authorizes
paper/demo/live trading. Scientific qualification, account sizing fidelity,
prospective first-known coverage and broker controls remain distinct,
protected acceptance gates.
