# Decision: adopt Gemini Phase 3 paper-research directions; plan 180-day evidence extension

- **Recorded:** 2026-11-03 (Asia/Bangkok; 2026-11-02 UTC).
- **Authority:** user requested that the accepted parts of the Phase 3 logical review be saved **before** extending source data to 180 days.
- **Scope:** **research/paper decision only**, not live execution, not a change to the frozen historical cohorts, not scientific qualification, and not an instruction to backtest or fetch data now.
- **Status:** **DECISION RECORDED; 180-DAY DATA EXTENSION PLANNED, NOT STARTED**.
- **Binding original selection:** [2026-11-02 selected three-wallet decision](2026-11-02-gemini-selected-three-pod.md).
- **Previous suggestions kept intact:** [Phase 2 alternatives registry](2026-11-03-gemini-alternative-portfolios.md). The new P14/P15 identifiers below refer to **Phase 3**, not the Phase 2 P5 naming scheme.

## Approved decisions

| Phase 3 candidate / idea | Decision | Exact meaning |
| --- | --- | --- |
| **P1: selected 3-pod core** | **ADOPT — primary paper research** | Preserve `S035-ENA + S051-BTC + S053-HYPE`, $10,000 *virtual* challenge reference, **$600 combined nominal loss budget**, $200/pod. First priority for prospective read-only capture and separate paper accounting. |
| **P14: 5-pod, equal-total-risk** | **ADOPT AS EXPERIMENT — shadow challenger, not promoted** | Preserve the **same** $600 total nominal budget over five pods ($120/pod): the P1 trio **plus** `S064-xyz:BRENTOIL` and `Whale_0x5f94`. Compare at *equal total risk*; never auto-substitute for P1. |
| **P16: four-pod core + whale** | **OPTIONAL RESEARCH CONTROL** | `S035-ENA + S051-BTC + S053-HYPE + Whale_0x5f94`. Gemini proposed modeled 30% / 30% / 25% / 15% risk allocations at $600 total. Useful to isolate whale contribution without S064 exposure; not an active deployment roster. |
| **P15: five-pod higher-risk variant** | **DEFER** | Same five identities as P14, but $1,000 combined nominal risk ($200/pod). Gemini's higher modeled gross PnL and pass rate largely reflect 1.667x scaling; **do not promote or increase risk** from those claims. |
| **S059-HYPE and Whale_0x5f94** | **EXPERIMENT — candidate discovery** | Preserve for 180-day review of identity, historical continuity, whole-book hedge coverage, costs, and dependence. They are **not** replacements for any P1 manager without a new decision. |
| **Wallet identity, episode-level economics, true MTM and dependence/clone deduplication** | **ADOPT AS EVALUATION METHODS** | Assess source-versus-follower replication gap, joint directional exposure, adverse/underwater additions, effective independent episodes, follower costs and cross-wallet co-loss. One controller per economically dependent wallet cluster, not one independent vote per address. |
| **Phase 3 fixed `k` multipliers** | **REFERENCE ONLY; RECONCILE, DO NOT DEPLOY** | Preserve as Gemini modeled assumptions, not live quantities or a replacement for the repository's **source-equity-relative whole-book sizing** and PM03/PM04 authority. |
| **Stage-2 ML meta-labeler / blanket underwater-addition veto** | **DO NOT ADOPT** | Gemini's own modeled validation showed negative mean net trade edge, and skipping scale-in tranches may break multi-day managers' strategy. Clone deduplication/structural ranking may still be evaluated separately. |
| **Forecast 77%–81% challenge pass frequencies; 13x Calmar values** | **UNVERIFIED CLAIMS** | Never advertise as real pass probabilities or qualified/annualized performance. Reported `Calmar` is essentially full-period PnL / period maximum DD, not necessarily conventional annualized Calmar. |

## Exact paper portfolio definitions

### Primary P1 — selected, three managers

| Manager | Gemini Phase 3 illustrative fixed `k` on $10k | Nominal risk budget |
| --- | ---: | ---: |
| `S035-ENA` | `0.0282x` | $200 |
| `S051-BTC` | `0.0430x` | $200 |
| `S053-HYPE` | `0.0296x` | $200 |

