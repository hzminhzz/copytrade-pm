# ML4T-66: actual combined $10,000 three-pod historical portfolio replay

**Executed:** 2026-11-05 on owner VPS, read-only sources. **Window:** 2026-08-05 00:00 UTC to 2026-11-03 00:00 UTC (end exclusive, 90 calendar days). **Version:** `scripts/ml4t66_portfolio_backtest.py`; 1m/2m/5m, 6/12/18 bps, 3 fixed historical research rosters. **Verdict:** historical event-time **SCREEN_ONLY**; zero trading authorizations, zero scientific qualifications.

## What was actually run

1. Confirm current `ml4t-strict-66` cohort and exact alias-address identity from the owner-private SQLite (66 wallets), merge local SHA-verified source generations **read-only**, and verify native Hyperliquid 1m market Parquet days and sidecar SHA with `_verified_day`. All six wallets from the proposed Explorer/Sprint/control portfolios were in SQLite; original source's missing beginning cannot be inferred.
2. A **new hypothetical follower** starts at $10,000 cash and **zero positions**. For each wallet/coin, only begin copying once an observed historical source fill has `startPosition=0`; earlier fills are censored (one of 10,349 initial source rows). This is an *explicitly distinct event-delta strategy* and **does not reconstruct the full wallet, parent/subaccount, collateral, non-source positions or true opening inventory**.
3. Apply the owner's reference `k_i=(1/3)*min(0.35, 10000/E_leader,scalar)` to each signed leader fill delta. This is **not source-equity-as-of faithful**: leader equity is an untimestamped vendor scalar.
4. Use the existing `anchored_batches` (first event, nonresetting +1/+2/+5m, sum signed per wallet/coin) and **strict next full UTC minute OPEN**. Reject orders below $10. A missing native OPEN is **not a fictitious fill**; record the missing execution, and declare all subsequent financial qualifications unknown. Unpriced *active* minute MTM is NaN, never forward-filled.
5. Maintain **explicit cash + signed positions per pod**, charge 3.5bps taker fee and 2.5/8.5/14.5bps adverse execution slippage for all executed *external* pod deltas (6/12/18bps combined per side), mark total pod equity at SHA-native 1m closes, stress simultaneous adverse 1m low/high, and compute retrospective first-passage against **Explorer** 5% daily / 8% continuous trailing / 10% then 5% targets and **Sprint** 3% daily / 5% EOD trailing / 8% target. The EOD high-water sampling is the corrected B rule v2.
6. A date later than the first skipped execution or first unpriced active position is a **conditional counterfactual**, not a certified valid result. No true broker spread/depth/participation, funding, liquidation, fresh follower first-known clocks, source PIT NAV or actual risk-control fills were observed.

### 6bps combined cost: conservative evidence prefixes

**P&L and max DD in this table are only through the first execution/mark gap**, so **not comparable as equivalent-length portfolio returns**, and not realizable after a modeled contract breach.

| Portfolio | Delay | Time through which cash/inventory was continuously marked | Prefix net P&L | Prefix max DD | Earliest modeled evaluation event |
| --- | ---: | --- | ---: | ---: | --- |
| Explorer: M10 + M33 + M53 | 1m | before Oct 14 00:00 UTC | **+$2,712.96** | **$6,135.38** | Sep 23 08:51 — **BREACH**, before missing data |
| Explorer | 2m | before Oct 14 00:00 UTC | +$2,657.77 | $6,139.02 | Sep 23 10:25 — **BREACH** |
| Explorer | 5m | before Oct 11 00:00 UTC | +$1,842.09 | $6,148.94 | Sep 23 10:25 — **BREACH** |
| Sprint: M52 + M42 + M53 | 1m | before Aug 31 06:51 UTC | +$621.20 | $356.88 | **UNKNOWN**: missing PONS execution |
| Sprint | 2m | before Aug 31 06:52 UTC | +$624.87 | $355.76 | **UNKNOWN**: missing PONS execution |
| Sprint | 5m | before Aug 31 06:55 UTC | +$552.57 | $358.46 | **UNKNOWN**: missing PONS execution |
| Historic leaderboard control M52 + M56 + M10 | 1m | before Aug 31 06:51 UTC | +$199.63 | $151.63 | **UNKNOWN**: missing PONS execution |
| Control | 2m | before Aug 31 06:52 UTC | +$204.06 | $151.23 | **UNKNOWN** |
| Control | 5m | before Aug 31 06:55 UTC | +$183.23 | $150.65 | **UNKNOWN** |

The Sprint prefix ends **before M53 begins trading in September**, so its +$552–$625 prefix P&L is not a fully active three-pod observation. The control's initial $183 profit also precedes its gap; neither certifies its previously reported +72.04% or 0.13% max DD.

### Portfolio first-passage: 5m / 6bps

