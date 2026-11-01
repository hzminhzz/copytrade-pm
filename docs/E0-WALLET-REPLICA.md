# E0 wallet replica — source-fidelity research contract (2026-11-01)

**Decision:** Whole-wallet **observed target positions** are the research baseline. A fill is a state transition, not an independently sized trade signal. The E0 adapter is `pm_wallet_replica`, not a replacement for PM-03 or PM-04. The original A/B/C E1/E2/E3 artifacts are immutable *historical-oracle partial-episode diagnostics*; they are not source-account replicas and cannot be relabeled.

## Invariants

- Each pod is one explicitly scoped account identity (master vs subaccount is not guessed). All active signed legs across the selected scope are considered; a missing market or hedge blocks rather than gets dropped.
- E0 uses exactly one positive `pod_capital_usd / audited_source_equity_usd` scalar per **complete observed book**. Proportions are not changed by per-signal budgets, volatility scaling, preselection of closed episodes or a discretionary leverage estimate.
- A snapshot must have complete account census, reconciled denominator, gap-free event continuity, source SHA, source event time and an actual **prospective local first-known time** no later than the follower decision. A self-declared `True` is not external evidence: independent source authentication remains outside this module.
- Downstream PM-04 and PM-03 may reduce/reject/split positions. Their decisions never rewrite E0 source intent. Store three books: **source-intended**, **risk-approved**, **actually executed**. Do not infer actual fills from simulation.
- `fidelity` records risk-overlay vs execution divergence using gross-dollar L1 measures. A flat source has UNKNOWN denominator (`null`), not perfect fidelity. A missing mark fails closed. E0 tracking error is not a profit metric.

## Five-action migration status

| Action | Execution state | Gate to completion |
| --- | --- | --- |
| 1. Freeze A/B/C | Existing sealed reports preserved; this decision supersedes their *interpretation* only | Historical artifacts untouched, no post-hoc promotion |
| 2. E0 whole-wallet baseline | Implemented `WalletBook -> replicate`; protected by source/clock gates | Independent live account census and full capital/funding reconciliation |
| 3. Fidelity measurements | Implemented `fidelity` stage-by-stage: approved vs intended, executed vs approved, total | Actual broker receipts before declaring *real* execution fidelity |
| 4. Re-run A/B/C as E0 | **BLOCKED_EVIDENCE** for genuine historical replay; never synthesize full Q3 books | Q3 contemporaneous verified whole books + equity + knowledge clocks, or a newly frozen future window |
| 5. Prospective qualification | Retain PM-01 signed receipt/economic-outcome workflow; no promotion | Non-retrospective observations, independent signed matched follower/control, OOS tests and real broker account rules |

## Existing A/B/C evidence and what it actually answered

- **A:** `W028 + W042 + W030`, independent completed episodes and batched execution. `docs/PM-36-three-pod-2026Q3.md` records 204 included episodes selected from 263 completed, 2,761 source fills and 23 instrument names. It excluded unfinished/open positions and unverified hedges. Source-relative account sizing was not measured. Its selected 92-day PnL cannot be renamed E0.
- **B:** `W044 + CA-005 + W031`, source-specific episode filters. Existing B branch `research/portfolio-b-e123-2026q3` holds concurrent uncommitted code; preserve it. Independent E1/E2/E3 trial evidence and actual source book qualification must be audited before comparisons.
- **C:** `CO-001 + W015 + VS066`. E1/E2/E3 12 scenarios stopped at differing dates because of exact 1m price gaps; no method ranking. E4 on branch `research/portfolio-c-e4-wallet-fidelity` implements proportional complete-book target semantics, but source preflight reports **zero admissible Q3 E4 snapshots for each of three wallets**. Do not import the E4 Q3 synthetic fixture as historical evidence.
- Official prospective E4 acquisition has master + subaccount discovery and all-DEX position frames, but independently reconciled combined source capital is still unavailable, and account scope of subaccounts is unknown. A source snapshot observed October 31 cannot become a July receipt.

## Portfolio adapter migration — no fabricated runs

Preserve legacy E1/E2/E3 and E4 functions and their sealed outcomes as separate, labeled experiments. For each wallet A/B/C, an audited producer must emit `WalletBook` with an explicit master/subaccount scope, original position identities, all-DEX census, reconciled account equity, account event sequence, receipt clock and original evidence SHA. Feed E0 intended books to PM-04 as atomic *full-book target revisions* at the first legally subsequent decision; compare PM-04 risk-approved and executed books via `fidelity` on the exact native market and mark time. Reuse PM-03/04 execution/risk accounting and immutable event lineage; do not create a second ledger.

The source scale may change when new audited source equity arrives; it must not be inferred from a new fill amount. E0 does not guess leverage, margin contribution or lot-size equivalence. Hedge/correlation benefits may affect risk-policy choices but never license dropping a hedge while claiming faithful replication.

## Qualification paths

**Retrospective path:** Audit genuine source books and account NAV at each event, retain exchange event timestamps distinct from knowledge time, and label results `HISTORICAL_ORACLE`. Even if a full quarter becomes reconstructible, it cannot prove prospective follower execution.

**Prospective path:** Capture first-local account state *before* it changes; detect reconnect gaps, censuses, transfers, funding and position changes. Reconcile all-DEX account states to independently observed equity/collateral; then make read-only PM-04 targets. Pair independently verified follower/control outcomes after maturity before PM-02 qualification. Until then: `BLOCKED_EVIDENCE`, zero qualified wallets, no order gateway.

## Validation

Focused tests: `uv run --group dev python -m pytest -q tests/test_pm_wallet_replica.py`.
Repository check: `uv run --group dev python -m pytest -q tests`; `uv run --group dev ruff check src tests`.
No external live execution, Propr broker authorization, or claim of first-known Q3 events follows from these tests.
