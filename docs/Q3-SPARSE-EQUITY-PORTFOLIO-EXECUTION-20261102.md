# Executed Q3 sparse-equity three-pod replay — 2026-11-02

**Disposition:** EXECUTED / ENGINEERING REPRODUCIBLE / HISTORICAL PROXY ONLY. No complete source-wallet equity-relative follower PnL, no validated best 3-wallet portfolio, no demonstrated prop-challenge pass probability, no trade authorization.

This research executes the **user's actual sizing equation** (`source signed quantity × allocated pod capital / prior observed source wallet equity`). It does **not** size each fill as an independent trade or substitute source-gross normalization for source equity. Exact copied *intent* is different from the risk-approved and hypothetically executed inventory.

## Objective, clock, and experimental design

- Frozen A = W028 + W042 + W030; B = W044 + CA-005 + W031; C = CO-001 + W015 + VS066.
- Fixed Q3 comparison: **July 1–October 1 exclusive UTC = 92 days** (the original comparable Q3 window; do not call it exactly 90 days).
- $10,000 initial shared PM03 account; each of three source wallet pods allocated $2,000. Research cash not allocated to pods = $4,000; **this is not leverage-free account exposure**.
- Native SHA-attested Hyperliquid minute **open** prices, five-minute hypothetical delay after source vendor event, one reconciled three-pod PM03 ledger, internal crosses. Assumed 5bp fee, full spread 3bp, slippage 5bp and a conservative 1bp/8h funding debit, with 2× cost stress.
- Explicit synthetic gross limits **$6,000 per pod / $18,000 account / $9,000 instrument**, and synthetic 3% daily loss, 6% static loss, 10% profit target. These are *research policy*, **not** verified account terms.
- Two historical source-equity carry policies: latest **prior** positive official `perpAllTime.accountValueHistory` sample no more than **8 days** (base), or **16 days** (stress). No interpolation from future samples. Source equity updates trigger a new 5-minute-lagged **whole-position target vector** even without a source fill. Zero/stale/missing NAV means skip the sizing **decision**, retain previous follower holdings and explicitly count the missed target; verified source flat events still close.
- Source portfolios use only directly observed *completed* flat-to-flat instrument episodes from immutable HyperX fills, screened to the October 30 Propr public display scope and native verified 1m day eligibility. This is **post-hoc source/market availability selection bias**, not a complete source-wallet book. Some source hedges and starting inventory are unknown.
- A missing one-minute price is never magically a new bar. **Only for exploratory holding marks**, carry a prior SHA-verified native bar open for at most 180 minutes while recording bar-age and frequency; **never fill an order at that carried price**. This enabled C to progress past the 155-minute observed `xyz:MU` July 7 quote gap. No intragap excursion is measured.
- Base-case capacity diagnostics flag orders above 5% of their **same-minute final quote volume**; this diagnostic is **noncausal** and never controls base-case execution. The independent *enforced* scenario uses **only the previous completed minute's quote volume**, available at the hypothetical order's minute open, and **skips** orders above 5% of that volume. A missing preceding minute means no authorized hypothetical capacity. This review fix prevents same-bar future-volume leakage into execution. Neither minute-volume proxy attests executable Propr order-book liquidity.

## A/B/C observed outcomes

| Portfolio | Base $ PnL at modeled stop | Modeled outcome and date | Simulated max observed DD ($) | Simulated gross-risk veto batches |
| --- | ---: | --- | ---: | ---: |
| A | **+847.40** | Q3 end Sep 30; unresolved follower positions at cutoff | 304.14 | 727 |
| B | **+1,001.42** | Synthetic +10% target Aug 21 01:29 UTC | 245.25 | 36 |
| C | **-24.20** | Synthetic daily drawdown breach Aug 13 13:35 UTC | 349.43 | 59 |

**A's $847 profit is not evidence that its source portfolio was copied.** Action-weighted absolute exposure tracking deviation is W028 **100%**, W042 **~100%**, W030 **90%**; PM03 vetoed 727 source-target batches. B's deviations: W044 **15.6%**, CA-005 **12.6%**, W031 **41.4%**. C: CO-001 **18.9%**, W015 **77.6%**, VS066 **29.6%**. This is **simulation target-vs-executed exposure** at decision times, not real-world copy fidelity or a time-weighted ratio. The stale/missing source NAV updates that never generated targets are counted separately and are not in this denominator.

Under 2× costs: A +$766.39 unresolved at end; B +$1,004.83 hits the modeled target later; C -$94.77 breaches daily drawdown earlier. Under 16-day previous-NAV carry: A +$775.53 unresolved; B hits the target Aug 21; C breaches Aug 13. With 5% of the **previous completed minute's** quote volume *capacity enforced*, A **+$838.01** unresolved at Q3 end, B **+$1,007.07** hits the modeled target Aug 21, C **−$54.06** breaches daily drawdown Aug 13. **None is verified executable.** Earlier same-minute-volume capacity results are retained only as superseded noncausal research.

## All 84 unique three-wallet combinations

The original three + **81 additional combinations** of the same nine wallets were executed with identical base conditions in seven bounded source-verified batches; SHA-consolidated results are available for all 84. Outcomes are **conditional, hindsight and not independent tests**:

