# Trader Intelligence — prospective scientific validation protocol

**Declared:** 2026-11-03 UTC; research-only. **Status: REGISTRATION PROPOSAL, NOT AN ACTIVE OBSERVED HOLDOUT.** This document establishes a proposed future evaluation contract. It does not prove that the producer has registered/subscribed all wallets, that an independent auditor exists, or that a holdout has begun. Do not backfill an active study or reclassify historic fills.

## Study population and fixed future boundaries

- Primary already chosen portfolio: **P1 = S035 (ENA), S051 (BTC), S053 (HYPE)**, drawn from the existing published Phase-3 decision. This cohort is **hindsight-selected for research** and must never be called an independent historical discovery sample.
- Separate predeclared challenger: **P14 = P1 + S064 + Whale_0x5f94**. P14 adds a second portfolio-selection hypothesis. Include its trial in familywise testing; do not silently switch from P1 after observing P14 returns.
- Start: **2026-11-04T00:00:00Z**. End: **2026-12-04T00:00:00Z** (30 UTC days). Any observation whose first-local-receipt time predates a genuinely registered roster/signing plan is *ineligible*. If source registration is late, set a **new future** versioned start and disclose the change. This date range is not proof that capture was continuously active.
- Discover the private wallet identity fingerprints only through the registered owner-private address registry. Do not commit addresses or expose source account credentials. Record the actual roster-known-at and manifest SHA when the immutable plan is activated. Unknown parent/subaccount relationships remain unknown, not independent.

## Predeclared policies and execution

Compare the **same opportunities** at identical causal decision cuts under five separately counted policies:

1. Existing descriptive three-address 2:1 consensus (incumbent).
2. Conservative independence-aware consensus with parent/subaccount collapsing.
3. Source-profit leaderboard rank, using only profit recorded **before** the decision.
4. Conditional wallet-skill rank from matured follower **net R** strictly before the decision.
5. Full trader + directional-trade quality policy, requiring coherent source book, equity and native instrument identity.

A separate **matched, timestamp-blind market-only control** must use exactly the same instrument, direction, start, exit horizon and follower costs. It may not exploit wallet identity, source PnL or post-decision execution data.

- First signal clock = immutable **local first-known receipt**, not HyperX vendor time.
- Decision/entry = earliest permissible order decision after **300 seconds**; next causally executable minute/open (no same-bar future volume).
- Predeclare and evaluate **5m / 15m / 60m** independently matured outcomes. Include all unsuccessful, missing, rejected and timed-out candidates. Market outage is missing, not zero.
- Capture native Hyperliquid OHLCV with verified day SHA, predecessor-minute notional participation, venue-native funding events and independent bid/ask or conservative quote-surrogate error bounds. Price bars alone cannot certify account- or Propr-executable fills.
- Risk = same fixed research notional/stop budget for policy and control, independent from PM-02's 0.20R and PM-03 account authority; C/X stay **0R** until independent qualification.
- Evaluate base costs, **2× all executable costs**, ten-minute signal delay and a predeclared stopped-exit stress. Do not choose a favorable cost after the holdout. All pricing assumptions and rule snapshots must have immutable hashes and verified coverage before scoring.

## Scientific tests and falsification

1. Independently sign first-known receipt audits and **whole-account v2** matched source/follower/market-control economic outcomes in the existing `ProspectiveLedger`. Signature means a declaration was signed, not that a broker fill independently occurred.
2. Require a complete, deduplicated episode census and coherent source equity, positions, all-DEX exposure, spot/hedge legs and parent/subaccount clusters. Explicitly quarantine incomplete wallet-hours.
3. Only **training outcomes sealed before the decision cut** may train or tune a score. Freeze model hash, parameters and intended family size before the first eligible holdout cut. A/B may not be tuned on these outcomes.
4. Evaluate policies on matched timestamp/instrument/candidate universes; report coverage, missing outcomes, take-rate, net follower R, incremental R against matched market-only, fees/funding, worst loss, drawdown and 2× cost/ten-minute sensitivity.
5. Group correlated episodes by source wallet/parent and UTC day; bootstrap full calendar blocks. Report one-sided **95% lower confidence bound** on paired net incremental R, alongside drawdown and the number of genuinely independent effective observations. Adjust the five-policy comparison family and P14 challenger for repeated selection. A zero or negative bound **falsifies positive-alpha qualification** at this cut.
6. Require the primary policy to exceed both the incumbent and market-only control **after costs** with multiplicity-adjusted lower bounds strictly above zero; no instrument or wallet may be dropped based on observed losses. Positive nominal means without uncertainty, economically infeasible fills, incomplete coverage, failed stresses or insufficient effective sample size remain **NOT SCIENTIFICALLY QUALIFIED**.
7. Any rank or grade produced by historical, hypothetical, unsigned, uncalibrated, stale, corrupted or post-cut evidence stays **C/X at 0R**. Research scores do not grant account order authority.

## Executable signed-evidence gate

The audit is intentionally read-only and **does not create ledgers or sign outcomes**:

