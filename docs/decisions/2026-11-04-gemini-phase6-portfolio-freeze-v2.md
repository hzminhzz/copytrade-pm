# Portfolio Freeze V2 — Gemini Phase 6A selection update

**Decision:** 2026-11-04 (Asia/Bangkok). **Owner approval:** user expressly approved replacing the research priority list after comparing Gemini Phase 6A to the saved P1/P14 decisions.

**Scope:** new **forward-paper RESEARCH selection only**. This is a dated successor selection, not a mutation of existing immutable historical portfolios, currently running research services, prospective P1/P14 trial records, Propr terms, or any real/automated order roster. **No science qualification or funded/live authority.** Machine-readable matching source: [the frozen v2 research selection manifest](2026-11-04-gemini-phase6-portfolio-freeze-v2.json).

## Current priority, effective for new paper campaigns only

| Order | Candidate | Frozen membership (canonical aliases) | Research disposition |
| --- | --- | --- | --- |
| **1** | **E6 / Phase 4** | **ACT04, S053-HYPE (W083), S051-BTC (W080), CM-002, Whale_0x5f94** | **NEW PRIMARY**: 5-pod, equal nominal total risk ($600) |
| **2** | **E2 / Phase 4** | **ACT04, S053-HYPE (W083), S051-BTC (W080)** | **NEW THREE-POD CHALLENGER**: equal $600 total risk |
| 3 | P1 / former primary | S035-ENA (W016), S051-BTC (W080), S053-HYPE (W083) | **INCUMBENT BASELINE**, no automatic removal from independently frozen P1/P14 studies |
| — | P14 / former five-pod challenger | P1 trio, S064-BRENTOIL (W100), Whale_0x5f94 | **ARCHIVED from active selection priority**, retains exact original definition |
| 4 | E3 | ACT04, S053-HYPE (W083), CM-002 | **RESERVE** conditional three-pod experiment; exact Phase 6A k values not frozen here |
| 5 | Phase 5 B (1×) | N01, N07, N02, N05, ACT08 | **SEPARATE COMPARISON** in PR #74; do not auto-substitute into current paper worker |
| — | P16; P15 | Preserved under Phase 3 decision | Optional old control; higher-$1,000-risk P15 remains **DEFERRED** |

### Wallet identity reconciliation

The owner's VPS-only Phase 4 source roster and historical CSV export identify (the large raw CSV exports are untracked; they are **not published by this decision**):

- `W083` and `S053-HYPE` as the same on-chain wallet (not independent pods).
- `W080` and `S051-BTC` as the same wallet.
- `W016` and `S035-ENA` as the same wallet.
- `W100` and `S064-xyz:BRENTOIL` as the same wallet, notwithstanding other traded instruments.
- The **specific Gemini Phase 3/4 `HL Perps Whale`** as `Whale_0x5f94` in `docs/HL108_TOP25_WALLETS_FILLS_FOR_GEMINI.csv`. Other Nansen records reuse the generic label **HL Perps Whale for distinct addresses**. Match the authoritative private address and raw source SHA before admitting this whale; **do not choose a whale by display label alone**.

Do not commit wallet account keys or full private identity maps. Any change of parent/subaccount or source-account scope requires a new versioned decision.

## Freeze the experiment identity, not its simulated alpha

Gemini's 2026-11-04 Phase 6A extension PDF reported:

| Reported Phase 6A P2 result | P1 (legacy) | E2 | P14 (legacy) | E6 |
| --- | ---: | ---: | ---: | ---: |
| Net return, **simulated** | +22.24% | +18.92% | +15.77% | +14.76% |
| Max daily DD | 2.42% | 2.42% | 1.98% | 1.48% |
| Max trailing DD | 6.81% | 4.31% | 4.06% | 2.73% |
| P0 trailing DD without pod stops | 12.40% | 11.15% | 9.83% | 7.70% |
| Worst five-day cluster DD | 9.90% | 7.64% | 7.13% | 5.43% |

**These are Gemini-modeled historical outputs, not verified real follower PnL, trading probability or genuine out-of-sample qualification.** E6 is preferred for downside robustness, not maximum modeled return. E6 and E2 overlap on **three of E6's five wallets**, so they cannot be counted as independent trials or silently trade together on one account.

The source report's **illustrative** risk-scaled 10k `k` coefficients are frozen as research references only:

