# Phase 7 — $10,000 BTC/ETH/SOL/HYPE follower sensitivity (M3/M4/M5)

**Evidence date:** 2026-11-05. **Source interval:** 2026-08-05T00:00:00Z through 2026-11-03T00:00:00Z exclusive. **Type:** retrospective conditional hypothetical four-market follower equity replay, **not** actual follower/exchange economic qualification. No additional historical fill acquisition.

## Executive answer

**M3 is the only promising conditional profitability candidate at a $10,000 starting account. M4 is a weak near-breakeven comparator; M5 is unprofitable at 20 bps.**

Main scenario: leader event seen hypothetically at source timestamp; **wait five minutes**, collapse to next **five-minute UTC execution grid**, execute at the exact SHA-verified future Hyperliquid 1m **OPEN**, follow normalized signed known-source positions **only in BTC, ETH, SOL, HYPE**. Apply composite one-way 20 basis points per order notional, including hypothetical terminal flatten. $10,000 cash starts; total **$6,000** maximum target gross exposure divided equally among wallet pods. **No enforcement of a max loss stop**: the equity curve continues after violations; consequently ending profits after a model breach are not feasible under a stop-constrained prop account.

| Portfolio | Wallets | Hypothetical ending equity | Net after 20 bps | Return on $10k | 1m worst-bar high/low max DD | Internal $850 trailing reference | First modeled crossing UTC |
|---|---|---:|---:|---:|---:|---|---|
| **M3-BALANCED** | H02, VS002, W083 | **$10,984.43** | **+$984.43** | **+9.84%** | **$858.13** | **FAIL** by $8.13 | 2026-09-24 09:35 |
| **M4-SPECIALISTS** | ACT33, ACT34, H02, W083 | **$10,136.87** | **+$136.87** | **+1.37%** | **$901.75** | **FAIL** by $51.75 | 2026-11-02 17:21 |
| **M5-SOL-BOOST** | ACT33, ACT34, H02, HX01, W083 | **$9,988.95** | **−$11.05** | **−0.11%** | **$894.21** | **FAIL** by $44.21 | 2026-10-30 00:18 |

All 90 daily market bars for all four coins are present and individually full-day, timestamp- and SHA-verified. The worst single-day *model* loss from UTC opening equity is **−$328.70**, **−$210.97**, and **−$245.01** respectively, all inside the illustrative $450 daily reference. This is not measured venue-level margin or official Propr rule enforcement.

### Gross budget sensitivity on the same $10,000 starting account

| Portfolio | $6,000 gross, 20 bps net / max DD | **$5,000 gross, 20 bps net / max DD** | $5,000 gross, 30 bps net / max DD |
|---|---|---|---|
| M3 | +$984.43 / $858.13 | **+$820.36 / $715.11** | +$198.20 / $1,118.44 |
| M4 | +$136.87 / $901.75 | +$114.06 / $751.46 | −$568.78 / $1,329.08 |
| M5 | −$11.05 / $894.21 | −$9.21 / $745.17 | −$599.78 / $1,244.54 |

**Model-only:** At $5k gross and 20bps, all three remain below *these two internal historical loss references*. **M3 is the only one with a material positive modeled margin.** All three exceed $850 max drawdown at $5k gross and 30bps. No sizing change is approved by this table. No full-account source leverage is known; this normalization is **not faithful to each leader's equity sizing**.

## Fee sensitivity is the primary economic finding

| Portfolio | Gross market-mark PnL | Gross modeled turnover | Model net @10bps | Model net @20bps | Model net @30bps | In-sample break-even composite cost |
|---|---:|---:|---:|---:|---:|---:|
| M3 | $2,477.61 | $746,591.69 | +$1,731.02 | +$984.43 | +$237.84 | 33.19bps |
| M4 | $1,775.70 | $819,411.58 | +$956.28 | +$136.87 | −$682.54 | 21.67bps |
| M5 | $1,406.31 | $708,679.89 | +$697.63 | −$11.05 | −$719.73 | 19.84bps |

