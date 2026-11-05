# Barbell vs defensive $10k challenge — ML4T-66 historical research (2026-11-05)

**Verdict: EXPLORATORY ONLY; no qualified winner, no recommended contract purchase, no authorized trading, and no operating paper portfolio.**

## Scope and authority

- Source: owner-private **SQLite authority**, v8 registry doctor verified on 2026-11-05; 214 unique indexed research wallets, including the SHA-pinned 66-wallet `ml4t-strict-66` cohort (source SHA `92c96f9b8131404545ea2a1bc10045e476fb9f87ccc766060f44b60827daf528`).
- The bounded first scan considered 27 cohort wallets with usable static source equity and native-price checks; the initial barbell matrix used **8 wallets**: anchors M22, H34, M55, M51 and runner-slot candidates H36, M40, M50, M58. This is not a full optimized search of the entire 214-wallet registry, and missing initial evidence is **not** treated as a losing wallet.
- Study: 2026-08-05 00:00 UTC through 2026-11-03 00:00 UTC (exclusive), retrospective source-fill event timestamps, observed first-zero per source coin, zero-initial-position *hypothetical* follower, native SHA-verified Hyperliquid 1m OHLCV/next-open, first-event anchored 2m or 5m batches, lot minimum $10.
- Costs: 3.5 bps taker + 2.5 bps slippage per side at base (6 bps); stressed total **12 and 18 bps per side**, including commissions. **Funding, quote-side liquidity/depth, impact, real first-known receipt delays and liquidation are unknown.**
- Scenario rule **user-supplied, unverified for any specific contract**: initial $10,000, 5% daily drawdown, 10% continuous trailing drawdown and +10% single-stage target; 00:00 UTC daily reset. The daily floor uses the higher of close-based intraday HWM and day-start equity; the trailing floor uses close-based equity HWM. 1m simultaneous low/high adverse marks are checked **before** a same-minute target. An intraminute favorable equity HWM is *not* available: actual prop compliance is not certified.
- Static `k` uses true source-event **quantity** rescaling but owner-private, **untimestamped** source-equity scalars; neither complete leader NAV/subaccount opening book nor first-known follower signal is attested. This **cannot** establish faithful whole-account copying.

## Sizing protocol

Initial 45 observed calendar days serve as **retrospective risk calibration**. Each anchor receives a nominal $200 lifetime/$120 daily limit; the runner has $150 lifetime/$100 daily; $50 of the $600 allocation is unassigned. Each pod also loses $20 in sizing headroom and receives a 1.5x stress factor:

\[
k_i=\min\left(k_{base,i},
 k_{base,i}\frac{B_{daily,i}-20}{1.5 A_{daily,i}},
 k_{base,i}\frac{B_{life,i}-20}{1.5 A_{MDD,i}}\right)
\]

Here `A` is the modeled follower adverse loss **at** `k_base`, not the actual leader account risk. This algebra is valid as a calibration heuristic only; minimum-order discontinuities require re-running the full priced inventory at each `k`. A first-45-day calibration does not make the 90-day P&L out of sample. Candidate selection was informed by the whole retrospective period.

A separate *adversarial* co-crash screen aligns every member's historical worst single day despite its actual date and multiplies their summed, k-scaled losses by 1.5. Internal research ceiling: **$400**, below the $500 contractual daily floor. This is a hypothetical common-shock stress, **not** an observed joint crisis day or a guaranteed loss bound.

## Selected 5m / 6 bps comparisons

