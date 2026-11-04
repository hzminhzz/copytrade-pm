# Phase 6B recovery and conditional risk research — 2026-11-04

**Dated v13 snapshot, retained for evidence lineage.** The later [Phase 6A input reconciliation and v19 disposition](PHASE6A-PHASE6B-RECONCILIATION-20261104.md) correctly isolates four ACT08 spot fills; the pure-perpetual universe is 95, not the original 96 mixed markets. Previous paths and counts on this page describe the v13 run and must not be silently reinterpreted as current.

**Engineering disposition: COMPLETE for the feasible read-only historical research.**
**Scientifically qualified Phase 6B follower PnL: NOT ESTABLISHED.**
**Trading authorization: NONE.** No order gateway, subscriptions or active production services were altered by this work.

This is the successor to the **dated** [initial Phase 6B coverage audit](PHASE6B-MARKET-RISK-AUDIT-20261104.md), whose v1/v2/v3 inputs and reports are immutable. This recovery does **not** overwrite the initial source pages, Gemini scorecard, portfolio definitions or earlier research outcomes. All paths below are **private VPS paths**. Git contains only research code/tests and this disclosure.

## Results at a glance

| Area | Evidence-backed result | Status |
|---|---|---|
| Frozen portfolios | Four original A/B compositions (base/active) and two explicitly *non-optimized* equal-capital 3-pod controls | VERIFIED identities and frozen k |
| Historical fills | 7 wallet files SHA-verified, **18,592** retrospective fills; ACT08 authentic 5,475 raw mixed HL/HyperX fills recovered with position-before fields and IDs | VERIFIED raw bytes; NOT a complete account |
| Source equity | 8 accounts acquired via public Hyperliquid `/info portfolio`; 13–43 `allTime` observations per wallet in 90 days | RETROSPECTIVE SPARSE; max gaps ~168–170h |
| Native minute coverage | 96 distinct symbols, **5,239,441** instrument-minutes SHA and OHLCV verified; **26** symbols continuous across the full 90d | VERIFIED exact-minute price data, incomplete universe |
| Data repair | Rebuilt 76 incomplete Hyperliquid 2026-10-30 native symbol-day partitions using existing canonical CryptoHFTData writer, 0 reported failures | RECOVERED market-source partition integrity |
| Exposure interval audit | **2,543,208** conditionally reconstructed nonzero instrument-minutes; **355,026** on unverified market days | CONDITIONAL observed-fill book; not all-account exposure |
| Historical account follower backtest | No independently reconciled historical all-DEX equity/funding, some position chains discontinuous; no first-known clock | BLOCKED (P&L/DD/first-passage NULL) |
| Snapshot stress model | 6 configurations × 90 fixed daily points = **540** observations, S1–S8 conditional diagnostics | EXECUTED as labeled hypothetical stress, NOT true account replay |
| Genuine PM-03 authorization gate | **540/540 RED**, **0** permissions for new risk; no simulated or actual flattening claimed | VERIFIED fail-closed behavior |
| Account scenario matrix | **180** frozen portfolio × policy × stress combinations explicitly `BLOCKED_NOT_RUN`; 3 empty typed Parquet output schemas | Correct absence of complete-account outcomes |
| Final binding | SHA-verified cross-generation immutable manifest | VERIFIED engineering lineage |

## Frozen portfolio identity and sizing

The four original Gemini portfolios are:

- **A_base:** H21 25%, N01 25%, N07 20%, N02 15%, H17 15%.
- **A_active:** H21 35%, N01 35%, N07 30%, N02 25%, H17 25% (nominal sum 150%).
- **B_base:** N01 25%, N07 25%, N02 20%, N05 15%, ACT08 15%.
- **B_active:** N01 35%, N07 35%, N02 30%, N05 25%, ACT08 35% (nominal sum 160%).
- **C_equal:** H21/N01/N07 each 33⅓%; **D_equal:** N01/N07/ACT08 each 33⅓%. These are new diagnostic **equal-capital controls, not equal-dollar-risk allocations** and not Gemini-optimized portfolios.

