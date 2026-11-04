# Read-only CCXT Pro trade/quote capture — 2026-11-04

## Evidence classification

**ENGINEERING VERIFIED / PUBLIC MARKET OBSERVED ONLY.** No complete source-wallet NAV/positions, authorized execution, complete traded volume, funding/margin settlement or scientific qualification is established. This is not a paper fill or pilot.

Current work is on draft Forward-Paper PR #73. `ccxt==4.5.91` is pinned in optional `market-stream`; no order/client credentials are configured.

## Design

- Reuse one CCXT Pro Hyperliquid public client for both `watch_order_book` and `watch_trades` per native market; bounded per-channel task and explicit time/event caps, no background daemon.
- The first `watch_trades` response is a **retrospective cache baseline** and contributes zero locally observed trades. Later rolling windows are deduplicated by `(instrument, native trade ID)`, native trade identity hashes, event timestamp and first-local-known clock.
- A conflicting native ID, stale/forged/future source time, cache overflow without overlap, local clock regression, WS exception or reconnect quarantines the market. New subscription sessions start a fresh epoch and do not bridge the gap.
- `PaperJournal.market_trade_batches` keeps a separate private SQLite WAL/FULL SHA chain by instrument and first-known time. Every batch carries `trade_volume_complete=false` and `executable_volume_base=null`. This is intentional: CCXT's rolling cache supplies a **lower-bound observation**, not independently attested complete volume or a settlement/execution guarantee.
- Financial PM-03/04 worker and paper manifests are unchanged. The existing quote/market tests continue to refuse an order-volume assumption from book depth. This collector has no wallet, order, cancel, leverage or broker API.
- The private quote and trade chains participate in the journal's online backup and exact integrity verification. The `copytrade-pm-market-stream` command is bounded and writes solely to the explicit private state root.
- A finite, opt-in `supervise_bounded_market_epochs` library driver creates a fresh public client, native catalog, and trade-cache baseline per bounded epoch, uses bounded restart pauses, and reports reconnect gaps and per-epoch acquisition failures. Each failed quote/trade or missing native identity marks its epoch `DEGRADED_EPOCH`, not healthy. It never bridges or backfills downtime, infers volume, claims 24-hour continuity, runs indefinitely, or starts a systemd worker. Regression tests inject a failed trade channel followed by a new client, prove the new epoch's baseline is excluded, and spy on zero exchange mutations.
- The bounded report now explicitly counts requested versus catalogued native markets and lists every missing identity under `missing_native_markets` and `stream_failures[market]`. Unsupported or ambiguous markets are never silently omitted from coverage. `full_requested_market_scope_observed=false` remains conservative even when every requested instrument was catalogued: per-channel success in a short bounded window cannot establish continuous source/quote coverage, session validity or execution capacity. Regression: `tests/test_pm_forward_market_stream.py::test_missing_native_market_is_explicitly_blocked_not_silently_skipped`.

## Live public canary (VPS)

```bash
uv run --extra market-stream --group dev copytrade-pm-market-stream \
  --instrument hyperliquid/mainnet:perp:default/BTC \
  --state-root /home/quant/dev/copytrade-pm/data/private/ccxt_trade_stream_20261104 \
  --duration-seconds 12 --max-updates 10
```

| Observed result | Value |
| --- | --- |
| Market | Hyperliquid BTC/USDC perpetual |
| Duration budget | 12 seconds |
| L2 quote receipts | 3 |
| Trade-cache batches | 10 |
| Initial cache baseline excluded | 1 |
| Newly observed unique native trade IDs | 16 |
| Quote tape cursor | 3 |
| Trade tape cursor | 10 |
| Trade SHA head | `98c0af3850a084697d8072972b5947ccecfa994629ce28851b1765292e16010d` |
| Quote SHA head | `743d1cd6785f7e13941a7057bce1ea3da8e729e7af0ffe08e0824c77f80a7677` |
| Disconnect, provider errors | 0 reported during bounded interval |
| Broker mutations, simulated fills | 0 |
| Trade-volume completeness | **UNKNOWN — not attested** |
| Actual continuous 24-hour observation | **NOT RUN** |

Both chains persisted under a canonical `dev/copytrade-pm/data/private` directory, not a `.devspace` worktree. These are unprivileged research observations and **not** protected deployed financial state. Future protected runtime isolation, independent source-book attestation, 72-hour pilot and 24-hour 50-account soak remain separate required gates.

Official [CCXT Pro manual](https://docs.ccxt.com/docs/pro-manual) notes that `watchTrades` returns a bounded cache; it is not a stream of only newly arrived trade objects. That behavior is explicitly covered by tests.
