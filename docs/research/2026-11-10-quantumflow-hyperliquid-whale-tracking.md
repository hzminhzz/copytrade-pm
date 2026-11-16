# Research audit — QuantumFlow Hyperliquid whale-tracking study and Copytrade-PM

**Date:** 2026-11-10
**Status at research review:** EXTERNAL RESEARCH ASSESSMENT — not a reproduced experiment, wallet-performance finding, application implementation, scientific qualification, or trading authorization. Q16 **was OPEN at the time of review**.
**Subsequent owner decision (2026-11-10):** The proposed economic acceptance gate and independently reversible Q16 delivery were **APPROVED** in the [design-closure ADR](../decisions/2026-11-10-source-wallet-health-k-recalibration-design-closure.md). This does **not** independently verify the article's empirical claims or authorize implementation.
**Article:** https://quantumflow.tech/learn/hyperliquid-whale-tracking/ — Dom / QuantumFlow, **6 November 2026**, full text retrieved and read on 10 November 2026.
**Repo context:** isolated `copytrade-pm` worktree from `6c07cc6d36099135881be27a072c426a52a24f24`, existing [Q1–Q15 approved design](../SOURCE-WALLET-HEALTH-K-GRILL-20261109.md), [Pydantic source contracts](../../src/copytrade_pm/pm_source_contracts.py), [risk-budgeted fixed-k policy](../RISK-BUDGETED-K-SIZING-20261106.md), [16-portfolio SHADOW evidence](../PYDNATIVE-V4-SIXTEEN-SHADOW-20261109.md).
**Independent verification ceiling:** The page itself, its disclosed methodology/limitations, published Hyperliquid official WS and fee docs, and current repository code were inspected. QuantumFlow's original 2.48B-fill raw dataset, analysis code, exchange fee-per-fill, funding history and broker counterparties **were not made available here**, so numerical results are **author-reported, not reproduced**.

## Thesis: observation != copyability != source skill != executable follower alpha

The study's result is a **negative-control benchmark** against the idea that visible size, leaderboard profit or even persistent gross profit is enough to justify follower risk. It is **not** a proof that a specifically selected slow-position pod under current official first-known T+300, costs, selected DEX scope and fixed-k risk is unprofitable. Its own copy test instead reconstructs main-market fills, delays a minute or an hour, simulates a month-by-month top-100 roster, excludes very high-fill accounts, and does not include funding, slippage or market impact.

An observed account has several distinct possible facts:
1. **Observed**: account and official selected-scope economic position are authentic, complete and durably first-known. Source continuation, network health and contract validation are not profit.
2. **Eligible**: specific wallet meets independently supported freshness, activity, identity, capital-floor and eligibility criteria. Transfer/outflow information is not edge.
3. **Economically copyable**: its observed, selected-scope position policy can be reproduced **after T+300 at follower prices and with executable costs/capacity**, not just that the leader was profitable.
4. **Persistent predictive quality**: net follower payoff survives PIT selection, next-period data, market regime changes and the number of search variants.
5. **Portfolio contribution**: incremental portfolio-level net economics remains positive after pod-risk, correlation, concentration and challenge drawdown. `k` scales risk; it does not create a missing source of edge.

**Candidate domain term (NOT YET APPROVED as glossary):** `Copyability` = evidence that a specified source strategy, observed with its actual first-known timing and followed under a specified execution-cost / delay / risk contract, is economically executable and positive *for the follower*. It is separate from source eligibility, raw leader skill and mathematical fixed-k correctness.

## Findings and quantitative caveats (all author-reported)

