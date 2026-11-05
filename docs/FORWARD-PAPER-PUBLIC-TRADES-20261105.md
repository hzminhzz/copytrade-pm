# Public market-trade wallet observations and causal UTC batching (2026-11-05)

**Authority:** isolated research implementation on `feat/pit-public-trade-paper-bridge-20261105`, based on `origin/main` at `58dc8ee`. This is NOT a financial paper worker, source-account NAV proof, live order path, or scientific qualification. Existing P1/P14 read-only observer and pinned release are unchanged.

## Verified bounded public-feed canary — 2026-11-05

The current owner-private SQLite metadata contains **2 prop-firm-excluded wallets in the sealed E6 portfolio**. The read-only E6 preflight returned `PUBLIC_TRADE_WALLET_PROPFIRM_EXCLUDED` before any network call or journal creation. **Do not remove the exclusions or silently substitute E2 as an approved trading selection.** E2 was used solely for a transport canary because its 3 indexed members had no matching prop-firm exclusions at inspection time.

With E2 and native BTC, the one-shot WebSocket canary successfully received **10 frames**, excluded one uncertain baseline batch, and produced **0 matched watched-wallet fills** during the ten-second window. Its isolated private SQLite journal has **2 gap/baseline records**, **0 candidate trade receipts**, **0 financial events**, **0 registered paper runs**, and `PRAGMA integrity_check=ok`; its directory is mode 0700 and database 0600. The subsequent `--mode plan` completed with **0 buckets**, no quote or paper execution, and `financial_events_committed=0`. This is transport smoke evidence only, not fill completeness or follower profitability.

## Why this capability exists

The existing `pm_forward_source_stream.py` subscribes to `allDexsClearinghouseState` for bounded *account snapshots*. An account snapshot cannot prove the sequence of intermediate fills or round-trip turnover. Hyperliquid public `trades` frames identify the two counterparties (`users=[buyer, seller]`), price, size, native market and trade ID. Filtering these events by addresses resolved from the authoritative SQLite wallet registry can observe candidate changes for many wallets without dedicating a user-specific WS slot to each.

**Limitations:** public trade streams are not independently sequenced, not guaranteed complete across network failure, do not capture whole-account NAV, collateral, all parent/subaccount ownership, funding, or liquidation adjustments, and do not imply execution capacity. Fills are **PROVISIONAL** until independently reconciled. Do not use a trade-by-trade net delta directly as an admitted follower position target.

## Existing native owners

| Concern | Owner |
|---|---|
| Canonical wallet identity, exclusions, sealed portfolio versions | `wallet_registry.py` and `wallet_registry_portfolios.py` in owner-private SQLite |
| Existing source snapshots and collateral diagnostics | `pm_forward_source_stream.py` and `pm_forward_source_observation.py` |
| Public trades and new bounded collector | `pm_forward_public_trades.py` |
| Receipt SHA chains, gaps, immutable UTC net-delta plans, quote as-of | `pm_forward_journal.PaperJournal`, private `paper-events.sqlite3` |
| Rolling vs UTC timing policy | `pm_forward_batch.ForwardBatch` |
| Public L2 best-level hypothetical cost preview | `pm_forward_quote_execution.py` |
| Actual paper financial accounting and target/risk authority | **Existing** `pm03_account`, `pm_forward_paper`, `pm_forward_pm04`; *not called by provisional intake* |
| Independent admission and protected workers | Existing `pm_forward_admission`, `pm_forward_readiness`, FP-11/FP-12 protected-gate procedures |

The journal adds these tables **only in a new private journal**:
`public_wallet_trade_heads`, `public_wallet_trade_receipts`,
`public_trade_stream_gaps`, and `provisional_utc_buckets`.
The canonical wallet registry is **read only**. Existing `source_receipts`, `events`,
`account_source_cursors`, `market_quote_receipts`, `funding_claims`, PM03 account snapshots and old SHA chains are unchanged.

## Causal contracts