| Research policy | k factors (in listed order) | Retrospective first-passage | Co-worst 1.5x stress | Key defect |
| --- | --- | --- | ---: | --- |
| 3 anchors H34/M55/M51 | 0.001468293 / 0.010867422 / 0.009785729 | Modeled target **Sep 27** | $642.76 | Breaches proposed $400 stress; at 12 bps the target follows an unmanaged pod-stop trigger |
| Barbell H34/M51/**H36** | 0.001468293 / 0.009785729 / 0.006698076 | Modeled target **Sep 25** | $636.61 | Stress **exceeds even $500**; cannot admit unchanged |
| Barbell M22/H34/**H36** | 0.010975858 / 0.001468293 / 0.006698076 | Modeled target **Sep 21** | $293.85 | Resized book loses price continuity **Sep 22**, still no complete source book/PIT NAV |
| Barbell H34/M55/**H36** | 0.001468293 / 0.010867422 / 0.006698076 | **No target** by Nov 3, +$832.69 terminal model PnL | $293.85 | Safer stress proxy but +10% target not reached |
| H34/M51/H36 with co-crash-clamped M51 | 0.001468293 / **0.004556347** / 0.006698076 | 5m/6bps modeled target **Oct 6** | $400.00 | Target occurs **after** an unmanaged pod-hard-stop threshold; no compliant stop/flatten replay |
| H34/M51/H36 with *full-sample* risk sizing | 0.001468293 / **0.002210158** / **0.005640022** | **No target** by Nov 3, +$647.43 terminal model PnL | $279.02 | Full-sample risk is knowingly retrospective; speed evaporates |

Full-sample terminal P&L and drawdown figures are **unmanaged scenario descriptions**; they must never be read as a follower account that would continue past its first contract pass, pod stop or unknown source state.

### Cost and delay sensitivity (unclamped H34/M51/H36)

| Delay | 6 bps per side | 12 bps per side | 18 bps per side |
| --- | --- | --- | --- |
| 2m | Modeled target Sep 25 | Modeled target Sep 26 | Modeled target Sep 27 |
| 5m | Modeled target Sep 25 | Modeled target Sep 26 | Modeled target Sep 27 |

These historical first-passage observations **do not establish a pass probability**. The same portfolio's 1.5x coincident daily stress is **$636.61**, above both the $400 internal target and $500 contractual daily allowance. Its speed advantage is therefore not an admissible recommendation.

The 5m/6bps three-anchor baseline reaches a hypothetical target Sep 27, two days after unclamped H34/M51/H36, but its co-worst stress is $642.76. Both are underprotected on this conservatively aligned scenario. Co-crash-clamping H34/M51/H36 largely removes its advantage: its 2m trajectory never reaches the target during the study, its 5m/12bps and 5m/18bps trajectories do not reach the target, and its 5m/6bps target requires ignoring a prior pod-hard-stop threshold. Actual flattening P&L **was not modeled**.

## Runner distribution and dependence diagnostics

The following are descriptive 4h increments of **retrospectively sized synthetic follower equity** at 5m/6bps, not authenticated source-account return moments, source PnL or independent prospective alpha.

| Wallet | 4h skew | Excess kurtosis | Observed source fill-turnover dominance |
| --- | ---: | ---: | --- |
| H34 | +3.951 | 34.793 | BTC 55.55%, ETH 36.32% |
| M51 | +1.038 | 27.421 | BTC 85.91% |
| H36 (runner slot) | **+0.301** | 10.430 | BTC 34.84%, ETH 28.16%, HYPE 17.53% |
| M40 (runner slot) | +5.167 | **77.589** | HYPE 92.80% |
| M50 (runner slot) | +0.481 | 8.297 | HYPE 45.28%, BTC 33.48%, SOL 21.24% |
| M58 (runner slot) | +0.149 | 3.738 | HYPE 48.70%, ZEC 28.18% |

**The apparently most robust speed runner H36 fails the proposed strict skew >+1 rule on these modeled 4h returns.** M40 clears positive skew but has extreme tail concentration and much higher subsequent stress risk. No candidate is independently qualified as a convex momentum runner, and labels are not verified structural alpha classifications.

Pairwise synchronized 4h diagnostics (540 windows, 5% tail = about 27 observations per wallet):

| Wallet pair | Pearson | Spearman | Conditional 5% co-loss | Joint lower-tail events |
| --- | ---: | ---: | ---: | ---: |
| H34/H36 | +0.3777 | +0.4819 | **33.3%** | 9 |
| H34/M51 | +0.0735 | +0.2018 | 3.7% | 1 |
| H36/M51 | +0.1804 | +0.2652 | 11.1% | 3 |

These point estimates are noisy; the H34/H36 co-loss fraction exceeds the provisional 25% pairing screen. Low unconditional Pearson is not proof of macro flush independence. All three have material BTC turnover exposure. M22 scaled-position marks are discontinuous, so no full-window 4h correlation is claimed for it.

## Blocking evidence and exact next experiment

1. **Risk:** enforce per-pod daily soft/hard stops and lifetime HALTs with stateful PM-03/PM-04 netting, cancel/partial-fill races, and real next-open flatten costs. The stored unmanaged stop timestamps are **diagnostics only**. Do not count target touches requiring ignored stops as passing.
2. **Data integrity:** repair M22 sized-follower active book at Sep 22; independently establish full first-known source equity, positions, DEX scopes, funding and opening inventory. No missing active market may be filled with zero, forward fill or an omitted-order alpha story.
3. **Science:** freeze wallet candidates *before* a new unobserved evaluation window and record point-in-time selection and source timestamps. Require separate calibration/OOS windows, alternative volatility regimes, cost ×3, joint tail dependence CIs, and live forward paper (14–30 days minimum).
4. **Actuary:** use existing `pm_contract_selector` only with complete synchronous net follower MTM after actual pod hard-stop/fill sequencing and user-confirmed contract rule snapshots. No EV or pass probability is produced from these files.

### Reproduce read-only

```bash
uv run --frozen --extra market --group dev python scripts/ml4t66_barbell_research.py \
  --db /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --source-root /home/quant/dev/copytrade-pm/data \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --output-root /home/quant/.local/share/copytrade/reports/barbell-20261105
```

**Immutable private report:** `/home/quant/.local/share/copytrade/reports/barbell-20261105/barbell_research_8c7ce3611da6471acf75.json`

**SHA256:** `8c7ce3611da6471acf75d02393a103a60246264789ee47eb71123204fad5ebdf`

Results in the immutable JSON are signed by no independent producer and are not prospective financial evidence. The SQLite registry, production processes, source pages and real orders were **not changed**.

**Status:** Research tool implemented and targeted unit-verified; economic scenario assessed; scientific qualification **NO**; live trading **NO**. Reviewer/judge verdict unavailable in this tool environment; no cohort promotion, freeze, or policy deployment has been authorized.
