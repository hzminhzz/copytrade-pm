# Public market-trade wallet observations and causal UTC batching (2026-11-05)

**Authority:** isolated research implementation on `feat/pit-public-trade-paper-bridge-20261105`, based on `origin/main` at `58dc8ee`. This is NOT a financial paper worker, source-account NAV proof, live order path, or scientific qualification. Existing P1/P14 read-only observer and pinned release are unchanged.

## Verified bounded public-feed canary — 2026-11-05

The current owner-private SQLite metadata contains **2 prop-firm-excluded wallets in the sealed E6 portfolio**. The read-only E6 preflight returned `PUBLIC_TRADE_WALLET_PROPFIRM_EXCLUDED` before any network call or journal creation. **Do not remove the exclusions or silently substitute E2 as an approved trading selection.** E2 was used solely for a transport canary because its 3 indexed members had no matching prop-firm exclusions at inspection time.

With E2 and native BTC, the one-shot WebSocket canary successfully received **10 frames**, excluded one uncertain baseline batch, and produced **0 matched watched-wallet fills** during the ten-second window. Its isolated private SQLite journal has **2 gap/baseline records**, **0 candidate trade receipts**, **0 financial events**, **0 registered paper runs**, and `PRAGMA integrity_check=ok`; its directory is mode 0700 and database 0600. The subsequent `--mode plan` completed with **0 buckets**, no quote or paper execution, and `financial_events_committed=0`. This is transport smoke evidence only, not fill completeness or follower profitability.

## Multi-market scaling and observed public feed — 2026-11-05

The original 7-pair BTC/ETH/SOL/HYPE/ENA/ZEC/NEAR canary received **122 WS frames**, baseline-captured all seven markets and matched **0 watched-wallet sides**. The updated sharded collector then received **83 frames across two concurrent shards**, successfully baselining all **10** default-perp markets in [the example allowlist](FORWARD-PAPER-MARKET-EXAMPLE-20261105.json): BTC, ETH, SOL, HYPE, ENA, ZEC, NEAR, XRP, SUI, TAO. Each had at least one **post-baseline** public trade message. Separately, a 16-second HIP-3 canary received **24 frames** with post-baseline observations for `xyz:BRENTOIL`, `xyz:GOLD`, `xyz:SILVER`, after verifying these names against official live `/info` `meta` (`dex=xyz`).

The two new private journals had, respectively, **20** and **6** baseline/end gap records, **0 matched wallet-fill receipts**, **0 financial events**, SQLite `integrity_check=ok`, private directory 0700 and SQLite file 0600. The watchlist was the union of SQLite-sealed P1 and E2; two excluded E6 members remain outside the observer. These are **bounded connectivity/cross-market routing tests**, not proof that all exchange trades or all source-wallet actions were captured. A catalog including 70–100 markets requires an explicit complete selection; do not infer a watched wallet's market exposure from its display alias alone.

The official protocol supports `trades` subscriptions by native `coin` name, including prefixed HIP-3 markets, and `/info` `meta` for universe discovery. See the [exchange WebSocket subscription contract](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions) and the [official Python SDK public metadata implementation](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/hyperliquid/info.py).

## Exact five-shard extension

The [owner-selected 40-market named 5×8 layout](FORWARD-PAPER-MARKET-TOP40-SHARDS-20261105.json) is now supported without alphabetic reshuffling. Each shard is bound to a stable name and the complete configuration is SHA-addressed. The exact configuration was verified against current official `/info meta` (34 default + six `xyz:`); [live and synthetic integration results](FORWARD-PAPER-TOP40-FIVE-SHARD-20261105.md) document the 628-frame real public feed and the distinct 80/80 deterministic wallet-side receipt test. The 30-second P1/E2 canary observed no wallet fills, independently consistent with zero reported official fills during the preceding hour, so real prospective matching remains `UNKNOWN`. This bounded research-only test does not qualify a financial paper worker.

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

For a **new** owner-private state root (mode 0700) separate from all protected journals, use the [13-market example allowlist](FORWARD-PAPER-MARKET-EXAMPLE-20261105.json) for a bounded observer run. This public catalog is an **example**, not an authoritative, comprehensive watched-wallet market roster:

```bash
uv run --frozen --extra source --group dev copytrade-pm-public-trades \
  --mode observe \
  --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --portfolio P1 --portfolio gemini.phase4/E2 \
  --market-file docs/FORWARD-PAPER-MARKET-EXAMPLE-20261105.json \
  --state-root /home/quant/.local/share/copytrade/reports/public-trade-candidate \
  --parallel-shards 2 --duration-seconds 20 --max-frames 500
```

`--instrument` can be supplied repeatedly instead of `--market-file`. All selections must use native `hyperliquid/mainnet:perp:default/COIN` or HIP-3 `hyperliquid/mainnet:perp:DEX/COIN` identities, not spot symbols or CCXT unified strings. The CLI strictly validates the allowlist, refuses duplicates, and supports **up to 128 explicitly selected markets**, split into ≤8 subscriptions per WebSocket and ≤5 concurrently running shards. It never silently drops an omitted market, and reports `NO_MARKET_FRAMES`, `BASELINE_ONLY` or `ACTIVE_AFTER_BASELINE` per market. `max-frames` and `duration-seconds` bound **each shard**, not a continuous daemon. Unsupported/incomplete universes stay blocked.

To run **one** immutable UTC scheduling pass across those markets and the same wallets, without exchange activity or financial paper fills:

```bash
uv run --frozen --group dev copytrade-pm-public-trades \
  --mode plan --timing-policy UTC_BUCKET_CLOSE \
  --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --portfolio P1 --portfolio gemini.phase4/E2 \
  --market-file docs/FORWARD-PAPER-MARKET-EXAMPLE-20261105.json \
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
