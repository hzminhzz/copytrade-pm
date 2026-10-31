# PM-36 synchronized historical challenge diagnostic (2026-10-31)

**Status: ENGINEERING RESEARCH ONLY. Not PM-03 acceptance, not ML4T-backtest
production integration, not a prospective signal, not a qualified prop challenge
pass probability. No live orders, credentials, account promotion, or deployment.**

## Question and result

Can independently replayable wallets among the frozen 36 be combined into a
synchronized challenge equity curve, rather than adding unrelated whole-window
terminal P&L?

**Yes, for a small, strictly labeled retrospective common window.**
The integrated private replay uses the historical HyperX fill cache and
SHA-verified native Hyperliquid 1-minute OHLCV from `ml4t-data`. It
reconstructs four fully completed 0.1%-gross hypothetical PM-01 books and
revalues them at exactly the same 1-minute opens.

**No, for scientific 30-day wallet-selection or a pass-probability claim.**
At the frozen source cutoff `2026-10-29T17:22:16.142Z`, the full roster
has 36 wallets, but only four wallets completed 5/15/60m historical replay
at this small size; only W022 has >=30 days of its own completed source
window. Thus **zero pairs or larger combinations have 30 days of common
completed replay**. At larger tested 1% and 10% gross sizes even fewer
scenarios complete. Censored or missing paths are NOT zero returns.

### Exact frozen inputs

- Sealed 0.1%-gross PM-01 replay full SHA-256:
  `bdd19a47c2fa0e1695cd4f5548118f8c2ad8c31bb72a3eb9e49e06ef35d92766`
- Includes four independent SHA-verified HyperX gap-recovery generations;
  original pages remain immutable.
- The wallet cohort retains 6 original + 10 wave1 + 20 wave2 aliases.
- Replay parity checks compare each reconstructed source-anchor time, final
  modeled P&L, and number of fills against the exact sealed PM-01 report.
- Minute-bar files are independently SHA-verified before price/volume use.
  No Binance substitution or unverified HIP-3 identity remapping.

### Synchronized exploratory output

The synthetic research rule assumptions are **10% profit target, 3% daily
loss, 6% static loss, UTC daily reset on a hypothetical $100,000 account**.
These are not contractual, independently attested Propr rules. Per-wallet
baseline notional is at most **0.1% of account initial capital ($100)** at
each PM-01 rebalance, including modeled fees, spread, slippage, funding, and
per-minute volume participation checks.

| Historical delay | Shared 1m opens | Common period (Oct 29 UTC) | Portfolio scenarios | Sampled target touches | Sampled floor breaches |
|---|---:|---|---:|---:|---:|
| 5 minutes | 1,007 | 00:36–17:22 | 30 | 0 | 0 |
| 15 minutes | 997 | 00:46–17:22 | 30 | 0 | 0 |
| 60 minutes | 952 | 01:31–17:22 | 30 | 0 | 0 |

Across each delay: evaluate all nonempty subsets of four candidates (15)
under two policies: fixed tested notional *per wallet* and fixed tested
notional *total*. This is **90 trial paths, not 90 independent samples**.
No five-wallet combination is evaluable. All result labels are
`OBSERVED_PATH_NOT_PASSED`; the remaining target horizon is unknown.
These outcomes are **not 0% empirical pass probabilities**.

The largest end equity among the 30 exploratory scenarios on each delay
was $100,019.79 (5m), $100,021.60 (15m), and $100,025.38 (60m).
The sample-max ending equity is a **post-hoc selection artifact** and
must not be used as a prediction or manager ranking. At 5m, the
2-wallet subset W022+VS077 and the 3-wallet W022+W019+VS077 have
identical ending equity in this window; including W019 was not incremental.

Content-addressed private outputs:

- 5m `55534f6ee8353440d1d26dc569da6a257a9d33816787be06a87dde25cdccc013`
- 15m `2ef3c0d52eda819bfe78b4afe4e8cbc8673cab09bd5547d7ddfecec59cad7de5`
- 60m `740bd743709c4d55a74fcc95502899e9eea084777e66afd273439439d12cd843`

