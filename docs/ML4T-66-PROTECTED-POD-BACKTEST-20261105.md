# ML4T-66 protected 3-pod copytrade backtest — correction

**SUPERSEDED for modeling and portfolio metrics by [6 November replay hardening](ML4T-66-PROTECTED-REPLAY-HARDENING-20261106.md)**. The following numbers are preserved strictly as a dated *prior-version* reproducibility record; do not rank wallets or contracts from them.

**Executed on VPS:** 2026-11-05. **Research-only; not qualified follower returns, not an authorized execution plan.**

The previous `ML4T-66-PORTFOLIO-BACKTEST-20261105.md` used an *unprotected* standalone historical source-fill replay. Its Explorer $6,148.94 loss was a **post-evaluation-failure, after-stop counterfactual**, not the result of the owner's specified portfolio construction.

## Correct risk rules

A $10,000 account with 3 independently accounted pods has an owner-specified **$200 (2% of account) nominal trailing P&L drawdown budget per pod**, not 2% of each pod's $3,333.33 equity and not a shared $600 pooled stop. The existing `pm04_shadow._stats` already implements per-pod executed-and-marked P&L high-water, independent `SUSPENDED` latches and routed zero-reduction intent. `pm03_account` owns actual account risk and positions. The original stand-alone study omitted those controls.

This **new offline research adapter**, `scripts/ml4t66_protected_portfolio_replay.py`, replays the same independently SHA-verified source/market inputs but follows PM-04 **stop semantics** in chronological 1m account cash/inventory, rather than clipping old returns:

1. Evaluate each pod's realized + marked P&L from its own zero-capital ledger; update its own high-water. At $200 trailing loss from that high-water, latch `SUSPENDED_PENDING_EXIT`. Do not accept another source increase for that pod.
2. Send **all open legs** of that pod to flat at the next native 1m open. Charge 3.5 bps taker fee and 2.5 bps adverse slippage on **every exit leg** (as on entry). The actual modeled loss **may exceed $200** due to marking latency, gaps and costs. A non-executable price leaves the position **open and blocked**, never fabricated flat.
3. Unaffected pods remain active until their own stop, the account contract barrier, or target. The contract barrier halts all pods and requests all positions flat; it never assumes a target can be carried forward as a stage-2 pass. This is **not a production PM-04 event-ledger integration**; it is an independent historical replay implementing the same risk thresholds, with its own regression tests.
4. The owner had separately frozen `P2_flatten` **$100 daily per-pod loss threshold** for three pods in `docs/decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.md`. This **is a separate policy option** and must not silently be treated as part of the owner's $200 trailing rule. Compare both clearly.
5. The alternative `--mark-mode adverse` uses simultaneous worst 1m low for longs/high for shorts **only to trigger a conservative early stop**; the cash ledger and execution still use observed 1m closes and next-minute opens. It is an intrabar stress bound, not guaranteed executable stop mechanics.

## Verified results (5m first-event batching, $10k, 6 bps per executed side)

| Portfolio | Risk configuration | Combined P&L | Max marked DD | Status |
| --- | --- | ---: | ---: | --- |
| Explorer: M10/M33/M53 | $200 pod trailing only | **+$123.37** | **$295.30** | all 3 suspended and flat |
| Explorer | $200 trailing + optional $100 daily pod loss | **+$88.70** | **$295.30** | all 3 suspended and flat |
| Explorer | $200 trailing + $100 daily + adverse 1m OHLC stop trigger | **+$121.71** | **$271.75** | all 3 suspended and flat |
| Sprint: M52/M42/M53 | $200 trailing only | UNKNOWN | $297.29 observed before gap | missing PONS opening price on Aug 31, fail-closed |
| Sprint | $200 trailing + $100 daily | **−$40.75** | **$287.17** | all 3 suspended and flat before any unavailable active price |
| Sprint | $200 trailing + $100 daily + adverse OHLC | **−$11.16** | **$265.57** | all 3 suspended and flat |
| Original leaderboard trio: M52/M56/M10 | $200 trailing + $100 daily + adverse OHLC | **+$91.32** | **$186.47** | all 3 suspended and flat |