- Archive: 2,482,884,183 **wallet-side** fills; 1,075,312 addresses; main Hyperliquid perpetual market 2025-07-28 to 2026-11-03. One trade creates two wallet-side fills. Ten selected liquid coins for most directional tests, not HIP-3 and the entire selected market universe.
- Whale long/short bias: for $5M+ open-position wallets, extreme net positioning offered -11.9 bp relative 24h return, reported 95% interval **[-56.8,+32.4]**; no directional evidence. $5M+ group net short HYPE 97.9% of hours. Off-market hedging possible but unobserved.
- Leaderboard past-profit top-100 copier: **-$13.6%** in 14 modeled forward months (Sep 2025–Oct 2026), with 1m delay and 4.5 bp fee per execution, before funding/slippage/impact; the first and second samples were materially different. Tested 72 variants; no tested rule beat cash and coin basket in both halves after multiplicity assessment.
- Top-100 membership turnover: avg **26.5 of 100** remain next month; **15.1** remain three months later. New/young wallets in selected top-100 had worse subsequent mean source gross profit than veterans. Do not use this as a universal negative age prior without independent research.
- Stability predicts being a *gross-profitable wallet* more than raw profit ranking: top-decile next-month gross profitable 47.7% vs 35.3% comparison; **last eight months -16.5 bp of next-month volume**, before costs. A better hit-rate classifier is not a profitable follower strategy.
- Leader fill markout: top set +2.3 bp one-hour **gross directional** move in a later sample; one-minute-delayed markout +1.0 bp and reported uncertainty spanning zero. Markout is **not** a complete position-lifecycle follower net PnL. The paper acknowledges a full-panel eligibility screen and thus not a clean prospective OOS test.
- Large new positions ($500k+): one-hour conditional price response +0.6 bp with interval [-0.6,+2.3]; size alone is not a useful new-risk prompt. First-seen >$2M entries had -18.1 bp relative 24h move, but the authors explicitly did **not** test costed follower returns for fading them.
- Liquidations: next-hour same-side $1M+ long liquidation 24.6% vs 7.7% matched hours. Stricter later-half comparisons weaken and directional returns do not support a robust trade. Treat as a **hypothesis for volatility/liquidity-risk diagnostics**, not automatic direction or sign.
- Statistical selection: among 19,897 wallets with three or more scored months, 439 passed individual 5% tests; **none survived the authors' multiple-testing correction**. A favorable 7d wallet or a historic ten-month winning streak is not automatically qualified alpha.
- Other signals: crowded-retail fade looked compelling but was strongest among 36 tested variants; shifted-signal test `p=0.21`, multiplicity-adjusted interval included zero, and BTC effect was absent.

## Methodological strengths and weaknesses

**Strengths:** large main-market panel, historical as-of monthly roster for copier, multiple time horizons, cash and matched-coin benchmarks, cross-regime splits, blocked calendar-time bootstrap and some explicit multiple-testing controls, fees in copy simulation, distinction between price markout vs actual copied PnL, explicit disclosure of limitations and negative results.

**Limits:** proprietary unreproduced raw evidence/code; gross per-wallet PnL before fee/funding; missing maker/taker role and actual fee tier; incomplete spot/HIP-3/off-platform hedging; market-size groups based on marked position not trader capital; reconstruction from historical fills rather than exact official position first-known receipts; copy model cannot be directly transplanted to a **5m** delayed official-state follower; simulated copy ignored funding, price impact and slippage, and portfolio sizing assumptions are not identical to frozen PM03/04 k; some exploratory screens used complete future-sample eligibility; many comparisons not exhaustively registered. Nulls from a broad population do **not** falsify all pre-registered conditional sub-strategies, but materially raise the prior burden of proof.

**Primary sanity check:** Hyperliquid official fees list base perp taker 4.5bp, maker 1.5bp, volume tiers and other modifiers, not a universal real fee for every wallet; source WS `allDexsClearinghouseState` provides selected-account position evidence. Current copytrade-pm `pm_forward_observed_paper._costs()` specifies **5bp fees + 2bp slippage per side** as paper-study assumptions, `full_spread_bps=0` and `impact_bps_at_full_participation=0`; a symmetric full entry-exit would therefore model about **14bp round-trip** before funding, variable spread and market impact, not 9bp. This is a code-stated scenario, NOT a measured installed broker schedule. A hypothetical +2.3bp 1h *markout* cannot pay this simple round-trip by itself, but is not the same as full multi-hour position PnL.

## Implications for approved decisions (research recommendations, NOT approvals)

