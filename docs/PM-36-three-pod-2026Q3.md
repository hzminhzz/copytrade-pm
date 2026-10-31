# PM-36: three-pod 2026Q3 shared-account execution experiment

**State: RESEARCH-ONLY historical-oracle experiment. Not a qualified
copytrading portfolio, not a prospective signal, not a Propr pass-probability
estimate, and no live orders or broker deployment.**

## Decision

Freeze the following **exploratory** pods for this experiment:

| Pod | Wallet | Research reason |
|---|---|---|
| A | W028 | 106 previously matched 5m/15m/60m historical episode comparisons |
| B | W042 | 40 matched episodes with positive post-hoc incremental control PnL |
| C | W030 | 32 matched episodes and a different candidate instrument mixture |

**No out-of-sample selection claim:** these three were picked after seeing the
July–September 2026 history. Results from the same period cannot scientifically
confirm their ranking or independence.

### Study bounds and provenance

- **2026-07-01 00:00 UTC inclusive → 2026-10-01 00:00 UTC exclusive**:
  92 calendar days (often called a 90-day quarter).
- Audited 6 + 10 + 20 wallet source cohort, exact three selected alias identities,
  SHA-verified original immutable vendor page economics and four authenticated
  HyperX gap-recovery generations.
- All complete flat-to-flat *per-instrument* episodes from each selected wallet:
  W028 140, W042 62, W030 61 = **263** available completed source episodes.
- Eligibility screen: **strict native crypto display match** in a **2026-10-30**
  post-period Propr snapshot, plus **continuous venue/symbol/SHA verified
  native Hyperliquid 1m opens** from first possible execution through final
  delayed exit. This retrospective filter uses future episode completion
  and future price coverage. It does NOT prove Propr offered the instrument
  during the July–September historical study.
- 204 included episodes: W028 **101**, W042 **50**, W030 **53**;
  **2,761 historical source fills**, **23** instrument names and
  **410** consumed native Hyperliquid instrument/day source hashes.
  **53** completed episodes excluded for unverified/outside post-period
  Propr display scope, **6** for exact 1m market gaps.
- Additional open or carry-in/carry-out source positions have no attribution
  in this follower experiment. **Missing is not flat or zero PnL**; this is
  a *partial, survivorship-biased* copy of three incomplete manager books.

## Portfolio risk and execution contract

- Hypothetical account: **$100,000**; equal pod entry-budgets of
  **$100 / $500 / $2,000 gross notional per newly observed per-instrument
  episode**. Three experiments; NOT 0.1%/0.5%/2% risk-at-stop.
- Pod maximum gross target = 5 × per-episode budget; portfolio target hard
  threshold = min(50% account, 15 × per-episode budget); single instrument
  threshold = 6 × budget. Target notional is limited to **90% of the
  portfolio/instrument thresholds** for execution headroom.
- Each source position change becomes one pod virtual target, scaled only
  from the *source episode's own first opening quantity and price*. Three
  pod quantities are **signed-netted by exact native market instrument**.
  Submitted account delta = capped combined target − actual account inventory.
- All policies share one virtual cash/position/funding ledger, same historical
  source episodes, same account risk limits and the same data.
- Taker fee **5bp**, half of **3bp spread**, slippage **5bp**, positive
  funding stress **1bp/8h**; all explicitly modeled, not calibrated to
  actual Propr fills. **1× / 2× / 3×** fee-spread-slippage sensitivity,
  funding assumption held fixed.
- Market capacity is at most **5% of the *previous completed* one-minute
  volume**, deliberately avoiding lookahead into the fill minute's volume.
  This is a weak volume proxy, not Level-2 or a proven executable quote.
  New-risk orders without capacity are skipped and counted. Risk reductions
  are divided into capacity-bounded partial orders across later minutes,
  with outstanding inventory continuously marked and counted.
- Simulated account floors are **+10% target, −3% daily, −6% static total**,
  with UTC midnight resets based on sampled *equity*, not an independently
  reconciled official Propr account balance. Checks occur at 1m opens only,
  so **intraminute spikes, margin liquidation and gaps can breach first**.
- Marked gross can still overshoot the target hard threshold on prices or
  liquidity constraints. Forced next-minute reductions are recorded;
  these are **NOT fully enforceable broker hard limits**. An observed
  in-sample path without sampled floor breaches is not a verified compliant
  prop-firm account.

### Execution policies

| Policy | After a source fill could first be observed at next 1m open |
|---|---|
| IMMEDIATE | Compute net three-pod target and place an eligible net order immediately |
| FIXED_5M | Defer each source update 5m; do not purposefully aggregate the updates |
| BATCH_5M | Start **non-resetting** 5m timer per symbol; net all updates into latest target, including reductions |
| ASYMMETRIC_5M | Batch new/increasing risk for 5m; bypass timer for risk reductions and flatten before reversals |

When minute capacity is insufficient, the policy must either skip new risk
or split reductions. Thus **"one market order" is not guaranteed** for
thinly traded instruments. The model does not connect to a live broker.

## Results — one full 92-day in-sample historical path

Dollar amounts USDC on the illustrative $100k account, all costs modeled.
**This is NOT a validated follower equity history or OOS pass probability.**

