# Phase 7 — Five-wallet portfolio expansion on a $10,000 account

**Research cut:** 2026-11-05. **Historical fills:** 2026-08-05 00:00 UTC to 2026-11-03 00:00 UTC, end exclusive. **Result:** CONDITIONAL historical follower-model comparison; **NOT verified first-known, source-equity-faithful or executable follower P&L**.

## Decision

**Five wallets can outperform the previously tested three-wallet baseline under the same *modeled* gross budget; the old M5 was poorly selected, not proof that five wallets are unsuitable.** Two new five-wallet designs are credible *research experiments*, while neither is scientifically qualified or trading-authorized.

1. **M5-BROAD-SEARCH-BEST — highest historical economic resilience in the bounded study:** **HX04 + N05 + VS025 + VS035 + W083**. At $10,000 starting cash, **$5,000 *total target gross***, 5-minute retrospective event-time wait plus 5-minute UTC execution-grid batching and 20bps composite one-way friction: **+$1,996.43** / $11,996.43 ending *modeled* equity with a pessimistic synchronous 1-minute high/low maximum drawdown **$673.26**. At 30bps: **+$1,696.39**, DD **$743.32**. The late 30-day segment was **−$72.19** at 20bps, however; **four of the five wallet histories come from CSV without verified opening positions**, and the selection involved thousands of correlated earlier historical trials.
2. **M5-M3-EXTENSION — continuity-focused alternative:** **H02 + VS002 + VS035 + VS057 + W083**. Preserves the full M3 trio and adds two candidates. Same $10,000 cash / $5,000 gross target / 20bps: **+$1,420.65**, DD **$582.89**. At 30bps: **+$981.94** but DD **$873.24**, *above* the illustrative $850 loss reference; recent 30-day net is only **+$22.56** at 20bps. The model's signed-delta reconstruction alternative shrinks 20bps net to **+$198.97**, and 30bps net to **−$184.37**, so the apparent advantage is **not robust to unknown starting positions**.
3. **M5-LOW-CORRELATION — defensive *relative* control:** **ACT39 + HX04 + N05 + VS002 + VS078**. First-60-day **mean modeled daily *wallet* net-PnL correlation = −0.0534**, vs **+0.6102** for M5-BROAD-SEARCH-BEST and **+0.5015** for M5-M3-EXTENSION. 20bps net **+$463.75**, DD **$504.66**; 30bps net **+$240.61**, DD **$613.06**. Last 30-day net **−$78.56**. A low mean return correlation is **not proof of independence**: this portfolio's maximum individual pair correlation remains **+0.6774**, and 25 first-60-day trading days have losses from three or more members. Historical opening positions/NAV unknown.

**M3 (H02 + VS002 + W083)** remains the fixed comparison baseline: 20bps **+$820.36**, DD **$715.11**; 30bps **+$198.20**, DD **$1,118.44**. The **old M5** (ACT33 + ACT34 + H02 + HX01 + W083) remains a negative control: 20bps **−$9.21**, DD **$745.17**; 30bps **−$599.78**, DD **$1,244.54**.

**Provisional research order:** (1) broad-search five-wallet conditional challenger, (2) direct M3-preserving five-wallet extension, (3) lower-correlation five-wallet stress control, (4) fixed three-wallet baseline, (5) old five-wallet negative control. Do **not** modify frozen E6/E2/P1 or assign trading-risk budgets from this output.

## Strict like-for-like cash and risk comparison

All rows below use **$10,000 starting cash**, the same **$5,000 total target gross** divided equally across the actual number of pods, and only exact native BTC/ETH/SOL/HYPE default perps. Each source wallet's known four-coin position mixture is gross-normalized to an allocation at rebalance events; **$1,000 notional per wallet is NOT a $200 loss budget or a hard continuous-exposure cap**. Mark-to-market price drift can increase gross between signals. There is **no automated dollar stop**, no real broker order/fill receipts and no source NAV/leverage.

| Portfolio | 5-min batch / 20bps net PnL | Modeled ending equity | 20bps pessimistic 1-min max DD | 30bps net PnL | 30bps max DD | $850 trailing reference at 20/30bps |
|---|---:|---:|---:|---:|---:|---|
| **New M5 broad-search** | **+$1,996.43** | **$11,996.43** | **$673.26** | **+$1,696.39** | **$743.32** | PASS / PASS, model only |
| **M5 M3 + two** | **+$1,420.65** | **$11,420.65** | **$582.89** | **+$981.94** | **$873.24** | PASS / FAIL, model only |
| M5 lower-correlation | +$463.75 | $10,463.75 | $504.66 | +$240.61 | $613.06 | PASS / PASS, model only |
| **M3 baseline** | +$820.36 | $10,820.36 | $715.11 | +$198.20 | $1,118.44 | PASS / FAIL, model only |
| **Old M5** | −$9.21 | $9,990.79 | $745.17 | −$599.78 | $1,244.54 | PASS / FAIL, model only |

