# ML4T-66 Barbell Phase 2: Expanded protected 3–5-pod research

**Run date:** 2026-11-06 UTC. **Classification:** HISTORICAL_EVENT_ORACLE_UNQUALIFIED / NO_TRADE. **Source:** owner-private SQLite v8; 214 registered research wallets, 66 members of sealed `ml4t-strict-66` cohort. The Phase 2 study expands 10 selected cohort wallets; the complete 214-wallet catalog was **not** retrospectively replayed.

**Headline:** 66 additional protected combinations tested over a separate 45-calendar-day period, including 36 three-pod, 24 four-pod and 6 five-pod policies; **zero modeled +10% target touches**. Of the 66, **13** satisfy the $400 after-the-fact, 1.5x co-worst-day stress diagnostic. This is not an independently verified pass-probability result.

## Research inputs and exact time separation

- **Risk calibration:** August 5 00:00 UTC–September 19 00:00 UTC (45 calendar days).
- **Separate historical follow-up:** September 19 00:00 UTC–November 3 00:00 UTC (45 days).
- **Follower start:** $10,000, zero inventory. In the separate period, new follower fills are admitted only once a source fill for that specific wallet+coin has an **observed pre-fill zero position after September 19**. Unobserved opening inventory is never inferred. This is a *per-coin* counterfactual, not a full wallet book.
- **Sources:** original SHA-verified local fills + native 1-minute verified market panels, 10 wallets in study (anchors H34/M55/M51/M22; runner-slot candidates H36/M40/M50/M58/M32/M29). 25,589 historical first-zero-filtered source fill events were available; 14,080 source fill events retained after the further September 19 flat-entry gate, with 876 post-split records skipped by that gate. Fill-event counts are not economic trades.
- **Sizing:** k is calibrated on 45-day maximum adverse intraday and cumulative excursions using a 1.5x stress multiplier and $10 per-pod buffer. Training co-worst aligned shock is capped at $400. Per-pod lifetime/daily budgets depend on portfolio size and role.
- **Protected replay:** first-event +5m anchored batches, strict next full UTC minute OPEN, taker 3.5 bps plus adverse slippage 2.5 bps per executed side, independent pod hard-stop latch (daily or cumulative) and modeled next-minute-open forced exit with costs, with zero automatic restart. Alternate 2m delay and 12/18 bps costs checked on the 10 top-screen portfolios.
- **Account barrier scenario:** +$1,000 target, 5% intraday-HWM daily loss, 10% continuous trailing HWM; low/high adverse scenario checked against the **previous observed minute** floor, close against the updated close floor, avoiding fictional same-bar OHLC order. This is a user-provided scenario, **not a verified Propr rule snapshot**.
- **Critical limitations:** First-known actual receipts, historical as-of source equity/NAV, complete DEX/subaccounts, initial full books, liquidation, funding, broker netting, bid/ask depth, capacity, adverse gaps longer than 1m, quote-side slippage and genuine OOS wallet selection are **not proven**. New wallet selection and eventual stress ranking use knowledge from the full sample; the 45-day holdout **is not an untouched independent scientific holdout**.

## Role-specific budgets

| Study | Anchor count | Runner count | Daily pod limits | Lifetime pod budgets | Unassigned lifetime budget |
| --- | ---: | ---: | --- | --- | ---: |
| 3-pod | 2 | 1 | $120/$120/$100 | $200/$200/$150 | $50 |
| 4-pod | 3 | 1 | $90/$90/$90/$100 | $130/$130/$130/$180 | $30 |
| 5-pod | 3 | 2 | $75/$75/$75/$70/$70 | $120/$120/$120/$100/$100 | $40 |

Account and pod limits are **modeled hard stops**, not guaranteed maximum realized losses. No pretrade gross cap or funded contract payout lifecycle was simulated.

## Top 13 risk-compatible historical scenarios

These 13 stay at or below the **$400 hindsight-aligned** 1.5x co-worst historical stress bound. All ended the 45-day study without touching +$1,000. Dollar PnL and drawdown are historical modeled **net follower** results on a fresh $10,000 account, not actual trading evidence. 5m, 6 bps/side.

| # | Portfolio: anchors / runner(s) | Modeled net PnL | Max observed DD | 1.5x co-worst stress |
| --- | --- | ---: | ---: | ---: |
| 1 | M55 / M22 / **M58** | +$224.05 | $57.10 | $293.80 |
| 2 | M55 / M22 / **M50** | +$220.24 | $56.26 | $327.03 |
| 3 | M55 / M22 / **H36** | +$215.55 | $104.16 | $325.58 |
| 4 | H34 / M55 / M22 / **M58** | +$139.70 | $64.44 | $329.27 |
| 5 | H34 / M55 / M22 / **M50** | +$137.43 | $56.35 | $362.22 |
| 6 | H34 / M55 / M22 / **H36** | +$133.45 | $102.95 | $345.23 |
| 7 | H34 / M55 / M22 / **H36 + M58** | +$113.05 | $62.79 | $312.83 |
| 8 | H34 / M55 / **M58** | +$112.92 | $69.31 | $293.80 |
| 9 | H34 / M55 / **M50** | +$109.11 | $61.25 | $327.03 |
| 10 | H34 / M55 / **H36** | +$104.42 | $109.17 | $325.58 |
| 11 | H34 / M22 / **M58** | +$34.34 | $63.75 | $293.80 |
| 12 | H34 / M22 / **M50** | +$30.52 | $55.87 | $327.03 |
| 13 | H34 / M22 / **H36** | +$25.84 | $121.19 | $325.58 |