| Gross budget per episode | Policy | 92-day historical-oracle net PnL | Modeled orders | Sampled peak-to-trough DD |
|---|---|---:|---:|---:|
| $100 | Immediate | +$660.76 | 1,925 | $150.04 |
| $100 | Fixed delay | +$658.58 | 1,610 | $110.46 |
| $100 | 5m batch | +$649.69 | 1,349 | $110.37 |
| $100 | 5m asymmetric | +$570.51 | 1,324 | $121.19 |
| $500 | Immediate | +$2,574.46 | 1,482 | $537.41 |
| $500 | Fixed delay | +$2,344.60 | 1,541 | $446.75 |
| $500 | 5m batch | +$2,307.07 | 1,284 | $427.96 |
| $500 | 5m asymmetric | +$2,121.13 | 1,238 | $483.94 |
| $2,000 | **Immediate** | **+$8,338.15** | 1,265 | $2,172.70 |
| $2,000 | Fixed delay | +$6,345.80 | 849 | $1,453.11 |
| $2,000 | **5m batch** | **+$6,655.92** | **772** | **$1,486.71** |
| $2,000 | 5m asymmetric | +$6,350.70 | **713** | $1,721.60 |

At $2,000 per episode, batching reduced order count by **39.0%**, but had
**$1,682.24 less net PnL** than immediate execution. This sample contains
only one surviving, retrospective path; it cannot establish which execution
policy has positive OOS expectation.

Under the *sampled* illustrative floors, **0/12** 1×-cost scenarios touched
the +$10,000 target or sampled loss floors. This does **NOT** imply 0%
pass probability or zero true intraminute breaches.

### Slippage and fee sensitivity, $2,000 episode size

| Cost multiplier (taker fee, spread, slippage) | Immediate net | 5m batch net |
|---|---:|---:|
| 1× | +$8,338.15 | +$6,655.92 |
| 2× | +$6,747.06 | +$5,298.27 |
| 3× | +$5,155.97 | +$3,940.63 |

Model cannot claim live market impact, true bid/ask queue position, partial
order semantics or broker-side fees. Widening assumed execution costs
did not reverse immediate vs batch PnL ranking in the selected sample.

### Critical risk and feasibility flags

- The $2k immediate scenario observed marked gross as high as **$32,822.79**
  versus a $30k gross nominal ceiling, and the batched scenario as high as
  **$33,254.21**. This occurred despite a 10% target sizing buffer, due to
  price movements/capacity-limited rebalancing. Consequently, the code
  **does not establish a mechanically hard intraday gross-cap guarantee**.
- At $2k the immediate account's sampled worst daily equity loss was about
  **$1,134** and sampled peak-to-trough drawdown **$2,173**. Batched
  equivalents were roughly **$997** and **$1,487**. These are open-minute
  samples, not independently verified tick/broker drawdown extrema.
- The **post-period** market list does not demonstrate Propr tradability
  at event time. Hidden cross-instrument hedges are missing; the successful
  flat-to-flat episode filter excludes unclosed (including potentially large
  losing) trades; source times are historical oracle timestamps with unknown
  public first-known time.
- Hypothetical success is therefore neither source-wallet skill,
  independently executable follower profit, nor a validated probability
  of passing the challenge. *All three pod seats remain research-only.*

## Engineering proof and follow-up

The execution model has regression tests for source timestamp precedence,
cross-pod signed netting, hard-target scaling, five-minute deadlines,
asymmetric reduction priority, prior-minute volume, capacity-bounded
partial exits, missing-price blocks, sampled account loss floors and
source signal sorting.

**Next test before trading:** acquire genuine first-known observations
and independently reconcile each pod's whole book, equity, funding and
source market identities. Pre-register a portfolio, costs, internal risk
ceilings and executable Propr instrument set; then replay an untouched
chronological period with full netted equity, joint liquidity, tick
adverse moves, margin limits and broker-level execution gates.
The current research sample must not be presented as OOS alpha.

### Private reproducible output

- Artifact SHA-256:
  `9806e1064dfb66690886955ef9b1788225ef7d46874f0ce56ad80ce01d477718`.
- Private path:
  `/home/quant/.local/share/copytrade/reports/pm36-three-pod-test/pm36-2026q3-threepod-9806e1064dfb66690886.json`.
- The file is valid JSON, stored owner-only and content-addressed. All source
  addresses, vendor page bytes, internal APIs and keys remain off Git.

```sh
ROOT=/home/quant/.local/share/copytrade/reports/five-pod-20261029-research
BASE=/home/quant/.local/share/copytrade/reports/pm01-hyperx-gaps
MARKET=/home/quant/dev/quant/ml4t-data/.data/store
OUT=/home/quant/.local/share/copytrade/reports/pm36-three-pod-test
uv run --extra market --group dev python -m copytrade_pm.pm_three_pod_batch_replay \
  --research-root "$ROOT" --market-root "$MARKET" \
  --propr-postperiod-snapshot "$ROOT/PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json" \
  --hyperx-generations "$BASE/g20261030t1710a" "$BASE/g20261030t1745b" \
    "$BASE/g20261030t1755c" "$BASE/g20261030t1815d" \
  --out "$OUT"
uv run --extra market --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
```

This retains the existing PM-01 cost/virtual-book logic and ML4T native
minute OHLCV lake; **it is not a verified `ml4t-backtest`/
`ml4t-diagnostic` full-account qualification.**