1. The WebSocket receiver stamps `first_known_at` immediately after `recv()`, before JSON parsing, queueing or disk I/O. Retrospective/backfilled events are **never** assigned the source's event time as first-known.
2. A native trade identity consists of canonical instrument, exchange trade `time`, `tid`, canonical wallet reference and signed buyer/seller side. Duplicate observations are idempotent and preserve the **original** locally first-known receipt. Wallet addresses are not serialized in paper receipts. `watchlist_sha` binds a capture to the address-to-wallet mapping read from SQLite; wallet numeric IDs are *generation-local*.
3. A receipt has both a local knowledge clock and an independently stamped SQLite `committed_at`; the latter is included in its SHA chain. For a due decision, only receipts **known and durably committed before that decision** may contribute.
4. On any new subscription epoch, the entire first market trade message is discarded as an uncertain baseline. On epoch close, data error, cancellation or bounded stopping, journal the gap. Do not silently claim it can be repaired at the old first-known time.
5. Five-minute source observation uses `[T, T+5m)` UTC wall-clock windows. `observed_utc_net_delta` reports signed net and gross turnover separately. Complete intra-bucket round-trips can net to zero; retains their gross turnover for diagnostics. Missing initial positions/NAV and unresolved stream gaps force `BLOCKED_NO_WHOLE_WALLET_NAV_OR_CONTINUITY`.
6. A provisional UTC plan is immutable. Late evidence produces a correction-needed state, **not** a rewrite of the original decision.
7. `first_eligible_quote_after` selects only the first locally known and SHA-verified market quote **at or after** the execution deadline, respecting a fixed maximum lateness and book age. This is not a fill. `preview_top_level_paper_cost` charges best bid/ask spread once, adverse slippage and taker fees, but blocks beyond displayed best-level depth and never asserts full traded-volume capacity or writes PM-03 PnL.

## Three timing policies are different

- **Legacy default** `FIRST_SIGNAL_PLUS_5M`: nonresetting deadline at the first eligible observation plus 300 seconds. Preserves old FP-05 behavior and tests.
- **New** `UTC_BUCKET_CLOSE`: bucket `[12:00,12:05)` due `12:05:00 UTC`. A fill known at `12:04:59` has only one second of delay; do **not** market this as a universal 5-minute lag.
- **New** `UTC_BUCKET_PLUS_5M`: `[12:00,12:05)` due `12:10:00 UTC`, at least 5m delay after the last observation in the bucket.

**Historical research parity is NOT assumed.** The owner must pin which policy, as-of clock, cost and mark regime generated the old retrospective order-count improvements before comparing with forward results.

## Offline and bounded observation commands

Discover before invoking:
```bash
uv run --frozen --group dev copytrade-pm capabilities show source.public_trades
uv run --frozen --group dev copytrade-pm capabilities validate
uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev copytrade-wallet-registry portfolio gemini.phase4/E6
uv run --frozen --group dev copytrade-pm-public-trades --help
```

For a **new** owner-private state root with mode 0700 and no existing protected paper journal, a scoped, read-only Hyperliquid trade observation (writes local provisional evidence only):
```bash
uv run --frozen --extra source --group dev copytrade-pm-public-trades \
  --mode observe \
  --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --portfolio gemini.phase4/E6 \
  --instrument hyperliquid/mainnet:perp:default/BTC \
  --state-root /home/quant/.local/share/copytrade/reports/public-trade-candidate \
  --duration-seconds 10 --max-frames 100
```

To run **one** UTC scheduling read over that same isolated provisional tape, without exchange activity:
```bash
uv run --frozen --group dev copytrade-pm-public-trades \
  --mode plan --timing-policy UTC_BUCKET_CLOSE \
  --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --portfolio gemini.phase4/E6 \
  --instrument hyperliquid/mainnet:perp:default/BTC \
  --state-root /home/quant/.local/share/copytrade/reports/public-trade-candidate
```

The commands are opt-in research-local *mutations*; do not run them against the protected P1/P14 financial journal, installed release, tracker or ensemble service. Native market coin and account evidence are public; wallet address mapping stays owner-private. Scope and known-at seals may block the command if a portfolio's canonical wallet ID is post-seal or unresolved.

## NOT YET achieved

- No guarantee of complete public trade coverage or reliable reconnect gap repair. Require matched independent `userFills`, TWAP and source position reconciliation, as well as observed first-known timing.
- No independent complete leader account and subaccount NAV, initial whole-book position, funding or hedges.
- No authenticated full-depth / executable-volume evidence or Propr account-specific fee and permission contract.
- No causal portfolio-level 5m financial paper worker attached to these provisional observations; **PM-03/PM-04 remain the only financial state authority**.
- No protected systemd paper-worker activation, 72-hour pilot, scientific alpha/EV qualification, real trade authorization or deployment.

These are explicit acceptance blockers, not reasons to bypass `admit_source_book` or simulate a fake financial fill. The next engineering milestone should reconcile a full account position and NAV in the real first-known clock, develop depth/capacity evidence and pass existing FP-04/FP-07 admission, then test the existing atomic `PaperJournal.consume_source_effect` bridge under a protected OS worker.

## Verification

```bash
uv run --frozen --group dev python -m pytest -q tests/test_pm_forward_public_trades.py tests/test_pm_forward_batch.py
uv run --frozen --group dev python -m pytest -q tests
uv run --frozen --extra market --group dev python -m pytest -q tests
uv run --frozen --group dev ruff check src tests
uv run --frozen --group dev ruff format --check src tests
uv run --frozen --group dev copytrade-pm capabilities validate
uv build --offline
```

Run tests on the actual updated commit and record results; a passing test never becomes a historical first-known receipt or worker admission.
