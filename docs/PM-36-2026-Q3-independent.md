# PM-36: independent wallet July–September 2026 research

**Status: historical source evidence verified / independently anchored episode
replay exploratory / whole-wallet follower and challenge qualification BLOCKED.**

This supersedes using the 16.9-hour October common window to judge how 36
wallets performed over July–September. It does **not** supersede PM-01's strict
whole-wallet follower acceptance, PM-02's qualification policy or PM-03's
independent account-risk supervisor.

## Study contract and dates

- **Interval:** `2026-07-01T00:00:00Z` inclusive to
  `2026-10-01T00:00:00Z` exclusive = **92 calendar days**, not exactly 90.
- **Universe:** 36 original + Wave 1 + Wave 2 Hyperliquid source wallet aliases.
- **Source:** original authenticated immutable HyperX per-instrument fill pages
  (with reported `closed_pnl`, `fee` and `fee_token`), verified W019/LIT
  generation and four previously SHA/identity-verified gap-recovery generations.
- **Market:** SHA/venue/symbol-verified Hyperliquid 1-minute Parquet in the
  owner-held `ml4t-data` lake. No Binance substitute.
- **Analysis:** every wallet **independently** for the fixed 92-day interval;
  no requirement that all 36 have a single simultaneous valid full-book
  follower replay. Missing data or unobserved positions never mean zero P&L.
- **Compliance:** post-period Propr public display-list snapshot is dated
  October 30, 2026 and cannot establish which assets were tradeable in the
  study period. HIP-3 matches are tentative, not verified broker order IDs.

## Tier A: all 36 source wallets' vendor-reported realized fill economics

`closed_pnl - fee` on fill events *dated within the interval*. These are
**reported realized cashflows, not account returns**, not total P&L including
funding and unrealized positions, and not hypothetical follower P&L. Source
closed PnL may recognize profits/losses on inventory opened **before July 1**;
positions still open on October 1 may carry substantial unrecognized P&L.

**Verified 46,314 quarter fills** across all 36 identities (source pages and
supplemental generation identities reconciled). Three-month event-flow total,
**summed across independent and differently sized source accounts**, was
+1,026,171.12996924 USDC. **This sum is not the P&L of any investable combined
portfolio.** No source collateral/equity denominator or exact account
funding reconciliation was available.

| Source month | Fill events | Sum of vendor-reported realized after-fee cashflow (USDC) |
|---|---:|---:|
| July | 7,998 | +236,392.17 |
| August | 15,344 | +332,805.86 |
| September | 22,972 | +456,973.10 |

### Complete 36-wallet descriptive ledger

Amounts are USDC, rounded to cents. Dollar amounts **must not** be ranked as
skill across different manager account sizes.

| Wallet | Quarter fills | Days with fills | Reported closed PnL minus fill fees |
|---|---:|---:|---:|
| EQ-001 | 3,179 | 52 | +298,767.83 |
| VS083 | 800 | 38 | +68,851.28 |
| CA-008 | 1,780 | 70 | +67,592.89 |
| CO-001 | 2,902 | 75 | +64,534.83 |
| VS073 | 942 | 25 | +61,873.15 |
| VS056 | 3,321 | 63 | +57,421.95 |
| W019 | 4,711 | 75 | +49,076.97 |
| W016 | 1,214 | 60 | +40,587.62 |
| VS077 | 740 | 34 | +32,216.17 |
| W015 | 628 | 38 | +31,177.28 |
| VS033 | 4,223 | 76 | +30,659.70 |
| W022 | 670 | 61 | +27,333.46 |
| VS068 | 1,941 | 54 | +26,338.06 |
| IX-004 | 2,353 | 40 | +23,767.42 |
| W030 | 1,940 | 53 | +21,076.15 |
| VS066 | 1,221 | 58 | +20,885.86 |
| VS042 | 1,335 | 44 | +16,972.35 |
| W023 | 918 | 34 | +16,881.71 |
| CA-005 | 1,847 | 55 | +16,595.14 |
| W037 | 278 | 39 | +13,600.96 |
| W026 | 1,041 | 51 | +9,658.43 |
| W028 | 1,425 | 43 | +6,618.25 |
| W031 | 672 | 43 | +6,328.89 |
| W032 | 962 | 60 | +5,147.50 |
| IX-003 | 949 | 48 | +3,772.94 |
| W033 | 559 | 43 | +2,247.72 |
| W035 | 388 | 50 | +2,208.96 |
| W036 | 451 | 54 | +1,857.98 |
| W041 | 517 | 72 | +664.17 |
| W043 | 242 | 29 | +600.21 |
| W045 | 733 | 25 | +483.64 |
| W044 | 200 | 42 | +397.73 |
| W047 | 129 | 35 | +215.39 |
| W042 | 431 | 43 | +176.27 |
| W048 | 105 | 45 | +65.30 |
| CM-005 | 567 | 53 | -483.05 |