These are **historically derived** turnover break-even arithmetic, not forward cost allowances. Real venue maker/taker mix, spread, adverse selection, market impact, funding and slippage at actual execution time are UNKNOWN; only flat composite cost stress is modeled.

**Stricter 30bps $6k DD:** M3 $1,342.12, M4 $1,594.90, M5 $1,493.44. Every combination fails the $850 sample trailing reference. M3's small +$237.84 modeled profit at 30bps comes **after an already breached loss limit**.

## Where did the M3 proxy profit come from?

20bps, full $6k budget, 5-minute wait and 5-minute batching. Unit-normalized contribution before and after allocated trading costs:

| Wallet | M3 modeled gross mark PnL | Costs | M3 modeled net |
|---|---:|---:|---:|
| H02 (SOL-leaning) | +$47.82 | $418.18 | **−$370.36** |
| VS002 (BTC/ETH mix) | +$593.85 | $329.11 | **+$264.73** |
| W083 / S053-HYPE | +$1,835.95 | $745.89 | **+$1,090.06** |
| **M3 combined** | **+$2,477.61** | **$1,493.18** | **+$984.43** |

**This is largely a HYPE-wallet result, not evidence of positive independent edge on BTC/ETH/SOL.** H02 loses under the modeled execution costs despite its SOL coverage. M4 is even more concentrated in one winner: W083 contributes +$817.54 while ACT33 contributes −$120.20, ACT34 −$282.70 and H02 −$277.77. M5 adds HX01 at **−$120.55** and ends slightly negative. Simply adding a fifth wallet is not an improvement here.

## Chronology and robustness

Full-window in-sample 30-day blocks at 20bps, $6k gross, five-minute batch:

| Portfolio | Days 1–30 | Days 31–60 | Days 61–90 | Positive blocks |
|---|---:|---:|---:|---:|
| M3 | +$1,241.71 | −$468.73 | +$211.45 | 2/3 |
| M4 | +$976.71 | −$290.55 | −$549.29 | 1/3 |
| M5 | +$816.64 | −$189.31 | −$638.39 | 1/3 |

**These blocks are not untouched forward/OOS holdouts.** Portfolios were identified using the same period, so the earlier gains may be selection effects. M4/M5's last two negative blocks weaken the thesis that more specialists yield a stable positive expectancy.

A second *causal state-assumption* sensitivity accumulates signed source fills from an assumed zero opening position, instead of using available raw `startPosition` and inferring CSV `dir` episodes. At 20bps with 5min batching: **M3 +$984.50, M4 −$448.41, M5 −$444.88**. In contrast, removing exact identical TID-less CSV lines as a *sensitivity only* (not a permanent data correction) gives **M3 +$1,313.06, M4 +$235.85, M5 +$78.36**. Thus **M4 and M5 change sign based on uncertain source reconstruction**; their apparent marginal profitability is not robust. M3 remains positive under these alternatives but has insufficient risk/cost robustness.

A no-five-minute-grid next-full-minute path (still +5m delay) yields at 20bps: M3 +$858.69, M4 +$29.77, M5 −$107.75; every one breaches the illustrative trailing reference at $6k gross. 10-minute historical signal delay further worsens some outcomes, and no actual first-known receipt is available.

## Data provenance and exact limitations

