# copytrade-pm repository rules

## Scope and authority
- This repository contains **research-only**, shadow portfolio-manager analysis and simulated prop-firm account risk.
- No real orders, live broker/Propr trading adapter, execution credentials, live PM promotion or trading authorization.
- Never modify or deploy the production `hyperliquid-expert-ensemble` service from here.
- Changes to contractual Propr assumptions require dated official evidence and versioned frozen rule snapshots.

## Data and science
- Historical HyperX fills are retrospective. Never promote event timestamps into first-known follower timestamps.
- Distinguish source-event, local first-known receipt, decision time, and hypothetical fill time.
- Incomplete wallet books, unresolved hedges, stale price series, missing liquidity or unknown account state fail closed.
- Keep original HyperX raw pages, private wallet address maps, provider credentials, market Parquet and original audit artifacts outside Git.
- Preserve verified source SHA-256 lineage, 36-wallet cohort and `pm01_fill_only_replay_v2` consumer interface.
- Scientific qualification is separate from engineering and passing tests. Until prospective follower evidence exists, zero live risk.

## Required reading and durable documentation
- Start at [docs/INDEX.md](docs/INDEX.md), then [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), the stage-specific [data acquisition](docs/DATA-ACQUISITION.md), [runbook](docs/RUNBOOK.md) and [qualification](docs/QUALIFICATION.md) guides. These are current navigation/operation contracts. Old `docs/PM-*.md` are time-scoped scientific or source-era records, not blanket execution authority.
- Before altering CLI args, data contracts, evidence schemas, provider limits, wallet roster or Propr assumptions, inspect actual code/tests and update the relevant canonical guide in the same PR. Keep links and executable command examples verified; include commit/time scope for counts. Historical evidence bytes/SHAs are immutable.
- The current PM-01 cohort is exactly 6+10+20 (36). New wallets require a versioned new cohort and consumer-contract changes, never a silent edit of the frozen manifests. The original PM-01 replay v2 and canonical PM-02 source SHA parity must stay intact.
- The HyperX historical fill-cache code and private alias maps live **outside** this repo. Bounded WS/REST receipts do not imply audited economic follower outcomes. An independent real signed matched-outcome producer is not yet verified/operational; keep actual qualified wallets at zero until measured evidence passes.
- Separate **IMPLEMENTED**, **ENGINEERING VERIFIED**, **SCIENTIFICALLY QUALIFIED**, **AUTHORIZED** and **DEPLOYED**. Do not claim a positive PM-02 proposal is a live position or an independently calculated pass probability.

## Engineering
- Run `uv run --group dev python -m pytest -q tests` and `uv run --group dev ruff check src tests`.
- For the optional native Polars market-data tests, use `uv run --extra market --group dev python -m pytest -q tests`.
- Test fixed-input deterministic hashes and as-of precedence. Never silently change a frozen model or research policy.
- Preserve others' dirty or untracked work, source history and source issue links.
- Source repository integration: https://github.com/hzminhzz/hyperliquid-expert-ensemble/pull/8