All private artifacts reside under
`/home/quant/.local/share/copytrade/reports/pm36-sync-research/`.
They are intentionally outside Git. Results and underlying raw wallet
addresses are not copied into code or public artifacts.

## Design and strict boundaries

- `pm_fill_replay.replay_wallet(record_path=True)` adds an **opt-in**
  historical virtual-book snapshot series. The default frozen PM-01 v2
  consumer output is unchanged. A row without complete economic execution
  cannot produce a successful path.
- `pm_synchronized_challenge` validates the complete 36×3 PM-01 cohort,
  provenance SHA, and historical knowledge prohibition. Reconstructed
  books are marked at each available common 1-minute open. A missing
  exact instrument-minute blocks the whole synchronized series.
- Only directly executed modeled wallet actions appear in virtual-book
  positions; between actions the position is marked using the observed
  minute-open. Conservative synthetic funding is projected between actions.
- Shared equity is recomputed from source virtual P&L relative to the
  common starting mark (not improperly summed from differing source anchors).
- Stop events are detected from sampled equity against illustrative daily
  and static floors. **Intraminute price extrema, live bid/ask queues,
  margin/partial fills, exact prop rule enforcement, and broker HALT
  recovery are not modeled.** Individual-wallet minute-volume checks
  do not establish joint order-book capacity or central cross-wallet
  netting economics. Thus even zero sampled breaches is not a verified
  zero breach count.
- `MAX 30-day` gate is a feasibility screen, not evidence of statistical
  sufficiency. No cross-validation, DSR/PBO, or untouched holdout is
  claimable because the common history is shorter than 1 day.
- The code uses native `ml4t-data` market sources via existing PM-01
  adapters. It **does not claim to run `ml4t-backtest` or
  `ml4t-diagnostic`** on this insufficient sample. Once data qualifies,
  those tools should support event-driven OOS execution and diagnostic
  validation; they cannot repair missing wallets or source timestamps.

## Reproduce on the VPS

```bash
cd /home/quant/dev/copytrade-pm  # or this feature worktree
ROOT=/home/quant/.local/share/copytrade/reports/five-pod-20261029-research
MARKET=/home/quant/dev/quant/ml4t-data/.data/store
BASE=/home/quant/.local/share/copytrade/reports/pm01-hyperx-gaps
PM01=/home/quant/.local/share/copytrade/reports/pm01-36-shadow/pm01-36-wallets-bdd19a47c2fa0e1695cd.json
OUT=/home/quant/.local/share/copytrade/reports/pm36-sync-research

uv run --extra market --group dev python -m copytrade_pm.pm_synchronized_challenge \
  --pm01 "$PM01" --research-root "$ROOT" --market-root "$MARKET" \
  --hyperx-generations "$BASE/g20261030t1710a" \
    "$BASE/g20261030t1745b" "$BASE/g20261030t1755c" \
    "$BASE/g20261030t1815d" --lag 5 --max-minutes 1500 --out "$OUT"
# Repeat --lag 15 and --lag 60
uv run --extra market --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
```

## What is required to establish a useful combination

1. Complete and reconcile the **real source whole-account book**, hedges,
   collateral, costs and Propr exact instrument mapping; acquire missing
   native minute data and actual executable depth.
2. Collect **genuine first-known prospective observations** to prevent
   copying before a trade became visible. Historical HyperX timestamps
   cannot be transformed into first-known receipts by adding five minutes.
3. Collect enough overlapping calendar history and independent economic
   episodes; estimate joint tail risk and compare portfolio sizing policies
   with walk-forward/OOS trials, multiplicity controls, and independent
   holdouts. The initial 30-day test is a minimum *availability* condition,
   not an acceptable confidence threshold.
4. Use versioned **official confirmed Propr** challenge rules and a
   complete PM-03 account simulator with floating-P&L floor detection,
   execution/margin accounting, and durable HALT replay before any
   probability-of-passing estimate.
5. Keep five PM-02 research seats EMPTY and live risk at zero until
   scientific qualification is genuinely supported.
