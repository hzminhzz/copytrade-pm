# T+5-minute follower net-economics screen | 2026-11-08

**VERDICT: ZERO QUALIFIED WALLETS.** This is a completed retrospective historical-oracle **subset** replay. It is not realized follower PnL, first-known paper trading, scientific validation, a verified contract-pass probability or trading authorization.

## Authority and window

- Isolated worktree: /home/quant/dev/copytrade-0711, research/0711. Private SQLite read-only. No broker, production, original market files, source cache, or registry changed.
- Current SQLite: 502 wallet identities; 32 distinct owner exclusions; **470 non-excluded** assessed. Registry doctor's 284 research_unique is a narrower research cohort and not this full-table denominator.
- Local six-generation source inventory: 159 JSON files, 653,058 unique supported native fill IDs across 144 addresses; 119 current non-excluded wallets matched. Three more priority wallets were screened using separately recovered Vike full/tail fills. **348/470 lack a replayable immutable input**.
- User period: July 1 to November 8. Historical oracle cutoff is 2026-11-07T00:00:00Z exclusive because verified native 1m data inspected ran through November 6. Nov 7–8 are NOT priced or extrapolated.
- Native history: only observed flat-to-flat fill chains from original startPosition are replayed. Vike does not expose this native field, so its source position paths are retrospectively inferred by matching completed round trips to exact signed fills; this SELECTS on future completed episodes and is NOT a causal full-wallet book. Vendor future maximum trade size was excluded from the ranking.

## Execution model

Reuse native copytrade-pm.pm03_account, pm03_execution.CostModel, and the SHA-verified native 1m day validator. The first source change starts a wallet-wide five-minute window; ALL changes observed before the first minute open after T+5 collapse into one decision. One hypothetical market order per instrument per decision; exits also wait the five-minute window. Rejected entries are not converted to multi-minute fill fragments. Missing market days or bad SHA produce null full-path PnL, never a partial-result winner.

Research-only fixed-k: derive k before the test from the first 30 days' P90 of source gross notional, with a $2,000 typical target and k<=1. At each observed source change the follower target notional equals signed source native quantity × contemporaneous source fill price × frozen k; hypothetical follower quantity uses the verified decision-time 1m open. No future Vike maximum-size, current source NAV, or after-exit return is used for position sizing. For Vike fill-inferred episodes, the *choice of complete episodes itself remains ex post*.

Scenario account: $10,000 start; +$1,500 profit objective; $450 daily allowance; $1,000 trailing drawdown; $200 peak-to-trough pod-loss trigger; $3,000 pod gross and market caps. These are **unverified research contract assumptions**, NOT Propr rules. The pod stop triggers one-shot forced exit but cannot guarantee a $200 terminal bound.

Costs: 5 bps taker fee per side, 3 bps full spread, 5 bps slippage per side, 20 bps market impact at 100% of previous completed 1m traded base volume; new entries require <=5% participation. 1 bp/8h funding debit is fixed in all sensitivities. 2x/3x multiply execution costs only. Forced over-capacity or zero-volume exits are hypothetical and labeled unverified, not real executable order fills.

## Complete registry classification

| Classification | Wallet count |
| --- | ---: |
| No matching immutable local replay input | 348 |
| Insufficient 30-day pretest calibration | 102 |
| Too few complete followable episodes | 5 |
| Missing/bad SHA-verified market minute | 6 |
| Completed native selected-episode replay | 7 |
| Completed Vike-inferred selected-episode replay | 1 |
| Risk-stop terminated | 1 |
| **Total non-excluded SQLite identities** | **470** |

Six paths completed 1x, 2x and 3x without risk stop. **Zero** met the strict numerical subset screen (positive under all costs, >=80% selected local fill coverage, >=20 hypothetical orders, no forced non-executable exits, source fresh through Nov6). **Zero** reached the research +$1,500 target. None meets scientific qualification or live/paper admission.

## Ranked conditional PnL from the fully closed 1x/2x/3x paths

USD PnL per separate $10,000 single-pod research account. Ranking uses the minimum over 1x/2x/3x scenario only for paths without pod-stop termination; it does NOT mean entire wallet performance or copyability.