The Gemini original `original_effective_k` for each frozen constituent was applied as a **research scalar** `k_source_report × $10,000 / $100,000`. This reproduces the original source-*notional* weighting convention on the smaller follower account. **It is not the required dynamic wallet exposure/equity scaling, and is not authorized for actual trade execution.** Reliable dynamic scaling requires authentic prior **whole-wallet** source equity and all-DEX positions at each decision.

## Repairs completed

1. **ACT08 false missing-source blocker:** The consolidated Phase 4 CSV had discarded source position-before fields. The authoritative existing raw `data/broader_active_inventory_fills_90d/` contains 5,473 Hyperliquid fills with `startPosition` and 2 HyperX fills with `start_position`, all with trade IDs. The adapter reads/normalizes both without modifying the immutable source. The source-chain audit still detects three breaks on coin `@107`; it does not erase or synthesize missing orders.
2. **Initial source book numeric bug:** A `Decimal("0.0")` source position had been labeled “unknown” because the original comparison used string `"0"`. The audit now compares numeric Decimal zero. Same-ms linked fills preserve stable causal chain order rather than arbitrary TID ordering.
3. **Incomplete native 2026-10-30 bars:** The canonical `ml4t-data` CHD writer detected and rebuilt 76 incomplete symbol-day partitions; the new independent 1m auditor verified the resulting Parquet against sidecar SHA and exact timestamp/OHLCV schema. We retained older audit generations. This is a data-lake repair, **not** wallet-fill acquisition.
4. **Historical equity look-up:** Bounded eight-account `/info portfolio` acquisition stored native raw responses with retrieval-clock and SHA. It established sparse retrospective history, not historical account-wide margin/funding or first-local receipts.
5. **Market audit SHA pinned to stress:** The new conditional stress runner verifies each consumed native Parquet day digest against the independent frozen v6 minute audit. A changed file, unknown native venue, unavailable quote or conflicting source generation fails closed.

The exposure audit's **v7** preliminary figures were inflated by reordering same-millisecond fills. Reconstructed v10 now reports 2,543,208 instrument-minutes and 355,026 not covered by fully verified daily market sources. Intervals are conditional on the last observed fill's after-position being carried until another observed event or the window end; this **terminal carry is not an independently verified complete account snapshot**. Neither these durations nor a market-day count can establish follower PnL.

## Six frozen portfolio diagnostics, not challenge backtests

Model values are dollar sensitivities on **priced, retrospectively observed legs only**. Individual column maxima may occur on different dates. They do not describe liquidation, realized losses, the unknown missing book, or calibrated loss probabilities.

| Model | Maximum priced observed gross | Maximum hypothetical loss from +50% short squeeze | P0 modeled veto days | P1 / P2 modeled veto days |
|---|---:|---:|---:|---:|
| A_base | $13,241 | $5,714 | 62 | 74 / 74 |
| A_active | $18,674 | $8,009 | 72 | 76 / 76 |
| B_base | $24,042 | $10,887 | 64 | 77 / 77 |
| B_active | $45,030 | $20,786 | 74 | 78 / 78 |
| C_equal | $17,591 | $7,618 | 64 | 72 / 72 |
| D_equal | $40,543 | $19,962 | 62 | 72 / 72 |

`P0/P1/P2` veto-day counts are predeclared **one-step synthetic sensitivities**, not historically executed risk intervention or trading permission. P1 uses a hypothetical **$300 total pod budget**, P2 adds a hypothetical **$350 daily soft threshold**, $20,000 gross cap and $5,000 instrument cap. P0 sensitivity uses $450 modeled daily hard loss and $1,000 trailing threshold. These dollar parameters are **study assumptions** and not authenticated Propr account terms.

**S1:** For each fixed snapshot, compute the price-only return over the prior one hour of the source holdings last observed before that hour. Actual intervening orders may have changed those holdings. **S2:** Conservative 10% adverse-per-pod gross shock, which is a hedge-break stress upper bound and may not represent a single feasible market price vector. **S3:** Uniform −10%, −20%, −30% net delta shocks on priced holdings. **S4:** +50% price jump against net short exposure. **S5:** 30bps additional one-off unwind execution drag; no real bid/ask, latency or platform TCA is claimed.

