# copytrade-pm

**Black-box wallet portfolio-manager research and prop-firm challenge preparation.** PM-01 and PM-02 are extracted from `hyperliquid-expert-ensemble` as a separate, auditable Python package. PM-03 implements a **shadow-only, deterministic consolidated account and risk supervisor**, developed in [Issue #2](https://github.com/hzminhzz/copytrade-pm/issues/2) and documented in [PM-03 architecture and contract register](docs/PM-03-shadow-account.md). This is NOT a real Propr account, an approved automation system, or scientifically qualified wallet selection.

This repository is **shadow-only**: no trading credentials, no broker integration, no live orders or live risk promotion.

## System roles

- **PM-01:** reconstruct observable whole-wallet portfolios from sealed historical fills and independent first-known observations; replay hypothetical followers with exact Hyperliquid instrument identity, latency, funding, fees, market-only comparators, missing-data guards and explicit coverage status.
- **PM-02:** immutable manager evidence cards, independence diagnostics, conservative hypothetical risk-budget proposals, historical/prospective separation and lifecycle research decisions.
- **PM-03 (engineering research):** one Decimal-based deterministic shadow account simulator, exact instrument/PM target netting and virtual internal crosses, modeled capacity/fees/partial fills, dated public Propr rulebook with contract fail-closed defaults, central graded risk authority, immutable replay-first event memory, and three-policy identical-path synthetic stress comparisons. Never assume research fills are Propr fills. [PM-03 design and reproducibility](docs/PM-03-shadow-account.md).

## Quickstart

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --group dev
uv run --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
uv run --group dev python -m copytrade_pm.pm_fill_replay --help
uv run --group dev python -m copytrade_pm.pm_manager --help
uv run --group dev python -m copytrade_pm.pm_handoff --help
uv run --group dev python -m copytrade_pm.pm03_cli --help
```

Native Hyperliquid 1-minute Parquet and vendor-data research uses the optional Polars/Pandas extra:

```bash
uv run --extra market --group dev python -m pytest -q tests
```

CLI entry points: `copytrade-pm-replay`, `copytrade-pm-rank`, `copytrade-pm-scope`, `copytrade-pm-market-audit`, `copytrade-pm-handoff`, `copytrade-pm-research`, and **`copytrade-pm-shadow`** (offline research only).

Synthetic example, with a content-addressed owner-private report:

```bash
uv run --group dev copytrade-pm-shadow --input examples/pm03_synthetic.json --output-dir /tmp/copytrade-pm03-shadow-demo
```

No credentials or API connectivity are used by the PM-03 CLI.

The source research artifacts and private data remain under their existing VPS owner-private paths. Supply paths explicitly to the CLI, never commit data or credentials. Imported historical documentation under `docs/PM-*.md` records source-era results; current commands use `copytrade_pm` rather than `ensemble`.

## Scientific status

- 36 historical source wallets (6 original + 10 Wave 1 + 20 Wave 2).
- Four shortlisted wallets passed a **90% Propr-native 1m market-day data gate**, not a profitable follower or full-book execution gate.
- **Zero scientifically qualified manager seats**. PM-02's real-data research recommendation remains five EMPTY seats and zero actionable R.
- Historical HyperX fill times are not first-known follower signals. Source account completeness, execution capacity, Propr market identity and contractual compliance remain unresolved.
- Synthetic PM-03 scenarios are implemented for accounting, stress and policy research; they **must never** be advertised as real challenge pass probabilities. Verified public Propr defaults do not establish account-specific trading authorization or guaranteed broker fills.

## Evidence and Git history

The imported code retains a **12-commit filtered PM-only Git ancestry**, merged with the destination's initialization history. See [migration provenance](docs/PROVENANCE.md) and [original PM integration PR #8](https://github.com/hzminhzz/hyperliquid-expert-ensemble/pull/8). Git was filtered by *paths*; original commit IDs changed, and the mapping is documented. No original runtime, Telegram, deployment files, untracked research or secret data was imported.

The legacy ensemble advisory service remains owned and deployed independently by `hyperliquid-expert-ensemble`.