| Wallet | 1x net | 2x net | 3x net | Reconstructable fill coverage | Orders 1x | Fatal limitation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| **M58** | +137.72 | +124.46 | +111.19 | 3.66% | 9 | Source ends Oct29; only 9 simulated orders |
| **REG116** | +220.94 | +149.99 | +79.05 | 35.52% | 70 | Source ends Nov2; 7 over-capacity forced exits, 20 entry vetoes |
| **M04** | +51.95 | +47.32 | +42.68 | 1.75% | 15 | Sparse selected episodes; source ends Nov2 |
| M42 | +1.36 | -1.64 | -4.63 | 5.11% | 7 | Negative at higher costs |
| M57 | +2.29 | -1.79 | -5.88 | 2.51% | 14 | Negative at higher costs |
| M54 | -5.98 | -29.08 | -52.18 | 3.15% | 26 | Negative even at baseline |

This does not promote M58, REG116 or M04. Their sample coverage and orderability are not sufficient.

## Additional audited wallets

- REG179: 5,846 fully paged Vike fills, 2,900 selected exact inferred flat-to-flat fills (49.61%). Historical simulated follower net +$136.65 at 1x, +$0.48 at 2x, -$126.10 at 3x; pod stop at 3x. 1x already contains **66 unverified over-capacity exits, 4 zero-volume forced exits and 104 new-entry capacity vetoes**. Five-minute taker economics are not robust.
- M56: Native source subset simulated +$226.00 at 1x, +$202.61 at 2x, -$37.77 at 3x (stop). Selected fraction 5.39%, source ends Nov2. Its separate Vike recent maker share ~94.4%, but its rejection comes from actual cost stress and missing coverage, not maker share alone.
- REG267: 5,487 fully paged Vike fills; 5,470 inferred episode fills selected (99.69%). Full follower path **BLOCKED**: source LINK September 22 native Parquet has NATIVE_SOURCE_SHA_MISMATCH. Partial PnL is deliberately null in rankings.
- REG238: 12,635 Vike raw fills since ~September 22 (NOT full July history), 8,604 inferred fills selected. Full follower path **BLOCKED**: MORPHO Oct31 native day has 1,439 bars, not 1,440.
- M29: positive modeled terminal PnL under all 3 costs but a pod loss-stop, just 2 orders and only 0.79% local source-fill coverage. Excluded from a fast-pass ranking.
- W028 and other candidate portfolios: incomplete market marks and/or source paths. Historical leader profits cannot substitute full follower evidence.

Vike provided only **1,421 traded candles** for LINK Sep22 and **1,399** for MORPHO Oct31. No no-trade minute was turned into a fabricated executable quote; no original Parquet file replaced.

## Decisions

**Do not promote F01/F03/F04/F05 or add portfolios solely to reach 30.** Explore source and market repair for REG267; acquire complete non-maker-dependent selected-source books and market evidence for REG116 and REG179 before a fresh prospective T+5 paper trial. Do not treat a risk-stopped or missing-mark path as a ranked winner.

Actual claim requires authentic selected perp vectors, as-of local first-known signal receipts, independently fresh quotes and native quantity/lot checks, actual single market-order paper fills including exit, slippage, fee, funding and aggregate Guardian pod/gross/daily/trailing accounting. Owner contract remains unverified. Status: NO TRADE, zero scientific qualification.

## Reproduction and evidence

New scripts in isolated research branch:
- scripts/research_t5_native_source_20261108.py
- scripts/research_t5_vike_inferred_source_20261108.py
- scripts/research_t5_follower_oracle_20261108.py
- scripts/research_t5_rank_audit_20261108.py

Private 226-chunk source collection:
- /home/quant/.local/share/copytrade/reports/fastpass-july-nov-recovery-20261108/g-215dd6dc5ea146f393b4
- Collection SHA-256 215dd6dc5ea146f393b44bb98103e526efe620dc1ef11b1f995eaff8dbe7e402

Private pinned follower screen receipts:
- t5-native-all-r3.json (SHA-256 5f856f8c3a073a6aecaa2adb4cf3dbacd270ce7bb915818549fe84a136d96d73)
- t5-native-candidates-r3.json (SHA-256 db5c6ea782345a17c2acd77538e0f39e8d30b62b0f53fd0632d4bf9fbe6c8529)
- t5-vike-inferred-r3.json (SHA-256 ba65b1ba2e797a170097eddd87a4d42b6549f003815721ed4fb5b79ed469460b)
- Software SHA-256 5ef2b461d368410a572f6ab36af0a4de2c76b10c3d640e781b28807a1c978e5a

Final private 470-row table and manifest:
- t5-rankings-20261108-v3/wallet_rankings.csv
- t5-rankings-20261108-v3/receipt.json

Previously created private v1 and v2 artifacts remain in place for audit history. The native capability catalog currently has two unrelated global registration errors, so capability-wide validation is still BLOCKED independently of this focused research.