The immutable audit also includes every wallet's three monthly slices,
daily realized cashflows on **days with fills**, turnover proxy, signed
reported fees, first/last reported fills, and source-chain gap counts.
Cashflow drawdown is **not** a mark-to-market equity drawdown.

## Tier B: 92-day independently anchored follower-episode replay

Farthest defensible *per-instrument* start is a directly observed flat
inventory, not the much later first-known appearance of every instrument
in the full hindsight roster. We select contiguous **flat-to-flat**
episodes **opening and closing inside the fixed study**, without filling
unknown periods or interpolating missing prices. Unobserved carry-in
positions, unresolved flips, cross-instrument hedges and positions carried
out of the quarter are outside this experiment.

An independent episode is notionally capped at **100 USDC gross exposure**,
using PM-01's modeled taker fees, half-spread, slippage, funding stress and
5% minute-traded-volume proxy limit. The source's future vendor event
timestamp is used as a historical action oracle, **not** proof that the
follower could observe the trade then. The matching always-long control
uses the same symbols and available execution minutes.

| Historical delay | 1,754 eligible closed source episodes | Modeled executable | Blocked |
|---|---:|---:|---:|
| 5m | 1,754 | 1,034 | 720 |
| 15m | 1,754 | 995 | 759 |
| 60m | 1,754 | 964 | 790 |

All 36 wallets have *some* executable modeled completed episodes. Blockers
include unavailable exact market minute and insufficient ex-post volume
participation. The replay consumed **1,792 independently SHA-checked venue-
exact 1-minute instrument-day partitions**.

The **795 identical episodes** that passed all three delays provide a
properly paired latency comparison, but still NOT a whole wallet or portfolio:

| Delay | Sum of hypothetical completed-episode net (USDC) | Incremental vs matched always-long (USDC) |
|---|---:|---:|
| 5m | +2,527.61 | +149.83 |
| 15m | +2,525.41 | +167.26 |
| 60m | +2,466.20 | +185.61 |

These are **sums of isolated 100-USDC episode simulations**. They do not
enforce a shared account gross-notional budget across concurrent episodes,
do not allow risk allocation proportional to each wallet's account equity,
and cannot be converted to a 92-day prop challenge equity curve.

**Critical selection bias:** selecting only episodes that complete
flat-to-flat inside the quarter excludes unknown and outstanding losses,
which can materially overstate skill. The 36-wallet cohort itself was
selected with later information (survivorship/selection bias). No
out-of-sample statistical claim follows.

### Five exploratory research priorities (not active wallets)

Post-hoc *screen only*: at least 20 episodes executable at **all 5/15/60m**
and positive incremental PnL against matched always-long at **all** delays.
This condition was not preregistered, has not been multiple-test corrected
and does not prove alpha or manager independence.

| Wallet | Matched 5/15/60m episodes | Incremental 5m | Incremental 15m | Incremental 60m |
|---|---:|---:|---:|---:|
| W028 | 106 | +7.46 | +7.76 | +6.06 |
| W042 | 40 | +38.10 | +47.62 | +53.32 |
| W022 | 36 | +1.30 | +1.49 | +3.03 |
| W030 | 32 | +13.03 | +5.76 | +7.58 |
| W044 | 25 | +15.27 | +19.94 | +19.50 |