- Gemini reported **+$3,294.67** net, **−$242.99** maximum drawdown, return/DD **13.56x**, and **77.4%** rolling challenge success under its stricter stop simulation. **MODELED, NOT VERIFIED.**
- Its Phase 2 stop variant reported +$3,521.30, −$384.20 max DD and 80.3% rolling pass frequency. **Do not merge stop rules across those two configurations.**
- The exact selected roster was already approved and documented on 2026-11-02. This document **does not reselect, reweight, or deploy** it.

### Challenger P14 — same $600 nominal risk, five managers

| Manager | Gemini Phase 3 illustrative fixed `k` on $10k | Nominal risk budget |
| --- | ---: | ---: |
| `S035-ENA` | `0.0169x` | $120 |
| `S051-BTC` | `0.0258x` | $120 |
| `S053-HYPE` | `0.0178x` | $120 |
| `S064-xyz:BRENTOIL` (Gemini calls it `S064-BRENT`) | `0.0191x` | $120 |
| `Whale_0x5f94` (full address privately resolved) | `0.00011x` | $120 |

- Gemini reported **+$2,832.54** net, **−$214.66** max DD, return/DD **13.20x**, and **74.2%** rolling pass frequency. **MODELED, NOT VERIFIED.**
- Relative to P1 at *equal* $600 risk, modeled maximum DD improved only **$28.33**, while modeled validation net PnL declined about **$472.65**. The case for P14 is a **falsifiable diversification hypothesis**, not an established upgrade.
- The label `S064-BRENT` does not mean BRENT-only: Gemini reports other significant exposures, including TAO. Confirm the full all-DEX source book and Propr's actual executable universe. There is **no authorization to silently drop untradeable source hedges**.
- Gemini's whale `0x5f94` had only **10 closed episodes** and an approximately 28-day median hold in its reported sample. Its reported peer-adjusted markout decreased markedly from training to validation. Large fill count/markout alone does not prove stable independent alpha.
- P14 and P1 use **separate virtual account ledgers**, even if an observation service is shared. Two virtual portfolios must not generate duplicate orders on the same demo/funded account.

### Optional P16 control

- Same core three + `Whale_0x5f94`, without `S064-xyz:BRENTOIL`.
- Gemini's 30% / 30% / 25% / 15% modeled risk shares correspond to $180 / $180 / $150 / $90 of the $600 *nominal* budget, **not** guaranteed stops, collateral or automatic order sizes.
- Reported modeled +$3,156 net and −$268 max DD. Evaluate only if it helps separate whale diversification from S064 instrument coverage.

## What Phase 3 did **not** prove

1. **Selection bias / reused validation:** the primary trio and new candidate screens have already been selected after inspecting August–November outcomes. Calling September–November an OOS window does not make it untouched for the **final selected** portfolios. New research must freeze candidates and parameters before inspecting its next confirmation period.
2. **Weak effective sample:** Gemini's 62 overlapping 30-day challenge windows were estimated to have only `N_eff≈5.2–5.8`; differences between 74.2%, 77.4%, and 80.6% modeled pass frequencies are not reliable rankings.
3. **Source dataset discrepancies:** the Phase 3 PDF reports 244,775 fills/24 training-observable wallets; the supplied leaderboard totals 290,467 `fills_90d` and flags 22 `train_obs=True` (with another training-observed but ineligible entry). The additional filtering may be legitimate but needs a versioned count bridge. Do not silently treat either total as established.
4. **Follower execution:** hindsight source fill clocks are not prospective first-known receipts, fill-tape/interpolated market prices are not executable market depth, and a historical nominal $120/$200 pod stop is **not** a worst-case loss guarantee. Costs, funding, gap risk, 1-minute quote coverage and Propr instrument mapping remain separate validation gates.
5. **Trader-identity significance:** Gemini's 200 shuffled-identity permutations and `p<0.005` claim do not account for every portfolio/parameter and prior-Phase search. Trader identity is a useful **research feature**, not proven future alpha.
6. **Meta-labeling:** Phase 3 itself reports Model 5A at −33.59 bps and Model 5B at −47.26 bps validation edge; no approval for an additional trade filter or overridden direction/quantity targets.

## Next research phase: extend **to 180 days** (USER-PLANNED; NOT EXECUTED)