Do not compare completed Sprint P2 policy variants to the Sprint trailing-only result as if they were equivalent; introducing the separately documented daily stop changes account behavior and removes the later missing-price exposure. None of these historical returns reached the Explorer's +$1,000 or Sprint's +$800 evaluation target in the fully flat trajectories.

### Independently modeled Explorer stop evidence (only $200 trailing)

| Pod | Stop time UTC | Cash P&L after forced flat | Remaining position |
| --- | --- | ---: | --- |
| M33 | 2026-09-14 00:01 | −$16.25 | none |
| M53 | 2026-09-23 07:06 | +$19.76 | none |
| M10 | 2026-09-28 03:22 | +$119.85 | none |

A pod can stop at **positive realized P&L** because its $200 trailing loss is measured from its own earlier marked profit high, not from zero. No source orders can reopen a suspended pod. Aggregate net **+$123.37**, observed MDD **$295.30**; priced peak gross notional **$36,001.89** (3.6× starting account). The owner-defined $200 stop is **not a pretrade gross/notional cap**: no leverage cap was silently invented. Exits were hypothetically filled at the next native minute open with modeled friction; real venue liquidity/latency could differ.

**1m/2m/5m 6/12/18bps sensitivity, $200 trailing only, Explorer**:

| Delay | 6bps P&L / MaxDD | 12bps P&L / MaxDD | 18bps P&L / MaxDD |
| --- | --- | --- | --- |
| 1m | +$80.80 / $293.67 | +$2.47 / $315.15 | −$75.86 / $336.63 |
| 2m | +$105.78 / $293.83 | +$30.32 / $315.31 | −$45.14 / $336.79 |
| 5m | +$123.37 / $295.30 | +$47.91 / $316.78 | −$27.55 / $338.26 |

Costs are charged on each executed side, including exits. All Explorer sensitivity variants ended flat after all three pods latched. The change in profitability under reasonable friction stresses demonstrates that the thin historical positive P&L is not qualified alpha or adequate contract EV.

## Private audit paths

Under `/home/quant/.local/share/copytrade/reports/ml4t66-batch-recovery-20261105/`:

- Trailing-only 27-case 1/2/5m x 6/12/18bps: `ml4t66_protected_pod_replay_db54bfdec3c03d8f0396.json`
- $200 trailing + $100 daily: `ml4t66_protected_pod_replay_92cd2a41775991c2e74e.json`
- $200 trailing + $100 daily + adverse OHLC: `ml4t66_protected_pod_replay_3eab90c75cc5f539d7ab.json`

Run using:

```bash
uv run --frozen --extra market python scripts/ml4t66_protected_portfolio_replay.py \
  --db /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --source-root /home/quant/dev/copytrade-pm/data \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --output-root /home/quant/.local/share/copytrade/reports/ml4t66-batch-recovery-20261105 \
  --portfolio EXPLORER SPRINT PRECOMPUTED_CONTROL \
  --delay 1 2 5 --cost 6 12 18 --pod-dd-usd 200
```

For the saved P2 version, append `--pod-daily-usd 100`. For an independent conservative OHLC trigger sensitivity, append `--mark-mode adverse`.

## Research limitations and governance

Retrospective source fill clocks are not independently captured first-known follower receipts; source-equity scalar `E_leader` has no per-fill timestamp; initial source account and subaccounts are not reconciled. 1m OHLC and hypothetical market opens are not independently measured Propr executable quotes or actual broker fills. The adapter does not model funding, fills under partial liquidity, real spread/market impact, full collateral, margin liquidation or independently verified gross/concentration caps. It freezes all risk at stop but **cannot promise realized final pod loss ≤$200**, especially at 1m OHLC resolution. The Explorer high gross and unproven PIT NAV remain serious risks.

The corrected run **does not prove** either portfolio is optimal, profitable out-of-sample, or an authorized prop contract purchase. It is, however, the required protected *historical-oracle* backtest rather than an irrelevant unprotected trace.

**No SQLite production portfolio changes, trades or service restarts.** `NO_AUTHORIZED_PURCHASE_RECOMMENDATION`.
