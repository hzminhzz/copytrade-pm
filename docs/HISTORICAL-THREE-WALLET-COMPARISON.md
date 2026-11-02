# Q3 2026 observed-chain three-wallet research (November 2, 2026)

## Result and status

This is an executed exploratory backtest, **not** a complete-wallet 90-day simulation or a demonstrated Propr trading strategy. The Q3 research interval is July 1 inclusive to October 1 exclusive (92 UTC calendar days). Three frozen portfolios A, B, C plus all 81 other combinations of the same nine wallets were evaluated. **All 84 combinations remain partial; no valid full-quarter comparison winner is available.**

The authoritative private evidence is in `/home/quant/.local/share/copytrade/reports/historical-3pod-20261102`, with SHA-addressed JSON files. The portfolio and mixed-combo study report at this snapshot has SHA256 `7367ea0ecfab19cceb1113f99e46e401861e0bcc18cb4ffca3c207f4cb568d04`. Do not commit source fill pages, private wallet mapping, market bars or reports.

| Portfolio | Wallets | Modeled USD PnL **at observed stopping time** | Last modeled observation | Stop |
| --- | --- | ---: | --- | --- |
| A | W028 / W042 / W030 | +73.68 | 2026-08-15 00:00 UTC | Missing exact minute mark |
| B | W044 / CA-005 / W031 | +281.59 | 2026-09-15 18:46 UTC | Simulated drawdown floor breach |
| C | CO-001 / W015 / VS066 | +18.28 | 2026-07-07 00:00 UTC | Missing exact minute mark |

**Do not rank these three PnLs.** They have unequal study durations, nonrandomly excluded source episodes, unverified initial positions, missing account equity/collateral and hypothetical fills. A positive prefix PnL is not the full-period result.

Across all 84 possible triples: 70 stopped at missing market-minute marks, eight breached a synthetic account drawdown floor, three hit the synthetic account profit target, three ended the quarter with an unresolved open follower book. None has a complete faithful source-book history. A result reaching a synthetic target is **not** a prop-challenge pass probability or real account outcome.

## Scope and assumptions

- Each wallet is reconstructed from original immutable HyperX fill pages and optional independently audited supplemental generations. The study admits only directly observed **complete flat-to-flat instrument-level episodes** with continuous quantity-before/after history and exact SHA-backed native 1-minute market bars across that entire episode. Unknown starting inventory, source gaps, unsupported market IDs and missing minute marks remain outside executable evidence, never assumed to be flat. **Filtering on ex-post completed episodes and continuous price availability creates selection/survivorship bias.**
- Historical vendor fill event times are used as a **retrospective signal oracle** with a modelled five-minute wait, not actual first-receipt times. The hypothetical follower uses the first available subsequent exact minute open, batching changes per wallet; one constant wallet-wide scale is retained across observed trades.
- Wallet quantity multiplier is fit using **July–August observed vendor gross notional at last reported trade prices** with a research $2,000 peak-gross budget per wallet. It is neither a true source equity ratio nor time-consistent whole-wallet leverage. No per-trade fixed-notional sizing.
- Consolidation uses the already implemented PM03 `Account` financial authority and internal crosses. Starting cash $10,000. Research-proxy limits: $3,000 gross per pod, $9,000 gross account, $5,000 single instrument, synthetic Classic 1-Step 3% daily loss / 6% static drawdown / 10% profit goal.
- Modeled fees 5bps, assumed full spread 3bps, assumed slippage 5bps, conservative funding debit 1bp per eight hours. Orders above 5% reported minute volume are counted but **not rejected in exploratory mid/open-price proxy**. Hence this is not proof that orders could have executed. Quantities use a 1e-12 simulation grid for exact PM03 reconciliation, not a live lot-size rule.
- The Propr market-display roster was observed October 30, 2026, **after** this study; strict native and tentative HIP-3 matches are screened descriptively, not proof of historical contract permissions. Excluded off-display trades may remove source hedges.
- First true full vendor-listed-instrument book anchors for eight of nine wallets occur **after September 30**, and for VS066 on September 25. Vendor-listed scope is still not proof of exchange-account completeness. Historical account equity/funding/collateral unavailable. A genuinely faithful three-wallet replay thus cannot be declared.

## Reproduce (offline read-only data, new private output)

```bash
uv run --frozen --group dev --extra market python -m copytrade_pm.pm_historical_combos \
  --research-root /home/quant/.local/share/copytrade/reports/five-pod-20261029-research \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --out /home/quant/.local/share/copytrade/reports/historical-3pod-20261102
```

Add `--no-mixed` to evaluate only A/B/C. `--hyperx-generations` accepts paths to independently SHA-audited vendor page generations, not raw unverified replacements. The output `wallet_audit` and `portfolio_results` distinguish coverage, admitted/excluded episodes, source scaling, actual stopping reasons and partial economic trajectories. This CLI does not send orders, activate the ML4T/Propr broker, alter PM02 qualification, or modify the preexisting source manifests.

## Next source-repair priorities

Recover complete source-book position anchors **before July 1**, including the initially open positions and all source instruments, via actual historical account states if available; otherwise report that fidelity cannot be established. Improve native minute coverage only for observed active source legs where its absence materially changes portfolio comparison. Reconcile historical equity and funding before comparing source-exact proportional sizing. Until then treat these scenarios strictly as counterfactual research fragments.
