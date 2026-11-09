# ADR: V4-aligned rapid wallet screening with three 1m price scenarios

**Date:** 2026-11-09

**Status:** APPROVED FOR IMPLEMENTATION PLANNING (Q1–Q5 owner-approved); **NOT IMPLEMENTED**

**Scope:** New, versioned offline **research-only** screening path in `copytrade-pm`.

**Related:** [official position-first T+300 ADR](2026-11-08-position-first-t300.md), [fixed-k default](../RISK-BUDGETED-K-SIZING-20261106.md), [offline engineering boundary](../OFFLINE-MILESTONE2-ENGINEERING-ACCEPTANCE-20261104.md), [real historical-oracle evidence](../OFFLINE-PIT-REAL-ORACLE-20261104.md).

## Why

The existing historical Polars oracle batches retrospective **fill timestamps** at a strict next-full-minute open and produces market-context **SCREEN_ONLY** results. V4 forward SHADOW instead uses first-local **official complete-position transitions**, an immutable T0+300 due time, observed Vike prices, fixed-k, and PM03/PM04. A verified real P1 case had T0 `10:09:36.032617Z`, modeled attempt `10:14:38.250828Z`, while Polars would choose `10:15:00Z`.

For fast discovery, the owner accepts 30–60 seconds of historical execution-price approximation and only has 1-minute OHLCV for many research windows. The aim is **rapid, defensible wallet ranking**, not tick/L2 reconstruction or an exact match to the live minute price. Preserve old source tapes, immutable reports, policies and live services.

## Approved decisions

### Q1 — Historical source reconstruction and evidence label

- Derive historical episode/position-change candidates from immutable, de-duplicated source fills **only where reconstruction coverage supports them**. Never treat an unknown opening position as flat, a vendor fill as a complete official SourceBook, or a past exchange fill timestamp as the original first-local receipt.
- Carry source quality/coverage and event-clock basis into every derived score. Use `HISTORICAL_ORACLE` / explicit **proxy** evidence labeling where first-known is not independently available.
- Incomplete books, missing causal exit data, insufficient market coverage or unknown cost/capacity mean `UNKNOWN` or typed `BLOCKED`, not invented zero-cost profit. Rankings may show exploratory candidates with lower evidence confidence; no false qualified PnL.

### Q2 — One 1m execution clock, three price scenarios

For a historical candidate with proxy time `T0`, let `eligible_at = T0 + 300s`. Use one UTC minute grid, each bar timestamped by its **open**.

1. **BASE:** first 1m `open` **strictly after** `eligible_at`.
2. **DELAYED:** next 1m open, one full bar after BASE.
3. **ADVERSE:** same BASE execution minute; apply **additional 10 bps adverse slippage on each executed side**, on top of base costs (not in place of them).

Example: `T0=10:09:36Z`, `eligible_at=10:14:36Z`; BASE `10:15:00Z`, DELAYED `10:16:00Z`, ADVERSE `10:15:00Z` with extra directional slippage. A current candle's **future close** is prohibited for an intraminute decision. Apply causal fills/exits as instrument+DEX-specific minute observations, not nearest future bars mislabeled as known.

**Source reductions/exits:** use first causally available minute open strictly after the historical reduction observation, **without another entry-style five-minute delay**. Right-censor missing bars or incomplete exits; never fabricate a flat book. Forward V4 continues genuine due=T0+300, 30s grace, immediate legitimate reductions, and independent current quotes **unchanged**.

### Q3 — Costs, capacity, and sizing

- Default research intent uses the **same V4 risk-budgeted fixed-k native quantity policy**, valid selected position vector, independent follower-mark notional conversion, amount-step/minimum-notional constraints and frozen per-wallet k. **Do not** silently import the legacy whole-wallet NAV-relative mode or invent historical NAV.
- Use the existing `EstimatedMinuteExecutionModel` semantics where 1m data permits: **5 bps taker fee, 4 bps half-spread, 8 bps baseline slippage**, participation-scaled impact up to **10 bps at a 10% minute-volume cap**. Directional ADVERSE adds 10 bps **per side** to this existing cost stack.
- Historical participation/capacity uses **the previous fully completed 1m bar's volume**, which is known by the candidate open. It is a causal **capacity proxy**, not equivalent to V4's as-of forming-minute volume, L2 depth or executable fills. Missing volume/invalid market scope is a typed unpriceable result, not unlimited fill.
- Preserve existing financial engine ownership: stage-1 vectorized score is **estimated follower economics**, never a PM03 certified account, guaranteed challenge pass or trading authorization.

