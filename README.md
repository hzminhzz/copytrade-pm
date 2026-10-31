# copytrade-pm

**Black-box wallet portfolio-manager research and prop-firm challenge preparation.** PM-01 and PM-02 are extracted from `hyperliquid-expert-ensemble` as a separate, auditable Python package. PM-03 is tracked but not implemented here.

This repository is **shadow-only**: no trading credentials, no broker integration, no live orders or live risk promotion.

## System roles

- **PM-01:** reconstruct observable whole-wallet portfolios from sealed historical fills and independent first-known observations; replay hypothetical followers with exact Hyperliquid instrument identity, latency, funding, fees, market-only comparators, missing-data guards and explicit coverage status.
- **PM-02:** immutable manager evidence cards, independence diagnostics, conservative hypothetical risk-budget proposals, historical/prospective separation and lifecycle research decisions.
- **PM-36 research diagnostic:** synchronized, SHA-verified historical 1-minute-open equity marks for any *fully replayable* wallet subset. Explicit minimum common-history gate and no causal follower/pass-probability claims. See [research report](docs/PM-36-synchronized-challenge.md).
- **PM-03 (planned):** one deterministic Propr account simulator and account-level risk authority. Original specification: [PM-03](https://github.com/hzminhzz/hyperliquid-expert-ensemble/issues/5); successor [issue #2](https://github.com/hzminhzz/copytrade-pm/issues/2).

## Quickstart

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --group dev
uv run --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
uv run --group dev python -m copytrade_pm.pm_fill_replay --help
uv run --group dev python -m copytrade_pm.pm_manager --help
uv run --group dev python -m copytrade_pm.pm_handoff --help
uv run --group dev python -m copytrade_pm.pm_synchronized_challenge --help
```

Native Hyperliquid 1-minute Parquet and vendor-data research uses the optional Polars/Pandas extra:

```bash
uv run --extra market --group dev python -m pytest -q tests
```

CLI entry points: `copytrade-pm-replay`, `copytrade-pm-rank`, `copytrade-pm-scope`, `copytrade-pm-market-audit`, `copytrade-pm-handoff`, `copytrade-pm-research`, and `copytrade-pm-synchronized`.

The source research artifacts and private data remain under their existing VPS owner-private paths. Supply paths explicitly to the CLI, never commit data or credentials. Imported historical documentation under `docs/PM-*.md` records source-era results; current commands use `copytrade_pm` rather than `ensemble`.

## Scientific status

- 36 historical source wallets (6 original + 10 Wave 1 + 20 Wave 2).
- Four shortlisted wallets passed a **90% Propr-native 1m market-day data gate**, not a profitable follower or full-book execution gate.
- **Zero scientifically qualified manager seats**. PM-02's real-data research recommendation remains five EMPTY seats and zero actionable R.
- Historical HyperX fill times are not first-known follower signals. Source account completeness, execution capacity, Propr market identity and contractual compliance remain unresolved.
- Historical PM-36 synchronized study: four completed 0.1%-gross wallet replays, 1,007/997/952 common minute-open marks at 5/15/60m, **0 qualified 30-day multi-wallet combinations**. Synthetic sampled challenge results cannot establish pass probabilities.
- Synthetic PM-03 scenarios, when built, must never be advertised as real challenge pass probabilities.

## Evidence and Git history

The imported code retains a **12-commit filtered PM-only Git ancestry**, merged with the destination's initialization history. See [migration provenance](docs/PROVENANCE.md) and [original PM integration PR #8](https://github.com/hzminhzz/hyperliquid-expert-ensemble/pull/8). Git was filtered by *paths*; original commit IDs changed, and the mapping is documented. No original runtime, Telegram, deployment files, untracked research or secret data was imported.

The legacy ensemble advisory service remains owned and deployed independently by `hyperliquid-expert-ensemble`.