The model also computes the **$6,000 total target gross** scenarios; at 20bps the new broad-search M5 produces **+$2,395.71** with modeled DD **$807.91**, inside the $850 reference. At **$6,000 and 30bps**, its DD is **$891.99**, exceeding the reference. Given the source-position uncertainty and higher gross sensitivity, **$5,000 is the stronger *research comparison* scenario**, not a recommended live allocation.

The loss references ($450 worst intraday from UTC opening equity and $850 trailing peak-to-trough) are **illustrative** and cannot be represented as exact contractual prop-firm risk enforcement. The model uses conservative per-minute high/low extrema, but is **not an actual sequential stop simulator**: it keeps reporting returns after any risk breach. Therefore a portfolio that breaches a limit cannot claim subsequent profit as achievable challenge PnL. All portfolios here are unqualified regardless of the modeled pass labels.

## Why the previous five-wallet result was misleading

The old five-wallet selection removed the profitable VS002 from M3 and added ACT33, ACT34, HX01 while cutting W083's notional share from a third to a fifth. That was a **different set of wallet strategies**, not just the effect of changing from three to five managers. It obscured the effect of true portfolio size.

The new study holds the **same total gross target** across both portfolio sizes, compares the original M3 unchanged, tests **M3 + two** explicitly, and explores a broader pool separately rather than claiming one arbitrary five-wallet portfolio represents all five-wallet designs.

## Market specialization and dependence

| Candidate five-wallet design | BTC traded-notional share | ETH | SOL | HYPE | Combined four-market | Mean modeled daily member-PnL corr (first 60d) | Max modeled daily member pair corr |
|---|---:|---:|---:|---:|---:|---:|---:|
| M5 broad-search | 13.50% | 16.81% | 9.08% | 35.85% | **75.24%** | **+0.6102** | +0.8880 |
| M5 extends M3 | 30.71% | 7.94% | 8.22% | 32.83% | **79.71%** | +0.5015 | +0.8282 |
| M5 lower-correlation | 33.17% | 18.87% | 7.58% | 16.11% | **75.74%** | **−0.0534** | +0.6774 |

These market percentages are the **equal-wallet historical share of filled USD notional**, *not* actual gross open positions. Correlations are **first-60-day modeled *daily net PnL* correlations**, *not* source-wallet realized economics, instantaneous long/short co-directionality, or proof of hedged exposure. The two most profitable-looking portfolios have **substantial positive modeled daily cross-wallet dependence**: five wallet identities are not five independent sources of risk.

### Cost, position-anchor and latency robustness

**M5 broad-search**: +$1,996 at 20bps and +$1,696 at 30bps under episode-inferred position state. Starting position reconstructed with a **signed fill-delta from an assumed flat book** instead: **+$817 at 20bps, +$544 at 30bps**; a conservative 10-minute signal delay gives **+$1,921 at 20bps**. Treating identical TID-less CSV rows as duplicates *for sensitivity only* gives **+$1,941 at 20bps**. The direction remains positive in these retrospective variants, **but actual opening positions, source account equity, timestamp of first availability and executable follower costs remain unknown**.

**M5 M3-extension**: +$1,421 / +$982 at 20/30bps in base model, but signed-delta alternative only **+$199 / −$184** and 30bps risk reference fails in the base model. The gain is sensitive to the source-episode assumption. Ten-minute delay still produces +$1,368 at 20bps, but delayed fills are not actual first-known receipts.

**M5 lower-correlation**: +$464 at 20bps / +$241 at 30bps; the first 60 days have lower mean modeled member PnL correlation than the two high-return portfolios. But the final 30-day sample is negative, its absolute net is smaller, and some member pairs remain correlated.

**No real risk authorization is established** by positive modeled PnL, by passing the $850 reference at one fee assumption, or by a signature of trading style.

## Time split and multiple testing

The stage-one optimizer uses **only days 1–60** (in this already explored 90-day sample), using historical conditional 20/30bps daily-close net results, daily-close DD and average of five worst daily closes. The last 30 days are reported **separately** and **were never used in the new stage-one score**, but the wallet roster and portfolio hypotheses had already been exposed to previous work spanning the full 90 days. **The final 30 days are NOT a pristine holdout**.

