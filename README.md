# copytrade-pm

**Black-box wallet portfolio-manager research and prop-firm challenge preparation.** PM-01 and PM-02 are extracted from `hyperliquid-expert-ensemble` as a separate, auditable Python package. PM-03 is tracked but not implemented here.

This repository is **shadow-only**: no trading credentials, no broker integration, no live orders or live risk promotion.

## System roles

- **PM-01:** reconstruct observable whole-wallet portfolios from sealed historical fills and independent first-known observations; replay hypothetical followers with exact Hyperliquid instrument identity, latency, funding, fees, market-only comparators, missing-data guards and explicit coverage status.
- **PM-02:** immutable manager evidence cards, independence diagnostics, conservative hypothetical risk-budget proposals, historical/prospective separation and lifecycle research decisions.
- **PM-36 independent Q3:** all 36 source wallets' actual July–September (92-calendar-day) vendor-reported realized fill cashflows, plus separate independently anchored 5/15/60-minute hypothetical closed-episode replay. These are not full wallet returns or a challenge-pass probability. See [quarter research](docs/PM-36-2026-Q3-independent.md).
- **PM-36 three-pod experiment:** a research-only shared $100k virtual account with W028/W042/W030, capped signed net positions, immediate-vs-5m execution policies, modeled partial exits and sampled daily/static risk floors. See [three-pod replay](docs/PM-36-three-pod-2026Q3.md).
- **PM-36 synchronized diagnostic:** SHA-verified 1-minute-open equity marks for the short common historical replay window only. Retained as a narrower diagnostic, **not** the three-month wallet ranking. See [prior research](docs/PM-36-synchronized-challenge.md).
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
uv run --group dev python -m copytrade_pm.pm_quarter_fill_audit --help
uv run --group dev python -m copytrade_pm.pm_quarter_episode_replay --help
uv run --group dev python -m copytrade_pm.pm_three_pod_batch_replay --help
```

Native Hyperliquid 1-minute Parquet and vendor-data research uses the optional Polars/Pandas extra:

```bash
uv run --extra market --group dev python -m pytest -q tests
```

CLI entry points: `copytrade-pm-replay`, `copytrade-pm-rank`, `copytrade-pm-scope`, `copytrade-pm-market-audit`, `copytrade-pm-handoff`, `copytrade-pm-research`, `copytrade-pm-synchronized`, `copytrade-pm-quarter-fills`, `copytrade-pm-quarter-episodes`, and `copytrade-pm-three-pod`.

The source research artifacts and private data remain under their existing VPS owner-private paths. Supply paths explicitly to the CLI, never commit data or credentials. Imported historical documentation under `docs/PM-*.md` records source-era results; current commands use `copytrade_pm` rather than `ensemble`.

## Scientific status

- 36 historical source wallets (6 original + 10 Wave 1 + 20 Wave 2).
- Four shortlisted wallets passed a **90% Propr-native 1m market-day data gate**, not a profitable follower or full-book execution gate.
- **Zero scientifically qualified manager seats**. PM-02's real-data research recommendation remains five EMPTY seats and zero actionable R.
- Historical HyperX fill times are not first-known follower signals. Source account completeness, execution capacity, Propr market identity and contractual compliance remain unresolved.
- Full Q3 2026 source-fill accounting: **46,314 verified historical fill records across all 36**, with vendor-reported realized after-fee PnL but **unknown full account equity, unrealized PnL and funding**. Partial historical-only episode replay: 1,754 fully observed source episodes, 1,034 / 995 / 964 independently modeled at 5m / 15m / 60m; 795 paired across all three. **0 qualified portfolios or copyable live followers**.
- Historical PM-36 synchronized study: four completed 0.1%-gross October wallet replays, 1,007/997/952 common minute-open marks at 5/15/60m; it is **not** the three-month assessment. Synthetic sampled challenge results cannot establish pass probabilities.
- Three-pod July–September historical oracle: W028/W042/W030, **204** selected flat-to-flat native-crypto episodes, 12 shared-account policy/sizing paths plus 24 cost-stress paths. Five-minute batching reduced modeled orders but did not outperform immediate execution at tested sizes. Missing whole-wallet exposures and first-known observations prevent scientific qualification; modeled gross can exceed research ceilings when liquidity blocks immediate reductions.
- Synthetic PM-03 scenarios, when built, must never be advertised as real challenge pass probabilities.

## Evidence and Git history

The imported code retains a **12-commit filtered PM-only Git ancestry**, merged with the destination's initialization history. See [migration provenance](docs/PROVENANCE.md) and [original PM integration PR #8](https://github.com/hzminhzz/hyperliquid-expert-ensemble/pull/8). Git was filtered by *paths*; original commit IDs changed, and the mapping is documented. No original runtime, Telegram, deployment files, untracked research or secret data was imported.

The legacy ensemble advisory service remains owned and deployed independently by `hyperliquid-expert-ensemble`.