The user intends to gather **180 days of relevant data** for the approved P1/P14 candidates **after** saving this decision. No additional data was acquired, no fresh replay was run, and no engineering or trading qualification is claimed by this document.

### Priorities and immutable input contract

1. **Freeze now:** selected P1, P14, optional P16, key research questions, causal 300-second execution rule, account size and **equal-$600 nominal-risk comparison**. Define the 180-day start/end timestamps in UTC, exclusions, training/validation/untouched confirmation split, and output manifest **before** running the next comparison.
2. **Acquire versioned 180-day source fills** for `S035`, `S051`, `S053`, `S064`, `0x5f94` (optionally `S059`), using user-approved historical **HyperX** fill acquisition. Keep raw pages/private identity maps and SHA-256 chain outside Git. Respect rate limits; extend farther back when necessary to establish initial inventory cost basis and account/subaccount continuity.
3. **Audit completeness and point-in-time limitations:** full parent/subaccount/all-DEX book, signed inventory, deposits/transfers/funding, source NAV/equity, deduplication, partial fills, event-time vs local first-known time, opening positions and horizon censoring. Unknown historical NAV or off-venue hedge means **BLOCKED** economic fidelity, not zero positions.
4. **Verify market and follower economics:** native 1-minute OHLCV and funding coverage, Propr-specific tradable instruments, independent marks, realistic taker/spread/impact/capacity and fee stress. Source-only 180-day extension does **not** create historical first-known receipts; run retrospective oracle research under that label, and separately log prospective decisions and execution.
5. **Compare matched P1 / P14 / optional P16** with identical market windows, virtual $10k ledgers, account daily/trailing rules, 1x/2x/3x costs, exposure/tracking and gross-net risk. Report train/validation/untouched-window performance by segment, per-wallet contribution, pairwise **joint drawdown** and crisis co-loss. Consider P15 only as a **non-selected leverage sensitivity**, not a new risk allocation.
6. **Measure whale specialization and durability:** source/account continuity over 180 days, independent position episodes (not raw fill count), 28-day-scale exposure, concentration, correlation during down markets, executionability of whale and S064 markets, and whether P14's DD benefit exceeds noise/complexity. A new wallet address or owner migration requires a documented identity chain, not blanket stitching.
7. **Do not re-optimize then call the same data independent.** Historical pre-existing Phase 2/3 look windows are already consumed for selection. If the 180-day interval overlaps them, the overlapping portion remains exploratory. Reserve a genuinely new time interval or collect forward paper results for confirmation. Nothing in the 180-day expansion automatically validates live following.

### Promotion / stopping rule

- **Proceed with P1 paper observation first**, keeping its $600 combined nominal research budget. Investigate failures rather than automatically reallocating to P14.
- **Keep P14 as a challenger** unless its diversification survives equal-risk, independent later windows and actual follower economics, including source completeness and operating cost. The modeled $28.33 DD advantage alone is insufficient to replace P1.
- **P15 stays deferred**: an increased total risk budget cannot be justified by higher modeled profit or a few-point reported pass-frequency gap.
- Move from retrospective hypothesis to scientific qualification **only** with independent, prospectively observed follower evidence, verified account rules and operator approval; trading on a demo/funded account is a separate governed action. No service or broker change is authorized here.

## References and continuity

- **Phase 3 attachments supplied in this chat:** `Hyperliquid_Phase3_Academic_Wallet_Discovery_and_Portfolio_Report.pdf`, `Phase3_Portfolio_Comparison.csv`, `Phase3_Complete_Wallet_Leaderboard.csv`, `Phase3_Wallet_Exclusion_Registry.csv`, and `Pasted text(20261102-173843).txt` (source claims and secondary analysis; do not assert they have been checked into Git or captured with source hashes).
- [Original selected roster](2026-11-02-gemini-selected-three-pod.md); [earlier Phase 2 alternatives](2026-11-03-gemini-alternative-portfolios.md).
- [Equity-normalized follower sizing](../EQUITY-WEIGHT-SIZING.md), [Research qualification gates](../QUALIFICATION.md), and [Private data acquisition](../DATA-ACQUISITION.md).
- [Phase 2 94-wallet exploratory PM03 replay — PR #25](https://github.com/hzminhzz/copytrade-pm/pull/25).