```bash
uv run --group dev python -m copytrade_pm.trader_intelligence_qualification_cli \
  --ledger /secure/existing-prospective-ledger \
  --auditor-public-key /secure/existing-auditor.pub \
  --asof 2026-12-04T00:00:00+00:00 \
  --holdout-start 2026-11-04T00:00:00+00:00 \
  --holdout-end 2026-12-04T00:00:00+00:00 \
  --selection-plan-sha256 <64-char-actual-pre-registered-plan-digest> \
  --horizons 5,15,60
```

The command can only run after real capture, independently reviewed selection plan and signed outcomes exist. It verifies the original SHA chain and trusted Ed25519 signatures, reports eligible v2 episodes and matched horizon coverage, groups correlated horizons per source event, and emits only descriptive follower-minus-control net R. Its result is **always NOT_SCIENTIFICALLY_QUALIFIED** until a distinct independent, frozen statistical and economic evaluation is implemented and verified.

## Matched walk-forward diagnostics (engineering amendment, 2026-11-03)

`trader_intelligence_walkforward.walkforward_diagnostic` reuses the existing
five-policy comparator at each *as-of decision cut*. It enforces explicitly
ordered, non-overlapping, 60-minute-or-greater embargoed folds, rejects a
candidate reused across folds, counts missing outcomes and controls without
zero-imputation and never ignores a cut outside the declared windows. It
calculates paired follower-minus-control R by policy, aggregates correlated
observations by UTC calendar day and computes a deterministic day-block
bootstrap lower diagnostic bound, with a conservative predeclared comparison
family default of 10 (five policies × two portfolios). Fewer than five observed
calendar days yield no bound; missing matched controls suppress the bound.

**Scientific limitation:** these offline descriptive bootstrap diagnostics do
not validate an independent real matched economic producer, actual Propr fills,
pre-registration, positive skill or a protected holdout. The tool always returns
`NOT_SCIENTIFICALLY_QUALIFIED`. There are no real P1/P14 300-second executed
follower/control observations to score in this study. The frozen future dates
are not enough to run genuine OOS evaluation. Cost/latency stresses require
matching independent observed scenarios; simulated tests cannot establish them.

## PIT trader features (engineering amendment, 2026-11-03)

`trader_intelligence_features.extract_asof_features` derives descriptive wallet ×
instrument direction, OPEN/ADD/REDUCE/EXIT/REVERSE status, parent-first
independence grouping, observed holding-time lower bounds and optional marked
notional-to-equity fraction from the versioned existing observation snapshot.
A continuous local zero-to-position transition is required before inferring
holding duration. A conflicting position chain, missing coherent source book,
unknown equity/mark or retrospective vendor-only receipt is never silently
imputed. A stable decision-cut report hash includes the **full as-of observation
content**, not only event IDs. These measurements are diagnostics, not proven
execution exposure, trader independence, A/B quality or a position target.

## Matched-benchmark integrity (engineering amendment, 2026-11-03)

The offline five-policy comparator now rejects conflicting duplicate episode IDs,
wallet outcomes outside the decision-cut monitored roster, future-first-known
labels, mismatched matched-control candidate identities, and controls whose
outcome clock precedes the selected hypothetical exit. These are mandatory
source-to-outcome binding checks, not statistical validation. Positive or negative
exploratory means remain descriptive only; none can establish a new independent
holdout or justify an A/B grade. Benchmark selection and evaluation must never
silently overwrite duplicate economic labels or merge different control events.

## 2026-11-04 continuation: model-cost and baseline comparability

The [engineering continuation](TRADER-INTELLIGENCE-CONTINUATION-20261104.md) introduces intentionally versioned `ti_matched_benchmark_v2` and `ti_matched_walkforward_diagnostic_v2` control-binding contracts. The control must match the exact episode, candidate cut, instrument, direction, horizon, entry/exit timestamps, cost R and execution-policy hash. The original `v1` descriptive input/report cannot be silently treated as `v2` without all these fields. Independent native data-day SHA checks, the four hypothetical fixed-input follower cost/latency/stop stresses and the read-only live journal source audit do **not** certify 300s executable follower/control economics or positive calibration. The previously frozen future study roster/window has **not** been activated; #31–#33 remain open.

## Already inspected data exclusions

The October–November prospective-journal/midpoint-markout period has **already been examined** in the [P1 exploratory diagnostic](TRADER-INTELLIGENCE-P1-EXPLORATORY-AUDIT-20261103.md), including P1 outcome means, intervals and multiplicity diagnostics. It is **permanently ineligible as an untouched independent validation window** for these selected wallets and model hypotheses. Do not use the apparent positive S053-HYPE results to silently redefine P1 or change the holdout family. The proposed Nov 4 window still cannot begin as a valid study without verified actual pre-registration, eligible source capture and an independent economic outcome producer.

## Current finding (2026-11-03)

The original immutable PM-01 prospective ledger and the PM-02 v2 contract already exist as code. In the inspected private PM-01 HyperX prospective/REST report trees, **no qualifying signed outcome ledger manifest was located**. Historical Q3 and 90-day fills and read-only opportunity-journal observations cannot repair that absence. Engineering code and signatures from unit-test fixtures are **not** positive research evidence. No live order, Telegram activation, or financial-account mutation is authorized by this protocol.