**S6:** Missing source scope or quotes result in model **block-new-risk**. `flatten_executed=null` because an actual exit cannot be assumed. **S7:** Leave each pod out of *observed* positions without renormalizing others, reporting only change in hypothetical net −30% shock. **S8:** Three prespecified consecutive 30-day cohorts report coverage and worst conditional loss, without imputing missing returns or creating Sharpe/OOS claims. Each of these 540 conditional snapshots also invokes the native `pm03_risk.classify` on an explicitly **unconfirmed rulebook and unknown state**: all 540 yield RED, zero new-risk admissions. It is a genuine PM-03 fail-closed engineering check, not an actual rolling account replay.

**NO RESULT:** The original Gemini N07 0.03% trailing DD, A 1.02%/1.60%, B 0.46% trailing DD, $10,000 follower net PnL, kill-switch realized execution, first-passage challenge pass probability or risk-normalized 3-v-5 pod performance. Missing historical source capital, full book, actual first-known, funding, and native minute markets make those **UNKNOWN/BLOCKED**, not zero.

## Private immutable evidence

Authoritative private report roots:

- `/home/quant/.local/share/copytrade/reports/phase6b-portfolio-history/g20261104Phase6BPortfolioHistoryV1/` — eight raw official histories, metadata and report SHA.
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-coverage-v4/` — seven verified fill source files, instrument continuity flags and frozen assumptions.
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-minute-v6/` — independent exact-minute SHA and OHLCV audit for 96 instruments.
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-observed-exposure-v10/` — corrected source-position interval and exposure availability audit.
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-snapshot-stress-v11/` — 540 conditional portfolio-snapshot S1–S8 stress results and PM03 supervisor negative admission.
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-blocked-scenarios-v12/` — 180 **genuinely blocked** account policy/outcome rows, empty typed Parquet economic outputs.
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-final-disposition-v13/` — cross-generation SHA signoff and classification.

The final `final_disposition.json` binds the exact source, minute, exposure, historical-equity, snapshot, and blocked-economics hashes. Its scientific outcome is `NOT_ESTABLISHED`; its engineering status is `COMPLETE` **only for the bounded, feasible research and data repairs**.

## Reproduction and guards

Entry points are native Python modules:

- `python -m copytrade_pm.pm_phase6b` (requires original Phase 5, verified New-50, Phase 4 raw sources, market root, new output).
- `python -m copytrade_pm.pm_phase6b_portfolio_history` (**network read-only**, bounded 8 public `/info` requests, requires a fresh `g...` output generation).
- `python -m copytrade_pm.pm_phase6b_minute` (native SHA minute integrity).
- `python -m copytrade_pm.pm_phase6b_activity` (position-after diagnostic and exact-market inventory).
- `python -m copytrade_pm.pm_phase6b_snapshot_stress` (requires matching frozen source + exact-minute audit and native market root).
- `python -m copytrade_pm.pm_phase6b_blocked` (empty economic outputs with explicit blocker).
- `python -m copytrade_pm.pm_phase6b_finish` (final cross-generation SHA/signoff).

Use the exact paths/CLI flags from `--help` for reproduction; never reuse an output generation with different bytes. Tests:

```bash
uv run --frozen --group dev python -m pytest -q tests
uv run --frozen --group dev --extra market python -m pytest -q tests
uv run --frozen --group dev ruff check src tests
uv run --frozen --group dev ruff format --check src tests
uv build
```

**Next scientifically necessary workflow:** forward prospective wallet/parent/subaccount snapshots with independently verifiable account equity and funding; real first-known clocks; native market quotes and execution/fee/capacity receipts, then sealed matched follower/control paper study. **Cannot manufacture first-known timestamps for August–November 2026 by querying an API after the fact.** No wallet or combination is authorized for live risk by Phase 6B.