| Manager | E6 (5 pod, $120 nominal/pod) | E2 (3 pod, $200 nominal/pod) |
| --- | ---: | ---: |
| ACT04 | 0.00257 | 0.00428 |
| W083 / S053-HYPE | 0.02825 | 0.04708 |
| W080 / S051-BTC | 0.02908 | 0.04847 |
| CM-002 | 0.00231 | — |
| Whale_0x5f94 | 0.00029 | — |

These are Gemini's first-45-day `frozen_train` historical model multipliers. **Do not use them directly as future follower order sizing.** Actual copy sizing remains **source-equity-relative and whole-book-faithful**, with complete account/DEX, source capital and receipts validated at each causal decision. A 90-day return including a training/calibration period is not an untouched 90-day OOS result.

## P2_flatten — target safety policy for new paper study

- Five pods: source-report aggregate $600 nominal risk calibration ($120 per pod), **$60 daily simulated MTM flatten threshold per pod**.
- Three pods: same $600 aggregate ($200 per pod), **$100 daily simulated MTM flatten threshold per pod**.
- Independently proposed account supervisor: $350 daily soft freeze, $450 daily hard flatten, 8.5% trailing hard flatten for a **hypothetical $10k account**. These are **provisional research terms**, not confirmed Propr contractual limits or an implemented broker policy.
- The Phase 6A comparison exported identical P1_flatten/P2_flatten results for all 10 configurations; **incremental account-supervisor benefit was not independently proven**. Paper testing must exercise actual account-level daily and trailing breaches, latch/restarts, stale receipts, partial fills, gap/slippage and kill-switch outages.
- The separate Phase 6A report contains unresolved 0.35× vs 1.5× concentration-cap text. **Do not select either limit** by implication, or silently enable account hard stops from this file.

## Preservation / compatibility

1. [P1 original owner decision](2026-11-02-gemini-selected-three-pod.md) remains the exact primary **of its historical version**. [Phase 3 P1/P14 adoption and 180-day research plan](2026-11-03-gemini-phase3-adoption-180d.md) remains immutable as prior intent, not overwritten. Phase 2 alternative sets remain archived.
2. The Trader Intelligence [P1/P14 proposed future study](../TRADER-INTELLIGENCE-PROSPECTIVE-STUDY-20261103.md) and existing FP-01..FP-15 (especially FP-09/FP-10) may already reference P1/P14. This V2 file **does not rewrite a registered study or mutate the running FP worker**. Existing comparisons continue as labeled until a separately versioned and future-dated E6/E2 campaign is registered.
3. Frozen PM-01 36-wallet cohort, historical A/B/C, Combo 2, original private Gemini Phase 5 manifests and PR #74 research evidence remain separate. No archive deletion or migration of production services.
4. Before starting new E6/E2 paper accounts: resolve canonical private addresses (including the duplicated whale display label), verify parent/subaccount/all-DEX scope, complete source equity/positions, supported venue symbols, future first-local receipts and trustworthy market/funding evidence. Register a **future** start and independent virtual ledgers. Unknowns mean NO TRADE, not assumed zero.
5. Retain **E6 and E2 as two different virtual ledgers** with identical observation windows, identical genuine costs and $600 nominal total risk, at least one independent future holdout and full disclosure of search/selection multiplicity. Do not claim a live/funded pass from this Gemini report.

## Change authority and completion interpretation

**SELECTED / RECORDED:** The user approved the *new research preference*. **NOT ACTIVATED:** No WR private SQLite admission, FP-09 runtime config, broker adapter, production tracker, Telegram copytrade service or funded account is changed here. A later **separate protected registry/activation decision** must satisfy [governance](../GOVERNANCE-GATES.md), [qualification](../QUALIFICATION.md) and independent review requirements before replacing a registered or running study.

Sources: user-supplied `Hyperliquid_Phase6A_Phase3_and_Phase4_Portfolio_Survival_Report_20261104.pdf` (historical conditional simulation), owner-approved comparison in this conversation, existing **owner-private VPS research exports** `PHASE4_PROPR_SIMULATION_RESULTS_108_WALLETS_20261103.csv` and `HL108_TOP25_WALLETS_FILLS_FOR_GEMINI.csv` (untracked; not distributed in Git), and prior dated [Phase 3 adoption decision](2026-11-03-gemini-phase3-adoption-180d.md). No new fills or backtests were run as a prerequisite for this selection update.