### Q4 — Two-stage selection, not three financial replays

- **Stage 1, for all eligible wallets:** once-loaded Polars source+OHLCV panel produces BASE, DELAYED, ADVERSE per-trade price/estimated-cost/estimated-PnL columns. Rank primarily by cost-adjusted estimated follower performance, alongside observation days, position reconstruction/market coverage, recent seven-day persistence, and sensitivity to the two stressed scenarios.
- Stress outcomes are **robustness diagnostics**, not three strict pass/fail gates; do not automatically discard a promising wallet solely for a small negative stress result. Explicitly report missing/blocked outcomes rather than dropping them from denominators.
- **Stage 2, shortlist only:** use existing PM03/PM04 chronological financial accounting for overlapping pods, gross/concentration limits, independent risk, daily/trailing drawdown, HALT, financing where evidenced, and right-censored/unresolved exits. No parallel financial simulator, generic event bus, registry or broker.
- Where authentic prospective first-known sources/quotes are available, preserve a separately labeled forward-replay parity fixture and compare causal decisions; do not promote retrospective estimates to authentic source proof.

### Q5 — Performance and compatibility budget

- Source and market data are scanned/verified **once**, with three vectorized Polars expressions or joins in a common lazy plan; reuse immutable SHA-addressed caches and DEX-specific market identity. Avoid per-event Python callbacks, per-row Pydantic models, or three complete PM03 replays for all wallets.
- **Initial engineering target:** <=25% median **warm-cache elapsed-time overhead** and no material memory regression versus the equivalent single-scenario screening input, using the same representative 90-day wallet universe and host. Measure both streaming and in-memory deterministic equivalence, cold/cache behavior, peak RSS, cache SHA, scenario counts, and right-censor/missing-data rates. This is a **target to measure**, not an existing benchmark or proof of speed.
- The original `pm_offline_job`, `pm_offline_oracle`, `pm_offline_eligibility` and all frozen historical result SHAs remain intact. The new path/report is **versioned opt-in** and cannot silently reinterpret older `HISTORICAL_ORACLE_NATIVE` or `SEALED_SYNTHETIC_PM03` evidence.
- Tests must cover fractional-minute eligibility, same-minute boundary, entry delay, early reductions, missing prior volume, incomplete source episodes, long/short adverse sign, fees charged **once**, participation cap, DEX identity, scenario equivalence/ordering, and nonqualified vs qualified report labels.

## Explicitly rejected alternatives

- Full tick/L2 backfill or second-by-second historical execution modeling for this quick wallet screen.
- Using a forming candle's later close or historical future volume to price an earlier order.
- Running three independent full account simulations and re-reading every market day for all wallets.
- Altering V4's official position authority, prospective due/exit timing, Guardian boundaries, live services or frozen old research contract as a shortcut.
- Presenting historical proxy source timestamps, reconstructed complete books, minute-volume estimates or synthetic PnL as independently verified real follower fills.

## Consequences and planning readiness

**Ready for a bounded implementation plan**: new opt-in screening artifact/contract, three-column price sensitivity, shared frozen fixed-k/cost policy, evidence typing, candidate shortlist handoff to PM03/04, causal fixture tests, resource benchmark, and old-report compatibility proof.

**Still unknown until implementation and evidence:** usable reconstructed trade coverage per wallet, actual throughput/memory overhead, historical fill/exit outcome quality, price sensitivity of real candidates, and broker-executable economics. These are outcomes to measure, not requirements to invent data or expand implementation scope.

**Authorization:** approval of Q1–Q5 is **design approval only**. No broker order, financial policy promotion, live service deployment, data repair, running observer change or scientific qualification is authorized by this ADR.
