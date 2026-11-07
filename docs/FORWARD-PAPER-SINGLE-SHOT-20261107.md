# P1 forward research paper: single-shot market execution v2

**Policy:** `single_shot_market_paper_v2`. **Owner:** isolated P1 observed-paper research
worker. No authenticated broker, Bybit, Propr, Guardian or dashboard mutation.

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

Exits and risk reductions are separate immediate, bounded attempts. Market
marks that trip a pod's loss latch create a distinct durable risk-exit intent
without waiting for a new wallet observation. If the PM-03 account has
contractually breached, the attempted flattening cannot fabricate a fill;
the retained position is reported as unresolved exposure. Unpriceable or expired exits retain the actual inventory, preserve
the loss liability and report `UNRESOLVED_EXPOSURE`. True reversals must
reduce/flatten existing inventory first. A further opposite entry still
requires the delayed entry window.

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

Never resume an `observed_fixed_k_p1_paper_v1` journal as v2. Keep its
manifest, source hashes and PM03 event bytes intact under the original run id.
For v2, allocate a fresh private state root and run ID; versioned code and
manifest must bind to a verified Git commit. Read-only observer SQLite and
native registry are shared unchanged. The quant-owned transient research
service may be stopped and replaced; no other systemd units or protected
financial services may be touched. Inspect the old run ledger hash/OS PID,
record the exact prior revision, stop exactly the selected service,
install the frozen commit and start v2 with finite resources and
`--poll-seconds 2`. Verify process, revision, incoming source, PM03 replay,
journal changes and error rate. A process without a post-start qualifying
source/market opportunity is only `RUNNING_AWAITING_LIVE_SIGNAL`, never
evidence that a live execution occurred.

Test path: `uv run --frozen --extra dashboard --extra market-stream --group dev pytest -q`.
The complete suite should remain green. `ruff check .` and `uv build`
are separate gates. Do not promote this paper outcome to live finance.

## Rollback

Keep the original private v1 research journal read-only and unmodified.
Stop only `copytrade-paper-research-p1-0711.service`; if v2 fails,
reinstall the frozen v1 release as a **new** research service after verifying
its legacy policy/run configuration. Never blend old and new modeled fills,
retimestamp historical signals or overwrite v2 accounting.
