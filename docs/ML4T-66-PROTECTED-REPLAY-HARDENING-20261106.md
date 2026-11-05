# ML4T-66 protected replay: 6 November 2026 integrity hardening

**Decision:** research-only, `SCENARIO_ONLY / BLOCKED_ECONOMIC_EVIDENCE / NO_AUTHORIZED_PURCHASE_RECOMMENDATION`. This report replaces the performance tables in [5 November preliminary protected replay](ML4T-66-PROTECTED-POD-BACKTEST-20261105.md). All old sealed reports are retained for reproducibility and deliberately not rewritten.

**Account** $10,000 hypothetical; frozen SQLite cohort `ml4t-strict-66`; 3 pods each given independent **$200 trailing marked-PnL stop** relative to its own high-water mark; 1m native SHA-validated OHLCV, 3.5bps taker plus 2.5bps slippage per side baseline, 1m/2m/5m first-event nonresetting batches. The STOP is *not* 2% of each pod's $3,333.33 initial split. Risk trigger freezes that pod, queues exit, fills at the **next observed 1m OPEN** if modeled capacity exists, charges exit friction and never assumes the realized loss was limited to exactly $200.

## Bugs found and repaired in isolated PR #120

1. **False whole-day missing market price**: The native, independently SHA-validated PONS source for 2026-08-31 has **1,210 continuous 1m bars 03:50–23:59 UTC**; the 06:55 order was inside that interval. The old loader rejected the whole day if bars were not exactly 1,440, and incorrectly returned a Sprint gap. The new loader uses only observed SHA-validated exact timestamps and leaves the 230 genuinely absent minutes `NaN`. No manufactured pre-listing candles.
2. **Pod stop after a new order**: The old replay processed orders before marking existing exposure at that minute's opening price; a gap could admit an additional risk-increasing source delta before stopping the pod. Opening-price checks now precede new source entries; the same-minute source increase is blocked if the stop or the account floor triggers.
3. **Ghost follower position when skipping sub-$10 signals**: Deltas now update the **cumulative leader target**, while the follower trades the difference between its *actual modeled book* and that target; an earlier skipped small buy cannot turn a subsequent leader close into a spurious follower short.
4. **Implicit post-flat reversal**: PM-04 has a hard `AWAIT_EXPLICIT_NET_REVERSAL_AUTHORIZATION` rule. A prior local script opened the other side one minute after flattening. The new replay stages the old-side close and latches an explicit `outstanding_source_reversals` veto without authorizing the opposite side. It never manufactures a new authorization merely from the passage of time.
5. **Unrestricted modeled exposure**: Optional, explicitly specified scenario-only `--max-gross-usd` and `--max-market-usd` now reject prospective increases using native current-open marked existing exposure, and request full halt/exit on observed marked overcap. They are **not claimed as authenticated prop-firm limits**. Reductions are never treated as completed before their modeled executions.
6. **No capacity guard**: Optional `--max-participation` uses the **preceding completed minute's native base volume** (not unknown current-bar volume), accounts for same-minute combined modeled fills across pods, rejects new increases when over the cap, and fails closed on unexecutable required reductions or stopped-pod liquidation. A native 1m volume cap is a scenario sensitivity, not an attested broker order-book fill.
7. **Misleading 3-pod performance labels**: Each report now carries `source_trading_pods`, `first_source_trade_utc`, `traded_pods_before_target`, `all_members_traded_before_target`, and `max_simultaneously_nonflat_pods`. Tests assert that an untraded third pod never counts as a fully participating ensemble.
8. **Policy and numerical regression**: Unit tests cover pod latch, next-open forced flat with exit friction, no automatic re-entry, gap at open, partial native day, $10 order catch-up, risk caps, source reversals, previously completed-minute capacity, fail-closed exits, UTC EOD Sprint ratchet, global halt, nonfinite settings, and a simple two-side double-entry accounting parity against native PM-03 `Account`.

**Important authority boundary:** These changes strengthen an **independent historical-oracle diagnostic**, they do *not* move its simulated cash authority into PM-03. Exact PM-03/PM-04 end-to-end whole-book execution, portfolio netting, PIT follower receipt/NAV and actual broker/Propr signed fills remain separate scientific and engineering admission requirements. A simple accounting parity test is **not** a full PM-03 integrated replay.

## Latest model comparison, frozen original source, 5m and 6bps each executed side

| Scenario | Explorer M10/M33/M53 | Sprint M52/M42/M53 | Earlier M52/M56/M10 |
| --- | ---: | ---: | ---: |
| $200 per-pod trailing stop only: **model net PnL** | **+$426.79** | **+$546.12** | **+$801.50** |
| Peak-to-trough model DD, USD | $295.26 | $297.29 | $155.85 |
| Model status | All 3 stopped and flat | All 3 stopped and flat | Modeled Sprint $800 target and 5 green days |
| Max simultaneously **nonflat** pods | 2 | 2 | 2 |
| Optional *hypothetical* $10k gross cap, model PnL | +$347.72 | +$422.95 | +$801.50 |
| Separately frozen P2 **$100 daily** pod stop, model PnL | +$34.47 | −$40.75 | +$6.44 |
| 10% preceding-minute base volume participation, full PnL | **UNKNOWN/BLOCKED** | **UNKNOWN/BLOCKED** | **UNKNOWN/BLOCKED** |

