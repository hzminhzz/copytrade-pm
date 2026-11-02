# Trader Intelligence implementation checkpoint — 2026-11-02

## Scope and contract

Research-only prototype on a separate, isolated worktree, not a live service. Source files:

- `src/copytrade_pm/trader_intelligence.py`: versioned roster, wallet event, strict source/known-at/decision clocks, deterministic SHA-256 JSON assessment, conservative A/B/C/X research references. Supports any roster cardinality; never imports the frozen PM-01 source_rows interface.
- `src/copytrade_pm/trader_intelligence_research.py`: offline minimum-300s 1m next-open hypothetical follower labels, explicit cost and capacity assumptions, shrinkage by independent outcome group, five exploratory matched-policy diagnostic rows. Always returns `NOT_QUALIFIED` for the benchmark.
- `tests/test_trader_intelligence.py`: deterministic contract, 1/36/94 roster, position reduction/reversal, historical-clock and future-receipt refusal, carry/missing evidence, losing follower despite winning source, and missing-exit tests.

No broker connector, Telegram publish or existing account ledger is touched.

## Scientific limitations and outstanding acceptance

**This is not a completed calibrated grading engine.** The optional `follower_evidence` dict can be caller supplied, and its maturity, matching and signed provenance are not independently checked. Do not supply a positive calibration or publish A/B to operational users until a validated immutable label producer, independent roster and train/holdout segregation are implemented and reviewed. The safe default `TraderIntelligence()` has no calibration and yields only C/X, with zero research R.

The current replay uses a constant specified funding rate, no stop-trigger intrahorizon exit, fixed minute-open marks and prior-minute volume. It records these as hypothetical proxy outcomes, **not executable matched Propr fills**. Missing marks and incomplete books must not be converted to profitable outcomes. Do not treat stop-distance-based R normalization as an enforceable order-loss bound.

The benchmark implementation is a **diagnostic scaffold**: absent market-only matched controls, outcome overlap purging, held-out policy training, forward validation, robust tail/calibration statistics and a PIT roster from inception. An arbitrarily supplied historical roster does not become unbiased by setting a flag. Do not infer alpha from matching synthetic fixtures.

Unresolved integration mismatch: `hyperliquid-expert-ensemble` (main `ef8d7c1`) has `ensemble/runtime.py` Telegram methods and does **not** contain `copy_board.py`, `copy_digest.py`, or `copy_opportunities.py`. Locate the real operator publisher (possibly another repository/service) before implementing Issue #34. Do not deploy the advisory service or change Telegram policies in this work.

## Next acceptance work

1. Complete TI-01 versioned external payload validation/strict chronology and TI-02 first-known read-only intake.
2. Bind source whole-books/equity, handle partial event chains and independent cluster evidence conservatively. Produce research specialty estimates from actual matured labels, not a user-supplied positive claim.
3. Upgrade follower economics: actual PIT costs/funding, matched market controls, exit path, hold grouping and fixed validation policies.
4. Run real-data experiments with legally known PIT rosters and chronologically purged holdouts; record negative results.
5. Locate actual Telegram publisher and add an optional artifact adapter with strict fallback and zero-production-policy change.
6. Run combined suites, build, CI, fault/restart and cross-repository contract tests; review and merge only after genuine acceptance.

Engineering tests are not scientific qualification, deployment, or trading authorization.
