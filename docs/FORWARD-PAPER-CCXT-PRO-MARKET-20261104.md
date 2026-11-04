# CCXT Pro Hyperliquid market evidence — 2026-11-04

**Evidence tier:** prospective public **market observation only**, not independently attested wallet equity/positions, executable follower prices, complete traded volume, real paper fills, or scientific qualification. GitHub draft PR #73, FP-07 #64. No order transport, broker credentials, source-wallet subscriptions, service restarts, or production cutover.

## Verified environment and interfaces

- Optional dependency: `ccxt==4.5.91` (`uv run --extra market-stream`). CCXT Pro Hyperliquid exposes public `watch_order_book`, `watch_trades`, `watch_ticker`, and `watch_ohlcv`; native market catalog is loaded with `load_markets`. `watch_order_book_for_symbols` was **not** reported as supported on the tested runtime.
- CCXT market `id` is a numeric exchange asset index (`0` for BTC, `110049` for `xyz:BRENTOIL` in this live sample). The canonical instrument uses Hyperliquid `info.name`, **not** numeric ID or guessed unified ticker. BTC: `hyperliquid/mainnet:perp:default/BTC`; HIP-3: `hyperliquid/mainnet:perp:xyz/BRENTOIL` with CCXT symbol `XYZ-BRENTOIL/USDC:USDC`.
- HIP-3 DEX catalogs require explicit CCXT option `fetchMarkets.hip3.dexes=["xyz"]`. A readable BRENTOIL quote **does not** prove that session, venue, Propr compatibility or execution permission are currently active; `supported=false` until those independently verified gates are implemented.
- One-shot read-only CCXT Pro L2 source receipts use **exchange event time** (`timestamp` milliseconds) and separately captured **first local known time**, with strict `source <= first_known <= decision` ordering and a bounded quote age. Captured best bid/ask is a quote-midpoint mark, **not** Hyperliquid `markPx`. No candle, future bar, or retrospective fill is promoted into a present quote.
- L2 best-level size is **resting depth**, not traded volume or an executable fill guarantee. PM-03 observation emits `volume_base=null` and the existing model rejects fills with unknown volume capacity. CCXT market metadata supplies lot increment/minimum notional, but not an attested independent executed volume or funding/margin agreement.
- Each quote and market metadata row is SHA-bound locally; those hashes detect post-capture mutation **only**, not exchange-origin signatures. On provider timeout, unchanged replay, invalid book or clock regression, the market is quarantined until a new catalog/subscription session.

## Reproduction — live **read-only** canary

```bash
uv run --extra market-stream --group dev copytrade-pm-market-ccxt \
  --instrument hyperliquid/mainnet:perp:default/BTC \
  --instrument hyperliquid/mainnet:perp:xyz/BRENTOIL \
  --hip3-dex xyz --timeout 18 \
  --record-root /home/quant/dev/copytrade-pm/data/private/ccxt_market_canary_20261104
```

`--record-root` is optional. Without it, the one-shot CLI does not persist any quote. The live run used a distinct private **market-observation** SQLite tape, not a protected paper financial-state or automatically deployed service. The path is under the canonical `dev/copytrade-pm` root, **not** inside `.devspace`.

| Evidence | BTC default perp | xyz:BRENTOIL HIP-3 |
| --- | --- | --- |
| Exchange event timestamp (UTC) | 2026-11-04 04:44:44.967 | 2026-11-04 04:44:44.967 |
| First local known (UTC) | 04:44:45.527981 | 04:44:45.843621 |
| Best bid / ask | $76,950.00 / $76,951.00 | $102.82 / $102.83 |
| Quoted mid | $76,950.50 | $102.825 |
| CCXT numeric market ID | `0` | `110049` |
| Quote quality | `VERIFIED_QUOTE` (local L2) | `VERIFIED_QUOTE` (local L2) |
| Paper instrument supported | `true` for quote identity; **volume unknown** | `false` (HIP-3 session unverified) |
| Quote receipt SHA-256 | `d70ca00ceab8ead2b21467978e0ef2301968ea437cd9523b45ce13c826b28542` | `b259726ce44aa3d9ccb788428483ddaf4c58f4e66d5a18664fa56edfda5719f8` |
| Local receipt chain head | `ee6a36aa2f9e1d8a0f39863527a9437c944cd1c9f2daf957c0f0d596befce472` | `f96de154f74cbbfe42cb191123fb3c04e8507b43fac7d69c21f6324f9f9c975a` |

The private path `/home/quant/dev/copytrade-pm/data/private/ccxt_market_canary_20261104` was verified mode `0700`, journal `paper-events.sqlite3` mode `0600`, effective owner UID 1001. Both market tape cursors were `1`; read-only full chain verification passed. File bytes remain outside Git. This is not a deployed protected paper wallet-account ledger.

## Contracts and limitations

- `pm_forward_ccxt_market`: native market identity, live L2 validity, provider-session gating and fake-client reconnect tests.
- `pm_forward_market.market_contract_reasons`: binds a `VERIFIED_QUOTE` observation to local L2 book/cost-policy hashes, quote freshness, allowed minimum lot/notional and conservative spread assumptions. A spoofed volume field is explicitly rejected.
- `pm_forward_journal.PaperJournal.append_market_quote` and `market_quote_status`: monotonic, immutable SHA-chain, latest-head integrity before append, and full SHA-chain validation on online backup/restore. A mutated latest head cannot silently admit more receipts; a corrupt market chain invalidates backup acceptance. The market observation tape is **separate** from source-wallet receipts and account effects.
- `pm_forward_pm04` and the PM-03 simulated decision path call the extended contract validator; no broker adapter or ticker-to-order conversion was introduced.

**Outstanding work before actual unattended forward paper:** independently complete and first-local-known source wallet equity/positions across all DEXes/subaccounts; prospective, continuous market/trade-volume and funding provenance; HIP-3 session and tradability attestation; independently verified worker/feed heartbeats, dedicated protected OS paper identity, reversible cutover, 72h pilot and 24h soak. CCXT Pro data alone cannot satisfy those requirements.

Primary references: [CCXT Pro manual](https://docs.ccxt.com/docs/pro-manual) and [CCXT Pro Hyperliquid implementation](https://github.com/ccxt/ccxt/blob/master/python/ccxt/pro/hyperliquid.py). The observed live output above is time-specific; it is not a standing price.