- **Explorer:** at Sep 23 10:25 UTC the modeled account falls to **$9,998.52**, below its modeled active floor **$9,999.45**. The first market-data risk gap is not until Oct 11. This is a robust **failure of the explicit counterfactual policy**, before missing bar evidence; it does not certify a real broker evaluation outcome. The account later recovers and has +$1,842.09 net through Oct 10, but a prop firm would already have terminated it.
- **Sprint:** first missing execution is PONS Aug 31 06:55 UTC. *If one wrongly assumes skipping missing PONS is safe*, the subsequent counterfactual would breach Sep 1 11:51 UTC at $10,315.55, below a $10,318.55 EOD-trailing reference floor. Since a missed source-relevant fill invalidates the intended follower inventory, **the proper verdict is UNKNOWN, not FAIL or PASS**.
- **Control:** first missing PONS execution Aug 31 06:55. An **omission-counterfactual** touches the Sprint-like $800 target Sep 4 09:07, but this cannot be counted as a contract pass. The previous precomputed +72.04% / 0.13% combination result is **not validated**.

### Cost sensitivity (5m, first intact prefix only)

| Portfolio | 6bps prefix P&L | 12bps prefix P&L | 18bps prefix P&L | First-gap status |
| --- | ---: | ---: | ---: | --- |
| Explorer | +$1,842.09 | +$1,492.82 | +$1,143.55 | Already modeled failed at all three costs |
| Sprint | +$552.57 | +$489.28 | +$426.00 | Unpriceable PONS, cannot qualify |
| Control | +$183.23 | +$156.61 | +$130.00 | Unpriceable PONS, cannot qualify |

**Additional post-gap scenario-only diagnostic:** Under a strict order-omission counterfactual, Sprint 1m and 2m have finite terminal marked outcomes of **−$5,648.26** and **−$5,790.67** respectively (6bps). They do **not** represent attainable portfolio net PnL because PONS executions were skipped as early as Aug 31, and later risk could differ. Sprint 5m and Explorer all delays have unpriced terminal open positions, so final P&L is **null**, never zero.

### Coverage and execution burden (5m, 6bps)

| Portfolio | Modeled orders actually priced | Model fixed fee+slippage, USD | Active market-unpriced calendar days | Max priced gross / initial capital |
| --- | ---: | ---: | ---: | ---: |
| Explorer | 320 | $372.49 | 23 | 9.16× |
| Sprint | 400 | $764.04 | 23 | 8.02× |
| Control | 567 | $886.54 | 20 | 7.17× |

Explorer: **COMP** missing 19 of 37 requested market-days plus one incomplete, and ALGO 18 of 43 missing; first unpriced active leg Oct 11 (5m). Sprint: PONS has one incomplete 1,440-bar daily source, the first affected execution Aug 31. Missing **historical candle days** are not solved by looking at realized leader closed PnL. Large gross leverage and persistent unflattened positions at the cut also invalidate naive tiny DD.

The orders and costs here follow the zero-anchored new-follower policy, so are **not identical** to the earlier unconstrained batch-count inventory in [allocation reassessment](ML4T-66-ALLOCATION-REASSESSMENT-20261105.md).

## Reproduction

From the feature worktree with native market extra:

```bash
uv run --frozen --extra market --group dev python scripts/ml4t66_portfolio_backtest.py \
  --db /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --source-root /home/quant/dev/copytrade-pm/data \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --output-root /home/quant/.local/share/copytrade/reports/ml4t66-batch-recovery-20261105 \
  --scenarios EXPLORER SPRINT PRECOMPUTED_CONTROL \
  --delays 1 2 5 --costs 6 12 18
```

Private immutable report:
`/home/quant/.local/share/copytrade/reports/ml4t66-batch-recovery-20261105/ml4t66_portfolio_backtest_c096f8374de9424bdef0.json`

SHA256: `c096f8374de9424bdef06eef1a3f35185120d8b3bbf9f24303ebb115e6aea854`.

The backtest prints only research metadata on stdout and writes an immutable, owner-private result. No SQLite portfolio was frozen/registered, no network data acquisition, broker order, installed service or production deployment was performed.

## Decision

- **Explorer M10/M33/M53: REJECT as configured for this challenge's historical research**. Its counterfactual risk floor breaches before any unpriced active market, consistently across 1m/2m/5m and 6/12/18bps. More total horizon PnL cannot undo first passage.
- **Sprint M52/M42/M53: INCONCLUSIVE / DO NOT PROMOTE.** Its source order is first unpriceable Aug 31 before the third pod starts; missing-price-filled or skipped variants are not sufficient for a genuine PASS/FAIL. Its extreme modeled drawdowns after omitted orders are warning signals, not authentic account losses.
- **Precomputed M52/M56/M10: INCONCLUSIVE / DO NOT PROMOTE.** An attractive early trajectory does not establish full-window EOD pass or low DD.
- **Next research prerequisite:** source-authoritative complete as-of equity/books/receipt evidence, complete local ALGO/COMP/PONS native days and realistic funding/quote-side TCA before using the `pm_contract_selector` or promoting a portfolio. No further claims from retrofitted leader equity scalars.

**Labels:** `IMPLEMENTED` yes; `ENGINEERING_VERIFIED` by tests yes; `SCIENTIFICALLY_QUALIFIED` **no**; `TRADING_AUTHORIZED` **no**.