- Source authority: current private SQLite registry, **158 exact research addresses**, source generation `e2836aab5ef6ef79306e9dfe732d8768c3b1ca6af29efbda066b37f03646a18f` as observed 2026-11-04 09:36:57Z. All six selected wallet addresses exact-match the registry and immutable original Stage-1 source catalog; the study does not select new wallets.
- Original fill sources, source SHA checked individually: three frozen original JSON files (ACT33, ACT34, W083) and two frozen compressed vendor CSV archives (H02, HX01, VS002). **8,754** BTC/ETH/SOL/HYPE rows across six unique wallets. **No new fills downloaded**, and all originals are read-only. No private wallet addresses or fill pages are committed to Git.
- Critical source sequencing repair: same-millisecond raw TIDs are **not** chronological. Reconstruct unambiguous `startPosition → postPosition` directed Eulerian fill chains before replay. ACT33: 117 resolved timestamp groups; ACT34: 407; W083: 326. All corresponding raw chains pass cross-group continuity validation. Original wrong-TID-sort V1/V2 reports are preserved and explicitly **SUPERSEDED**, not silently overwritten. Counterfactual versions with signed-delta and TID-less CSV duplicate collapse are clearly labeled.
- Native minute pricing: **90/90 complete SHA-verified UTC source days per coin** for BTC, ETH, SOL and HYPE. Market OHLC open/high/low/close, 129,600 minutes each. Timestamp event+5m followed by next allowed 5-minute UTC execution-grid minute **OPEN**; no same-bar decision lookahead or nearest price imputation. Actual availability of historical fills at that time remains **unverified**.
- Portfolio construction: initial $10k equity (cash accounting of PnL), $6k or $5k **total modeled gross budget**, equally divided by wallet. Each wallet's *only currently reconstructed four-coin book* is gross-normalized to its budget when new source evidence arrives. This is **NOT** source-equity-faithful sizing. The CSV-only managers have no known opening book; unmatched closes are ignored until observable opens, with modeling ambiguity retained.
- The requested four markets are explicitly **filtered**; all leader fills outside BTC/ETH/SOL/HYPE are excluded. Therefore the model tests a *new filtered follower policy*, not each manager's actual whole-wallet return. There is no evidence that this filtering preserves each wallet's strategy PnL, risk hedges, funding or net equity.
- Composite costs 10/20/30bps are applied to each *executed* gross notional change, including a synthetic flatten at study end. **No independently measured orderbook spread, impact, fees, funding, rejection/partial fill, queue, margin, capital transfer, liquidation, real prop-firm risk cut, or broker production execution**. When a hypothetical trailing/daily threshold is exceeded, the backtest **does not stop**; subsequent returns are invalid for a strict risk-limited challenge interpretation.
- The result is a **hypothesis-generation sensitivity**, not statistically significant alpha, a forward holdout, a verified $10k brokerage return, a pass rate, a follower NAV or a wallet trading authorization.

### Immutable local artifact / reproducibility

Code: `scripts/phase7_major4_10k_filtered_follow.py`. Tests: `tests/test_phase7_major4_10k_filtered_follow.py`.

Most recent SHA-pinned private full evaluation (all input source and market fingerprints, model/audit alternatives, individual contributors, calendar blocks, risk path):

```text
/home/quant/.local/share/copytrade/reports/phase7_major4_10k_filtered_follow_20261105_v5.json
SHA-256: f4fd04352794173075c7afafd7afbd6d16a1f108f3a0deb61d165243b21ffc1e
```

Reproduce in project worktree, passing a **new** output name (immutable output never overwritten):

```bash
uv run --frozen --group dev --extra market python -m scripts.phase7_major4_10k_filtered_follow \
  /home/quant/.local/share/copytrade/reports/phase7_universe_20261104_v2.json \
  --root /home/quant/dev/copytrade-pm \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --output /home/quant/.local/share/copytrade/reports/phase7_major4_10k_filtered_follow_20261105_YOUR_NEW_VERSION.json
```

**Disposition:** M3 **EXPERIMENT** with a $5k gross risk-normalized reference only; M4 **WEAK COMPARISON**; M5 **IGNORE as profitability candidate**. All three remain **RESEARCH_ONLY**, `SCIENTIFICALLY_QUALIFIED=false`, `TRADING_AUTHORIZED=false`. Frozen E6/E2/P1 and all paper/prod workers remain unchanged.
