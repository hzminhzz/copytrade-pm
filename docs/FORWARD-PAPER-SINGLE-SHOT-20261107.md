# P1 forward research paper: single-shot market execution v3

**Policy:** `single_shot_market_paper_v3`. **Owner:** isolated P1 and
reviewed additional registry-bound observed-paper research campaigns.
See [the multi-portfolio activation contract](REGISTRY-PAPER-PORTFOLIOS-20261107.md).
No authenticated broker, Bybit, Propr, Guardian or dashboard mutation.

## Intent, not a permanent target-chasing loop

One first locally known selected account/perp source position starts an immutable
T0. At T0+300 seconds, the latest complete source position seen during the wait
is fixed-k sized against a verified, fresh independent follower quote and
**actual** PM-03 paper holdings. Intermediate source updates do not reset T0.
The worker records an intent, one set of per-instrument attempts and the
settlement atomically in the existing PM-03 append-only replay ledger.
Identical receipts, repeated quotes, restarted processes and stale residual
differences cannot consume an intent twice. Actual market orders are
instrument-specific; multiple L2 matching levels are multiple modeled fills
inside **one** instrument/order intent, not separate order submissions.

The handler `pm_forward_single_shot.apply_paper_event` is the only PM-04
single-shot transition authority, dispatched via the existing PM-03 ledger.
`PM04_PAPER_SOURCE` stores source timestamps and desired quantities;
`PM04_PAPER_EXECUTE` commits attempted quantity and any modeled filled
inventory; `PM04_PAPER_EXPIRE` terminates absent opportunities. An eligible
intent has a T0+300s due time and a 30s **maximum** grace period. Failure
to price an order is `UNPRICEABLE_MARKET_ORDER`, with zero invented fills,
and no target catch-up. Poll latency is bounded by a <=2s source poll and a
deadline-aware wakeup; scheduling delay is not exchange order latency.

Exits and risk reductions are **immediate** bounded single-market-order
opportunities, never subject to the 300-second entry delay. One instrument
gets one attempted order at the current verified bid (sell) or ask (buy),
walking all *known* levels once. No partial top-level fill is rolled over
to subsequent polling ticks; inadequate depth yields
`UNPRICEABLE_MARKET_ORDER` and preserves actual inventory as
`UNRESOLVED_EXPOSURE`.

A **new source reduction** (quantity decrease, full close, or reversal)
may create a fresh exit intent. A residual difference from a failed exit
alone cannot authorize another order. An unrelated leader size increase
cannot retry it. Updates during a pending exit coalesce into that same
intent, with its initial ID and 30-second deadline unchanged; withdrawal
of the reduction cancels an unattempted exit. Each outcome remains in
durable exit history. The same observed quote cannot be consumed twice
on the same instrument and order side, including across separate
entry/exit intents or pods.

A pod-loss mark creates an independent risk-exit authorization without
waiting for a new wallet observation. It can override a failed source exit,
or escalate a still-pending source exit **without** creating a second
order or extending its original deadline. Once a risk exit is attempted,
subsequent risk-mark ticks cannot implicitly retry the leftover inventory.
If the PM-03 account has contractually breached, the engine does not
fabricate a flattening fill; the liability remains unresolved. True
reversals must close existing exposure first; new opposite exposure still
requires a separate delayed entry window.

**Sizing remains unchanged:** for each market, source native quantity times
source mark times frozen pod k is the signed follower notional. Divide by
the independently observed follower quote to get quantity, then round
toward zero to native lot. PM-03 alone accounts for cash, fees, realized
and unrealized PnL. PM-04 enforces pod daily/max-drawdown/stress,
gross exposure and concentration. The configured three $200 pod budgets
are nominal triggers, not guaranteed maximum losses or actual protected
broker headroom. Source wallet whole-account NAV is not required.

## Market evidence classes

An authenticated locally chained public CCXT market receipt may include
bounded, monotonic multi-level bid/ask depth. The model walks the executable
side once for entire market-order quantity, uses displayed levels for
VWAP plus 2 bps added execution slippage and 5 bps taker fee. Bid/ask
spread is already present in the executable prices and not charged twice.
When only top-level evidence exists, that level must suffice for the
**whole** requested amount or execution is unpriceable. Depth is displayed
liquidity, **not** observed traded volume or broker-confirmed fill. There
is no hypothetical successful fill for an unsupported full size.
HIP-3 remains blocked without independent session eligibility; funding
is unavailable, and forward-PnL is not scientifically qualified.

## Campaign migration and verification

Never resume a v1 or `single_shot_market_paper_v2` journal as v3. Keep
their manifests, source hashes and PM03 event bytes intact under the
original run IDs. The v2 campaign's earlier source/expiration records must
not be retroactively replayed through changed transition rules. For v3,
allocate a fresh private state root and run ID; versioned code and
manifest must bind to a verified Git commit. Read-only observer SQLite and
native registry are shared unchanged. The quant-owned transient research
service may be stopped and replaced; no other systemd units or protected
financial services may be touched. Inspect the old run ledger hash/OS PID,
record the exact prior revision, stop exactly the selected service,
install the frozen commit and start v3 with finite resources and
`--poll-seconds 2`. Verify process, revision, incoming source, PM03 replay,
journal changes and error rate. A process without a post-start qualifying
source/market opportunity is only `RUNNING_AWAITING_LIVE_SIGNAL`, never
evidence that a live execution occurred.

Test path: `uv run --frozen --extra dashboard --extra market-stream --group dev pytest -q`.
The complete suite should remain green. `ruff check .` and `uv build`
are separate gates. Do not promote this paper outcome to live finance.

## Rollback

Keep the original private v1 research journal read-only and unmodified.
Stop only `copytrade-paper-research-p1-0711.service`; if v3 fails,
restart the last verified, still-pinned v2 research release and its
original journal only after verifying immutable manifest compatibility.
Never blend old and new modeled fills,
retimestamp historical signals or overwrite v2 or v3 accounting.
