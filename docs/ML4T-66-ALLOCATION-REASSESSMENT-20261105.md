# ML4T-66 — existing research audit and contract-specific allocation hypotheses

**Date:** 2026-11-05. **Authority:** live owner-private SQLite, plus original local fill JSON and precomputed research CSVs. **Status:** `RESEARCH_ONLY; BLOCKED_ECONOMIC_EVIDENCE; NO_AUTHORIZED_PURCHASE_RECOMMENDATION`.

This is a correction of the earlier acquisition-centric approach. The original request was **two distinct $10,000 copytrade multi-pod allocations, for the 2-step Explorer and EOD-trailing Sprint**, not merely an API and data recovery task. Read the existing studies first, preserve their source SHA lineage, run the actual models and avoid treating historical source events as first-local follower knowledge. No portfolio is registered or traded by this audit.

## Source and provenance

Use the live `ml4t-strict-66` SQLite cohort and `ml4t_strict` aliases, exclude `propfirm_exclusions`, and match *full hexadecimal addresses*, never filenames. Registry `doctor` verified inventory SHA `3217b46450dcd4fe7b23c17079bf50eb99d585546002610e2e189779ef0f4bf8` and 66 unique cohort wallets at inspection. A supplemental new private generation of official `/info` historical raw fills (9 API requests, 15,357 fills for 5 previously missing accounts) completes **raw-fill presence** to 66/66. It does **not** prove completeness of every source account, position book or historical receipt clock.

Historical precomputations in the dirty primary checkout (read only):
- `docs/ML4T_66_MASTER_SCORECARD.csv`
- `docs/ML4T_66_STRUCTURAL_PROFILES.csv`
- `docs/ML4T_66_TOP20_PRECOMPUTED_ENSEMBLES.csv`
- `docs/ML4T_66_CORRELATION_MATRIX_TOP25.csv`
- `docs/ML4T_66_DIRECTIONAL_CONFLICT_MATRIX.csv`
- `docs/PHASE7_ML4T_INSTITUTIONAL_METRICS_TOP25.csv`
- `docs/PHASE7_ML4T_PRECOMPUTE_SPEC.md`

**Different cohort warning:** the separately published Phase7 ML4T institutional metrics are for N07, H21, N02, ACTxx and others; they do NOT establish a skewness/PSR score for `ml4t-strict-66` Mxx accounts. Do not transplant those moments into Mxx scoring. Existing Phase7 328-combination and $10k major-four reports use known-book gross-normalization, **not** the user-mandated source-equity-normalized sizing. They are useful as a method and negative-control reference only.

## Reproducible independent corrections

The read-only audit `scripts/ml4t66_existing_research_audit.py` rechecks the precomputed scorecard against actual SHA-preserved source rows and current SQLite aliases, recovers unambiguous timestamp-group position endpoints using a directed before/after graph (not TID ordering), and measures source-supported same-coin overlaps. It found:

- 66 scorecard rows, **11 with stale current alias identity or raw-fill counts** (including old synthetic 1-fill placeholders).
- The precomputed directional-conflict matrix has **zero nonzero conflict rows**; that is not evidence of no risk. Among observable between-fill intervals, M33 and M42 show **257.59 h opposing BTC exposure and 65.99 h same-direction BTC exposure**. M52/M56 show **296.14 h same-direction HYPE exposure** and **2.47 h opposing**.
- Profile labels are sometimes misleading. Gross *fill-turnover* dominance (not instantaneous book allocation): M52 **79.51% ETH** despite HYPE label; M56 **56.61% ZEC** despite HYPE label; M33 **74.95% BTC** despite XMR label; M42 **66.19% BTC** despite ENA label; M53 **47.91% SOL**; M10 BTC **27.05%** among six markets.
- Reconstructed, contiguous same-side source-chain span medians: M10 **87.46h**, M53 **36.09h**, M33 **21.95h**, M42 **5.07h**, M56 **4.51h**, M52 **3.83h**. These are *supported chain spans*, not independently validated whole-account trade holding distributions.
- Current wallet fill histories are left/right censored differently: M10 first Aug5,last Oct20; M56 first Sep16,last Nov2; M53 first Sep21,last Oct22. Absence of fills afterward does not prove flat inventory or no loss.

