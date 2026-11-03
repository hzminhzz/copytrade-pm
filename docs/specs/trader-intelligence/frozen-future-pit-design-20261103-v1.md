# Trader Intelligence v1 — frozen future PIT research design (registration pending)

**Protocol freeze date:** 2026-11-03 UTC. **Owner:** copytrade-pm Trader Intelligence research.
**Status:** `DESIGN_FROZEN_NOT_ACTIVATED`. This checked-in design is a pre-outcome commitment to the comparison rules, **not** evidence that a PIT roster was independently registered, an independent auditor signed observations, or a future study ran. Do not backdate activation or call historical July–November samples unseen.

## Population, clocks and endpoint

- P1 primary: `S035-ENA`, `S051-BTC`, `S053-HYPE`.
- P14 challenger: P1 plus `S064` and `Whale_0x5f94`. The hypotheses are familywise-related, not two independent discoveries.
- Future candidate window originally specified **2026-11-04T00:00:00Z** (inclusive) to **2026-12-04T00:00:00Z** (exclusive). It applies **only** if independent identity, source capture and frozen protocol registration demonstrably exist *before* the start. Otherwise record a missed window and freeze a new version with later dates; never retroactively activate this one.
- Existing October–November shadow midpoint/markout reports and Gemini/HyperX retrospective fills are exploratory and excluded from protected forward validation.
- Roster-known clock is the actual registered first-known roster event, not a clock invented from this file or the listed wallet aliases. All named source identities, parent/subaccounts, spot exposure, DEX coverage and account equity must independently reconcile; unknowns are **NULL**.
- Five policies per portfolio (10 family tests): incumbent 3-address 2:1; parent-cluster independence-aware consensus; source PnL rank learned only from matured pre-cut source evidence; follower net-R skill-only; and trader+trade quality. No post-cut selection; no discarded losers. Each policy sees the **same candidate cuts** and markets.
- Input event clock must be immutable local first-known. Earliest follower entry is **first-known + 300s**, at the next legitimately executable minute. A 600s delay is predeclared stress. Exit horizons **5, 15, 60 minutes** with matched control, same market, direction, delay, costing and exit policy. Event time from HyperX alone cannot establish this.
- Source trades, their failed/incomplete events and no-trade controls remain in census; missing outcome or failed executable capacity is not a zero return.
- Source native 1m price/bar-day SHA, prior-completed-minute capacity, fee/spread/slippage, funding and stop order outcome must be independently checked. Require base cost, 2× all executable costs and 600s delay. Do not use a midpoint markout as independently filled Propr economics.
- Actual P1/P14 research budget and risk R are **not order sizes**. A/B grade activation prohibited; C/X remains 0R.

## Evaluation lock

- Training outcome must be independently signed, matured and sealed **strictly before each decision cut**. Validate model hashes, predeclared selection and parent cluster before scoring.
- Five policies × two rosters counted as **10 attempts** regardless of result. Exact same source/decision horizon and market for policy and matched market-only control. No favorable post-hoc instrument or wallet filtering.
- Non-overlapping chronological folds with an embargo at least the maximum tested label horizon. If changed research horizon is longer, increase embargo before **any** protected evaluation.
- Report observed denominator, missingness and dependent groups by parent × UTC calendar day; paired follower-minus-control net R, hit rates, PnL tails/drawdowns, coverage, latency sensitivity, 2× costs and uncertainty. Deterministic calendar-day bootstrap lower bound and familywise comparison control. Positive means are insufficient.
- Full model must outperform incumbent and market-only matched control after cost with multiplicity-adjusted lower confidence bounds strictly above 0, no failed cost/tail stress and independent source-economic attestation. Otherwise scientific result is NOT QUALIFIED or FALSIFIED depending on measured evidence; unavailable outcomes are BLOCKED, not proof of no alpha.
- `trader_intelligence_walkforward.walkforward_diagnostic` is an **exploratory deterministic implementation** of fold matching and block uncertainty. It is not an independent signed economic evaluator and never outputs a qualified grade. Do not promote it to positive certification.

## Actual activation evidence needed

No verified external registration or independent 300s follower/control settlement producer has been supplied as of this protocol freeze. Consequently **this is not an ACTIVE scientific study**. When an independently reviewable evidence collector exists, register a new immutable owner-private activation receipt with actual wallet identity hashes, collector and auditor public keys, subscription/book coverage clocks, study/model/source-policy SHA, actual venue and costs, exact future start and end, and evidence-census continuity. Do not modify this frozen design to imply it was operational. Keep pre-existing source histories and original signed receipts immutable.

## Engineering and state separation

Full core/native tests, Ruff and CI can establish IMPLEMENTED/ENGINEERING VERIFIED, not HISTORICAL VALIDATED or PROSPECTIVE VALIDATED. The existing ensemble Telegram overlay is a separately pinned research-only C/X digest at 0R, never an account or trading deployment. **LIVE AUTHORIZED = false**. For the original design and current readiness gate see [study](../../TRADER-INTELLIGENCE-PROSPECTIVE-STUDY-20261103.md).