The original leaderboard ensemble M52/M56/M10 **reached its modeled $800 threshold on 2026-09-04 13:33 UTC**. This **was not three contributing wallets** at first passage: M52 contributed +$771.05, M10 +$30.45, and **M56 had no executed copied trades and $0 modeled PnL**. The activity evidence is `traded_pods_before_target=["M10","M52"]`, `all_members_traded_before_target=false`; max simultaneously exposed pods = 2. The historical $155.85 MDD is **1.56% of starting capital**, which does **not** meet the user's stricter Sprint exploration goal of maximum DD **below 0.50%** even though it is below the nominal 5% EOD trailing evaluation limit. The five-green-day model threshold is *not* a provider-verified firm pass.

The Explorer and Sprint candidates use all three wallets during their individual research windows, but **never simultaneously hold three nonflat pods in the modeled paths**. They also stop before hitting their respective $1,000 and $800 challenge profit targets under baseline $200-per-pod trailing. Neither is optimized, qualified, independently followed or suitable for purchase based on this study.

## Costs and delay sensitivity, $200 trailing only

| Delay | Explorer PnL 6 / 12 / 18bps | Sprint PnL 6 / 12 / 18bps |
| --- | --- | --- |
| 1m | +$423.63 / +$340.29 / +$255.04 | +$521.53 / +$422.51 / +$323.49 |
| 2m | +$415.16 / +$375.66 / +$292.34 | +$517.69 / +$418.99 / +$343.31 |
| 5m | +$426.79 / +$344.04 / +$261.29 | +$546.12 / +$447.44 / +$348.77 |

These PnL sensitivities are **not OOS**; wallets were selected using historical source information. The earlier ensemble’s target first-passage PnL changes by path/cost, so apparent non-monotonicity near a threshold is not evidence of positive slippage.

## Exact offline reproduction, private immutable SHA evidence

All command execution is through the development worktree, and all outputs are owner-private. Run from the worktree with the version-pinned environment:

```bash
uv run --frozen --extra market python scripts/ml4t66_protected_portfolio_replay.py \
  --db /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --source-root /home/quant/dev/copytrade-pm/data \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --output-root /home/quant/.local/share/copytrade/reports/ml4t66-batch-recovery-20261105 \
  --portfolio EXPLORER SPRINT PRECOMPUTED_CONTROL \
  --delay 1 2 5 --cost 6 12 18 --pod-dd-usd 200
```

Immutable reports inside `/home/quant/.local/share/copytrade/reports/ml4t66-batch-recovery-20261105/`:

| Variant | Report prefix | SHA-256 |
| --- | --- | --- |
| Corrected primary 27-case 1/2/5m × 6/12/18bps | `ml4t66_protected_pod_replay_1595f27d580453e3d5ed.json` | `1595f27d580453e3d5ed5519dd53da280be4e2411c082c8d1a5041feef06208d` |
| Separate P2 daily pod stop at $100 | `ml4t66_protected_pod_replay_2c1465b11598cfa9d277.json` | `2c1465b11598cfa9d277c40b6df983d9d8eeb82ae59fbc422b82780e07507b92` |
| Hypothetical $10k maximum gross | `ml4t66_protected_pod_replay_2b25f9d605dfd64a6e54.json` | `2b25f9d605dfd64a6e54ca90ed6e3f41d442bf947dd72959de5e775119d80c56` |
| 10% prior completed 1m volume capacity | `ml4t66_protected_pod_replay_f85ba2ef9a52a9de7e37.json` | `f85ba2ef9a52a9de7e37de73b85d4463c1cabf0bcb46b699218528f33cdb58cd` |

Previously frozen `ML4T-66-PROTECTED-POD-BACKTEST-20261105.md` and dated scenario artifacts remain unchanged *except for an explicit supersession banner*. Never splice old scenario results with corrected logic.

### Still blocked by real-world evidence, not patchable as historical data

- Atomic opening source positions on all perp DEXs and linked subaccounts; as-of leader equity/NAV and collateral/funding; independently known first follower receipt times
- True executed follower fills, bid/ask depth, market impact, broker minimums, margin/liquidation and precise prop contract rulebook and overnight EOD caps
- Actual PM-03/PM-04 consolidated netted book replay, hedge-break stress and independent supervision with a durable journal under a genuinely future paper trial
- Host CI startup: GitHub Actions jobs remain blocked **before any runner steps** under existing repository issue #113. Local tests cannot replace required hosted checks.

**Authorization:** no portfolio registrations, no orders, no deployments, no service changes; `NO_AUTHORIZED_PURCHASE_RECOMMENDATION`.