Original precomputed `M52+M56+M10` claims +72.04% and 0.13% drawdown; those are **not reproducibly established full follower results** and include an HYPE co-directional concentration. The very small drawdown must not be used to price an EOD-trailing contract.

The audit also sums `closed_pnl` and source-reported fees across original retrospective fills and multiplies by the *static* reference `k_i = w_i * min(0.35, 10000/E_leader,i)`, with equal `w_i=1/3`. As an independent arithmetic diagnostic only, the historical source **closed** minus reported **source** fees on that static scale sums to: M52+M56+M10 **$6,749.68**, M33+M42+M53 **$4,972.20**, M10+M33+M53 **$4,702.52**, M52+M42+M53 **$5,544.50**. These values **are not $10,000 follower PnL**, and are not directly comparable across incomplete source windows. No open-inventory MTM, future bid/ask execution, follower friction, funding or correlated loss is measured by this diagnostic.

## Two distinct candidate allocations — for next full simulation only

All allocations below are **unapproved research hypotheses**, not registered or certified portfolios. Full addresses and raw private fills are in the private SHA evidence, not committed to Git.

| Objective | Selected wallets | Weights | Static `k_i^eff` | Structural motivation |
| --- | --- | --- | --- | --- |
| Explorer 2-Step swing | **M10, M33, M53** | 1/3 each | M10 **0.09888257**, M33 **0.11666667**, M53 **0.11666667** | Longest observed supported holds, BTC/alt, BTC and SOL/UNI; M10/M33 share BTC risk |
| Sprint EOD-trailing | **M52, M42, M53** | 1/3 each | M52 **0.04578751**, M42 **0.11666667**, M53 **0.11666667** | ETH / BTC / SOL source turnover; avoids the M52/M56 co-directional HYPE exposure |
| Mandatory comparator, not selection | M52, M56, M10 | 1/3 each | M52 **0.04578751**, M56 **0.08416246**, M10 **0.09888257** | Published precomputed leader, but M52/M56 are short hold and overlap HYPE |

**Do not claim gamma1>+1, max DD<0.50%, 5 green days, target pass, optimal weights, funded EV or stop guarantees from these partial data.** Only full synchronized marked equity paths could validate those. Past paper/Phase7 reports have documented how tiny historical modeled DD can disappear under exact book and worse costs.

### Independently executed 1m/2m/5m Polars next-open batch diagnostics

Using the native `pm_ml4t_batch_recovery` isolated study with exact SQLite/cohort identity, supplemental raw-page SHA checks, native minute-open SHA/day verification, reference static `k_eff` and $10 minimum order, I reran each trio separately.

| Trio | Delay | Nonzero net batches | Native-priced and $10+ accepted *scenario orders* | One-side combined 6bps cost (USD) |
| --- | ---: | ---: | ---: | ---: |
| Explorer M10/M33/M53 | 1m | 414 | 408 | $376.47 |
| Explorer M10/M33/M53 | 2m | 374 | 369 | $373.56 |
| Explorer M10/M33/M53 | 5m | 326 | 321 | $372.64 |
| Sprint M52/M42/M53 | 1m | 491 | 477 | $834.40 |
| Sprint M52/M42/M53 | 2m | 448 | 437 | $818.22 |
| Sprint M52/M42/M53 | 5m | 410 | 400 | $764.04 |

For Explorer, missing COMP Oct 16/20 blocks two native market-days (3 batched orders at 5m); Sprint PONS Aug 31 has only 1,210/1,440 verified native bars (3 batched orders at 5m). The Sprint trio also has a greater turnover and one-way execution cost burden at 5m than Explorer. These numbers are *conditional historical oracle* orders with **no independent funding, L2 impact or source-equity-as-of**. They do **not** establish two complete PnL curves or a winner.