| Outcome of base three-wallet simulation | Combinations |
| --- | ---: |
| Modeled first passage of +10% profit target | **49** |
| Synthetic drawdown breach | **22** |
| Q3 end with unresolved follower open inventory | **7** |
| Interrupted by missing exact market price | **6** |
| Total | **84** |

**Do not interpret 49/84 as a challenge-pass probability**. These combinations share wallets and historical shocks, were evaluated and selected on the **same Q3 data**, omit unobserved source positions/market exposure, and use insufficient source-equity clocks.

### Three promising *conditional research* trios

All three reached the synthetic +10% first-passage threshold in the base, 16-day-NAV, 2× costs, and capacity-enforced scenarios. Their selection is purely for more research, **not** a qualification or live recommendation.

| Combination | Base target hit | Capacity-enforced target hit | Capacity-blocked hypothetical order attempts | Worst capacity-stress pod tracking error |
| --- | --- | --- | ---: | ---: |
| W030 / W044 / VS066 | Aug 17 | Aug 20 | 156 | ~66% (W044) |
| W030 / W044 / CO-001 | Aug 19 | Aug 21 | 215 | ~73% (W044) |
| W044 / CA-005 / CO-001 | Sep 9 | Sep 17 | 217 | ~34% (W044) |

**Highest-priority follow-up for paper/shadow research:** W044 + CA-005 + CO-001. It is the lowest sensitivity to the defined volume-capacity stress of these three; all three source legs remain represented in the modeled book. It is **not** a verified winner. In particular W044's official master NAV has a zero historical observation, CA-005 and CO-001 may have other subaccount exposures, and the 217 blocked *order attempts* exceed the few occasional skipped follower trades envisaged by the user. Some capacity attempts may represent repeats, not distinct original source fills.

W030 + W044 + VS066 is an alternative, with earlier modeled first passage, fewer executed orders, but sparse VS066 source NAV (only seven Q3 samples) and substantially worse W044 exposure tracking when capacity is enforced.

## Evidence and reproduction

Private, immutable SHA-addressed report root:

`/home/quant/.local/share/copytrade/reports/q3-sparse-equity-weighted-20261102/`

**Consolidated 84-combo + selected-sensitivity summary (post-review):** `pm01-36-wallets-67c12a0dd37b7983041b.json`, full SHA256 `67c12a0dd37b7983041b7f669efc77cc3b11a20f42980fa6a2ab42b7e43259be`. It cryptographically checks the SHA-addressed base report, all seven disjoint mixed batches and all three custom sensitivity generations, matching source SHA maps, Propr screen, account policy, and market settings.

Re-reviewed A/B/C + 4 scenarios: `pm01-36-wallets-0b09e40f94cf811cbffb.json`. The 81 unchanged **base-case** mixed results are reused from their original immutable generations (the base-case sizing/execution logic did not change). All 81 mixed:
- 0: `f0743653602e054136eb`
- 12: `05235dc15776c48b1b7e`
- 24: `32ef3cdf82293731550e`
- 36: `53f9bd5a7faaa38df5df`
- 48: `e287ae161215698808bb`
- 60: `465f9074ea79b0be71ed`
- 72: `b9f5054dafb14ab389be`

Re-reviewed selected stress experiments (4 scenarios each): `ae4d1840a60db674be3a`, `98972150ae7176f368da`, `54f3fe4d3b1babbcbfeb`, respectively. The pre-review reports remain privately immutable and **must not** be used as causal capacity results. All file names use `pm01-36-wallets-<20 SHA hex>.json`.

```bash
# Base frozen A/B/C; native data and historical equity files remain read-only.
uv run --frozen --group dev --extra market python -m copytrade_pm.pm_sparse_equity_portfolio \
  --research-root /home/quant/.local/share/copytrade/reports/five-pod-20261029-research \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --ab-equity-root /home/quant/.local/share/copytrade/reports/historical-equity-20261102/g20261102equityabv1 \
  --c-equity-root /home/quant/.local/share/copytrade/reports/pm-e4-hyperx-20261031/ge4live20261031first \
  --out /home/quant/.local/share/copytrade/reports/q3-sparse-equity-weighted-20261102

# Additional mixed combinations, 12 per bounded call; final batch has nine:
# append --mixed --only-mixed --mixed-offset 0 --mixed-count 12
# repeat for offsets 12 24 36 48 60 72.

# Selected sensitivity: add --only-combo --combo W044 CA-005 CO-001
```

Aggregation CLI: `python -m copytrade_pm.pm_sparse_equity_summary --base FILE --mixed-batches SEVEN_FILES --custom-runs THREE_FILES --out PRIVATE_DIR`. Refuses missing, duplicated, mismatched-policy or tampered SHA reports.

## Verification limits and decision

This is **implemented exploratory execution**, not a scientifically qualified follower portfolio. Source price marks, source equity at each minute, source account/subaccounts, actual Propr execution capacity, historical first-local receipt clocks and an unused holdout are **not verified**. The original strict equity-replay path remains fail-closed and unaffected; no source history or frozen audit is mutated. The user can accept a few missed follower trades in production, but skipping 100+ capacity attempts is material deviation.

**Suggested next research action, not a production dependency:** Prospectively observe the same selected wallets with complete book, reconciled master/subaccount equity and local receipt timestamps; then run a *new* genuinely OOS shadow period with measured source-to-follower tracking and Propr rules. No live order gateway or capital risk is authorized by these results.