| Approved area | What stays | What to add as explicit *proposed evidence work* |
| --- | --- | --- |
| Q1/Q4/Q5/Q10 source continuity | Fix SQLite producer and per-account GAPs under systemd | Do not let an economically weak source wallet invalidate engineering source-writer acceptance. Correct transport is a precondition for prospective economics, not proof of edge. |
| Q2/Q6/Q7/Q8/Q11 wallet health | Date-scoped eligibility/attribution vs quality, source NAV optional | Quality should include a separately labeled **follower copyability/net** view, evidence maturity and source-observed behavioral age; avoid auto-selecting recent top-PnL wallets or equating inactivity with bankruptcy. |
| Q3/Q9/Q12/Q13 k recalibration | Per-pod, per-portfolio versioned k, risk-budgeted, no automatic increase | **Gate k increases** on OOS cost-adjusted follower net payoff, trial-count-aware selection, delay/cost stress and positive *marginal portfolio contribution*; k selection must not optimize past winners without holdout. |
| Q14 Grafana | Separate operational/economic authority fields | Display `source valid` and `follower economics qualified` independently; an all-green source/run card must not be interpreted as copy alpha. |
| Q15 Prefect | Scheduled read-only wallet checks and proposal generation only | Automate inexpensive multi-horizon as-of outcomes, candidate-attribution reports, exposure/copyability diagnostics, regime monitoring and proposal diffs; no Prefect tasks in T+300 critical path. |
| Q16 release frontier (OPEN) | Three separately reversible workstreams | Add a **separate economic null-evidence gate** to wallet quality/k proposals (not a blocker for source reliability): cash/no-trade baseline, fixed cohort vs random/matched cohort, price-momentum/coin basket benchmark as appropriate, multiplicity log, frozen OOS/forward, stress at 5m + additional 1m and adverse slippage. |

## High-ROI executable research protocol (to specify, NOT run here)

1. **Freeze candidate selection** by registry-version, timestamp and first-known candidate provenance; retain rejected and attempted wallet/portfolio combinations, not just final winners. Do not choose the testing window after seeing performance.
2. **Fast Polars screen** for every candidate on historically reconstructable position-change episodes: available book/market coverage, exposure, hold duration vs 5m delay, turnover, estimated follower costs and crude net. Allow maker-heavy wallets to compete if their **position-change policy** is copyable; fill count by itself is a poor rejection proxy.
3. **Strong candidates only** go to actual PM03/04 execution-cost and challenge-risk evaluation: baseline entry at first eligible 1m price after T+300, one extra minute, and adverse slippage; original first-known receipts where available; retrospective first-known unknown labeled **ESTIMATED**; include immediate source reductions and exits, funding when verifiable, proper incomplete outcomes.
4. **Negative controls:** cash/no trade; coin/market beta or matched-coin basket; candidate-selection random/matched baseline with the same turnover/cost; record all tested ranking/portfolio/k variants. A strategy should be better after costs and risk than the relevant alternatives, not merely profitable in a trending market.
5. **Evidence separation:** historical reconstructed trials are screening only; frozen subsequent OOS and authentic forward receiver/journal episodes are distinct verdicts. Check split-by-regime and contribution to portfolio correlation/risk; insufficient data means **UNCERTAIN, no k amplification**, not a universal zero-alpha verdict.
6. **Output contract:** `source_integrity`, `wallet_eligibility`, `copyability`, `edge_persistence`, `marginal_portfolio_value`, `research_evidence_class`, `k_proposal`. Each attaches as-of/data/window/trial-count and cost-policy provenance; research statuses are not permits.

**High-level falsifiable thesis:** Selected slower, sufficiently active individual wallets may still deliver positive **post-T+300 follower** economics even when aggregate whale positioning, generic leaderboard selection and short-horizon markouts do not. Test the conditioned selected cohort, not the broad null only; no alpha until genuine OOS/forward evidence survives costs and alternate pricing assumptions.

## Decision status and next frontier

Do **not** reopen Q1–Q15 or authorize deployment based on this article alone. It supports the existing architecture and suggests a *narrow Q16 economic-evidence addendum*, specifically to wallet-health and k-recalibration acceptance. Source-writer reliability remains independently releasable.

Q16 is open: request owner approval for (a) independently reversible delivery and (b) an additional low-cost, test-trial-aware **economic replicability** acceptance boundary for wallet selection and positive k recommendations. No implementation, commit, merge or deployment.