Private immutable Explorer report: `ml4t66_batch_audit_762c88375f39b7612c0c.json`, SHA-256 `762c88375f39b7612c0ce2815803f316dc5a82fd9a865febf7fe5bb3c3ca5530`.
Private immutable Sprint report: `ml4t66_batch_audit_7ee3b3e7fa55a85442ad.json`, SHA-256 `7ee3b3e7fa55a85442ad2862254bd3b0b4e93be86d0f213b90cf2903563501f0`.
Both reside in `/home/quant/.local/share/copytrade/reports/ml4t66-batch-recovery-20261105/`.

### Contract rule mismatch found and fixed in the isolated feature branch

The original B Sprint model accidentally set `challenge_eod=False` (ratcheting on intraday marks). The user-supplied rule requires EOD trailing, ratcheting at 00:00 UTC. `contract_actuary.CONTRACTS` now sets B `challenge_eod=True`, and `pm_contract_selector.RULES_VERSION` is bumped to `user_archetypes_20261105_unverified_v2`; the old synthetic Sprint figures remain historical **v1**, not corrected v2 outcomes. A correction-specific regression test pins the user rule. Funded 4% EOD / 2.5% daily is retained. Explorer 8% intraday evaluation / 5% daily / +10% and +5% phases unchanged.

## Accepted path to true portfolio selection

1. Use SQLite as unique roster/alias authority; source vendors remain original, SHA audited. Reconstruct **every** exact coin/DEX parent+subaccount position with unambiguous same-ms fill chains and independently observed *initial* book.
2. Obtain contemporaneous correct-scope source equity/NAV and first-local follower receipt timestamps. A current un-timestamped vendor equity scalar cannot serve as July/September per-fill NAV. All-DEX collateral and any HIP-3 hedge must be reconciled, not excluded for a flattering risk curve.
3. Build synchronized *per-wallet, per-minute* whole-book quantities and $10k follower simulated cash/inventory using source-equity weights. Run causal 1m/2m/5m first-event net-delta windows, then strictly next-open fills, 3.5bps taker+2.5bps adverse slippage each executed side; enforce $10 minimum, liquidity/impact, funding, risk netting and no lookahead. Missing active risk blocks affected portfolio/windows, never zero-fills.
4. Use PM-03 sequential equity/HWM/daily reset and pod control with the corrected **distinct** Explorer and Sprint rulebooks, including first-passage and funded protection. Use the native contract-selector only with its complete truthful synchronized net PnL tape; otherwise report `BLOCKED`.
5. Separate return/skew/PSR/daily-green-day/contract success, OOS and fee stress; account for the 20 precomputed ensembles and all other screened combinations as *multiple tests*. A candidate's retrospective PnL cannot be advertised as independently predictive alpha or authorized purchasing advice.

### Private outputs

- Audit V3: `/home/quant/.local/share/copytrade/reports/ml4t66-batch-recovery-20261105/ml4t66_precomputed_integrity_audit_20261105_v3.json`, SHA-256 `18ff5f59961aeff4b6db0223c9f36ba24315c73fd0404ac35a0b1fe8d7669750`.
- Source/market batch audit after recovered native data: `/home/quant/.local/share/copytrade/reports/ml4t66-batch-recovery-20261105/ml4t66_batch_audit_4f07c7e14eb45c83885b.json`, SHA-256 `4f07c7e14eb45c83885b9de2fd64d5bf4d5e5d8cbfaae3dfa8f16853c059e677`.
- New public raw generation: `/home/quant/.local/share/copytrade/reports/ml4t66-public-fills-g20261105-01/report.json`, SHA-256 `91ac6800ff1c5f5a2c587e717d774c71f92fefb0b200a1ba4c50baf47819a9f5`.

`NO_AUTHORIZED_PURCHASE_RECOMMENDATION`.