All figures USDC on independent 100-USDC-episode research caps. The
unverified Propr/DEX scope matters: among 2026Q3 source fills, W030 had
1,901/1,940 exact native crypto *display* matches, but W022 had 385/670
strict matches and 148 records under other unverified DEX namespaces.
These snapshots were gathered October 30, **after** the evaluation interval.
Do not silently drop a manager's absent hedge instruments and call it
faithful whole-wallet following.

## Remaining blockers for a credible 92-day challenge-pass estimate

1. Collect historical **account equity/starting collateral**, funding,
   deposits/withdrawals and start/end open position marks for each wallet.
   Report actual 92-day whole-wallet return and NAV drawdown only after
   independent reconciliation. Do not represent a closed-PnL cashflow as ROI.
2. Construct and audit 92-day **hypothetical follower NAV paths** using
   truly observable signals, venue-exact order IDs and realistic broker
   costs. Neither historical source fill time nor an arbitrary 5-minute
   lag supplies a verified first-known copy timestamp.
3. Observe or explicitly stress **concurrent gross, joint order-book
   capacity, hedges, partial fills and cross-wallet netting**. Independently
   modeled episodes do not automatically sum into a feasible follower book.
4. Fit risk budgets and choose pods only on earlier chronology; evaluate
   OOS/forward, time-series dependence, correlated-tail losses and
   multiple-testing controls. A 92-day *in-sample* post-hoc shortlist
   cannot authorize trading.
5. Freeze and verify exact **Propr** stage rules, equity-vs-balance floors,
   daily resets, stop conditions and instrument IDs. Then use PM-03 to
   simulate the central challenge equity, not the single-manager source
   PnL series.

**Decision:** Five PM-02 actionable seats remain EMPTY; 0 qualified
prospective copyable wallets; no challenged account trades or order
authorization. The synchronized October 16-hour diagnostic remains a
distinct experiment and should not be used as the 92-day wallet ranking.

## Artifacts and reproduction

Immutable owner-private content-addressed report files on the VPS:

- Source after-fee fill audit: SHA-256
  `57f4eb4e6b5abdb755a4ee599ba224d5e451e240dd2c78cf202cd764f17a93e9`,
  `pm36-2026q3-fills-57f4eb4e6b5abdb755a4.json`.
- Flat-to-flat delayed episode audit: SHA-256
  `0f10be09d577bfef9e749f258e34fe00acc2f13667c2e9180671dda8da66732b`,
  `pm36-2026q3-episodes-0f10be09d577bfef9e74.json`.

Private directory:
`/home/quant/.local/share/copytrade/reports/pm36-q3-independent/`.

```sh
ROOT=/home/quant/.local/share/copytrade/reports/five-pod-20261029-research
MARKET=/home/quant/dev/quant/ml4t-data/.data/store
BASE=/home/quant/.local/share/copytrade/reports/pm01-hyperx-gaps
OUT=/home/quant/.local/share/copytrade/reports/pm36-q3-independent
# Explicit individual paths avoid unsafe shell word splitting.
uv run --extra market --group dev python -m copytrade_pm.pm_quarter_fill_audit \
  --research-root "$ROOT" \
  --hyperx-generations "$BASE/g20261030t1710a" "$BASE/g20261030t1745b" \
    "$BASE/g20261030t1755c" "$BASE/g20261030t1815d" --out "$OUT"
uv run --extra market --group dev python -m copytrade_pm.pm_quarter_episode_replay \
  --research-root "$ROOT" --market-root "$MARKET" \
  --hyperx-generations "$BASE/g20261030t1710a" "$BASE/g20261030t1745b" \
    "$BASE/g20261030t1755c" "$BASE/g20261030t1815d" --out "$OUT"

uv run --extra market --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
```

ML4T components: native `ml4t-data` price lake and existing
PM-01 event-driven research follower cost engine. This is **not**
`ml4t-backtest` or `ml4t-diagnostic` scientific qualification.