| Portfolio | First 30 days, 20bps | Days 31–60 | Days 61–90 (reused diagnostic) |
|---|---:|---:|---:|
| M5 broad-search | +$1,882.96 | +$185.65 | **−$72.19** |
| M5 extends M3 | +$1,525.72 | −$127.63 | **+$22.56** |
| M5 low-correlation | +$457.96 | +$84.35 | **−$78.56** |
| M3 baseline | +$1,034.76 | −$390.61 | **+$176.21** |
| Old M5 | +$680.53 | −$157.76 | **−$531.99** |

**Selection universe and trial accounting:**
- Registry-first checked 158 research addresses (108+20+30) with generation SHA `e2836aab5ef6ef79306e9dfe732d8768c3b1ca6af29efbda066b37f03646a18f`, observed 2026-11-04 09:36:57 UTC; all selected candidates use exact canonical address binding to original frozen 90d fill sources, with 22 owner exclusions excluded. A monitored or selected wallet is not paper-running or qualified.
- Stage-1 eligible pool: **24** research wallets; 26,918 BTC/ETH/SOL/HYPE source fills parsed from SHA-checked original 90-day JSON/CSV data. **No acquisition calls** were made.
- **42,504** five-wallet combinations explored. **2,433** meet >=75% combined four-market traded-notional share and >=7.5% mean on *each* BTC/ETH/SOL/HYPE; **143** of these preserve all three original M3 wallets. **2,191** passed a **positive first-60-day 30bps net heuristic**. The broader pool and loss/return study had already been tested on this period, so these are highly correlated in-sample selection trials, **not thousands of independently profitable strategies**.
- Secondary full-minute 10/20/30bps and $5k/$6k risk sweeps were evaluated for **19 preselected finalists**, with signed-delta, identical-CSV-row sensitivity and ten-minute delayed alternatives on the major controls. Preselection did not use final-30-day profit metrics, but the overall research is hindsight-contaminated.
- BTC, ETH, SOL and HYPE each have **90 independently SHA-verified complete native 1m days**; no missing bars or cross-venue candles were silently substituted. Source opening positions outside adjacent fills, historical NAV, per-DEX subaccounts, funding and first-known receipt timestamps are NOT established.
- The four-market follower design excludes every other coin in each leader's book, which may remove hedges, alter netting and break leader-economics fidelity. Actual investor equity and source-leverage-based `k` are not available.
- Each wallet is assigned $1,000/$1,200 **gross target at a rebalance** for five wallets. The target is not a hard continuous cap: source position price drift between signals produces per-wallet observed gross multipliers above 1.0 (up to 1.43 in N05, 1.37 in W083 and 1.41 in VS057 in the local 90d model), and potential correlated gross positions are not independently netted or margin-reconciled.
- Risk-budget, stop/kill, true execution, transaction-cost calibration, venue liquidity, real first-known, source-equity sizing, genuine OOS walk-forward and scientific economic acceptance remain UNKNOWN. **This study does NOT authorize active paper worker or live orders.**

## Reproducibility

New research script: `scripts/phase7_best5_major4_screen.py`. Focused tests: `tests/test_phase7_best5_major4_screen.py`.

Pinned immutable private report:

```text
/home/quant/.local/share/copytrade/reports/phase7_best5_major4_screen_20261105_v5.json
SHA256: 86bb03ff35d4a639c429d8a4b916496f4d210f4c0485918f7691e84d74af8614
```

The machine-readable report includes all 19 finalists, portfolio members and their selected research roles, all three costs for both gross targets, exact modeled earliest risk-reference crossings, first60 and last30 comparisons, selected sensitivity modes, coin mix, correlations, wallet source SHA records and 90-day independent native price-day evidence. Older private V1–V4 are **superseded** and remain unchanged.

```bash
uv run --frozen --group dev --extra market python -m scripts.phase7_best5_major4_screen \
  /home/quant/.local/share/copytrade/reports/phase7_universe_20261104_v2.json \
  --source-root /home/quant/dev/copytrade-pm \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --output /home/quant/.local/share/copytrade/reports/phase7_best5_major4_screen_20261105_REPRO_NEW_VERSION.json
```

Existing original fill files, canonical market data, approved Gemini E6/E2/P1 portfolio seals, registry selection, Telegram monitor, provider and broker services are **unchanged**. All candidate scores are **RESEARCH_ONLY / SCIENTIFICALLY_QUALIFIED=false / TRADING_AUTHORIZED=false**.