This table is a **descriptive ranking within the researched combinations**, not a recommendation to register, run or trade any portfolio. The 5-pod challenger uses two runners to explore the upside/risk tradeoff.

### Illustrative k factors from calibration-only sizing

- **3-pod M55/M22/M58**: M55 `0.011954150`, M22 `0.012073398`, M58 `0.002436930`.
- **4-pod H34/M55/M22/M58**: H34 `0.001174636`, M55 `0.008693928`, M22 `0.008742367`, M58 `0.002959129`.
- **5-pod H34/M55/M22/H36/M58**: H34 `0.000954391`, M55 `0.007063816`, M22 `0.007134280`, H36 `0.005023557`, M58 `0.001566598`.

These figures are not orders or live follower quantities. Static source-equity scalars are not independently attested point-in-time NAV, and a true whole-book replica requires re-verification at decision time.

## Execution sensitivity: three strongest stress-compatible trios

| Portfolio | 2m / 6bps | 2m / 12bps | 5m / 6bps | 5m / 12bps | 5m / 18bps |
| --- | ---: | ---: | ---: | ---: | ---: |
| M55/M22/M58 | +$231.91 | +$181.39 | +$224.05 | +$173.46 | +$122.86 |
| M55/M22/M50 | +$225.73 | +$177.70 | +$220.24 | +$172.00 | +$123.77 |
| M55/M22/H36 | +$206.75 | +$139.41 | +$215.55 | +$148.33 | +$81.11 |

**M58 vs M50:** both generate nearly the same historical net PnL and downside. M58 has lower co-worst stress ($293.80 vs $327.03); M50 retains similar PnL at 18bps. Neither meets the previously proposed **runner skew >+1** research filter: their prior retrospectively sized 4h skew diagnostics were M58 +0.149 and M50 +0.481. H36's was +0.301. These skew figures are **not** independently verified source-account moments. None is currently a scientifically qualified convex runner.

## Higher-return but not $400-stress-compatible barbell variants

| Portfolio | 5m net PnL | 1.5x worst-day stress | Verdict |
| --- | ---: | ---: | --- |
| M55/M22/**M29** | +$374.75 | $429.33 | Above proposed internal ceiling |
| M55/M51/**M29** | +$343.04 | $786.69 | Above $500 contractual daily allowance |
| M55/M51/M22/**M29** | +$336.09 | $664.15 | Above $500 contractual daily allowance |
| H34/M55/M22/**M29** | +$292.65 | $448.98 | Above internal ceiling |
| M55/M22/**M32** | +$245.43 | $624.48 | Above contractual daily allowance |
| M55/M22/**M40** | +$224.11 | $608.39 | Above contractual daily allowance |

These were not validated in the higher-cost sensitivity shortlist. Their positive historical PnL is **not** grounds to override risk limits.

## Decision and next research

**EXPERIMENT, no portfolio freeze.** Three-pod bars generally achieved larger protected historical PnL than four- and five-pod alternatives at these conservative per-pod risk budgets. The maximum stress-compatible modeled gain was only **+$224.05** in 45 days. Do not extrapolate a 45-day descriptive gain into a 60-, 90- or 180-day probability.

Higher priority than further in-sample combination tuning:

1. Obtain authoritative parent/subaccount source books, as-of NAV, first-known follower receipt clocks and native quote-side TCA, then build complete synchronized P&L tapes.
2. Restore a *genuine* untouched prospective selection period (separate from wallet selection and k calibration); collect 14–30 days of independent bounded paper receipts.
3. Run at least one separately versioned protected replay with enforced pretrade gross and concentration caps and measured stop-to-flatten gaps.
4. Only after complete net follower tape and verified rules, call native `copytrade-pm contracts compare` to estimate pass odds/contract EV. That tool currently returns **BLOCKED: MISSING_COMPLETE_NET_FOLLOWER_MTM_TAPE** for saved comparison portfolios.

### Reproduction

```bash
uv run --frozen --extra market --group dev python scripts/ml4t66_barbell_protected_oos.py \
  --db /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --source-root /home/quant/dev/copytrade-pm/data \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --output-root /home/quant/.local/share/copytrade/reports/barbell-20261106
```

**Immutable private report:** `/home/quant/.local/share/copytrade/reports/barbell-20261106/ml4t66_barbell_protected_oos_4efbccf2edba18f4085e.json`

**SHA256:** `4efbccf2edba18f4085ec51da4fa66805fadc68751a4581bf240f094daa4dcb8`

No SQLite mutation, production worker deployment, brokerage order, contract purchase or research portfolio registration was performed. Code verification evidence is separate from financial qualification.
