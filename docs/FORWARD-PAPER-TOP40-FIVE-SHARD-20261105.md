# Top-40 five-shard public trade coverage — 2026-11-05

**Status: ENGINEERING_VALIDATED / LIVE_PUBLIC_FEED_OBSERVED / LIVE_WATCHED_WALLET_MATCH_NOT_OBSERVED / FINANCIAL_PAPER_BLOCKED.** This is a bounded research-only WebSocket experiment, not protected production deployment, completed follower PnL or trade authorization.

## Exact configured universe

The explicit [five-shard top-40 market layout](FORWARD-PAPER-MARKET-TOP40-SHARDS-20261105.json) is an owner-defined **market capture scope**, not a new wallet/portfolio authority. The SQLite registry remains authoritative for which wallets belong to P1/E2 and for denylist decisions. No manual address list is committed. Group order and market order are preserved, not alphabetically repartitioned.

| WebSocket shard | Exact symbols (8 each) |
| --- | --- |
| Core crypto majors | HYPE, NEAR, ZEC, BTC, ETH, XMR, SOL, ENA |
| Liquid altcoins | LIT, PONS, TRX, UNI, JUP, CASHCAT, VVV, ZRO |
| Commodities & indices | xyz:CL, xyz:BRENTOIL, xyz:XYZ100, PUMP, CRV, ONDO, xyz:SP500, BNB |
| DeFi & L1 | MORPHO, LINK, SUI, kPEPE, USELESS, XRP, MET, STRK |
| Precious metals & alts | AAVE, xyz:GOLD, ARB, DASH, XPL, PAXG, INJ, xyz:SILVER |

Current official Hyperliquid `/info meta` responses were SHA-checked before subscribing: 34/34 default perps, 6/6 `xyz` HIP-3 perps were present and not marked delisted. Live `/info` preflight prevents silently ignoring removed or renamed assets. This is **current** metadata only, not a historical listing proof.

The CLI accepts `--market-file` or repeated `--instrument`. Each collector still has a fixed **8-subscription per WebSocket** limit (`MAX_NATIVE_MARKETS`), not a `--max-markets-per-collector` CLI switch. `--parallel-shards 5` now permits five simultaneous sessions. V1 flat JSON still works, while `paper_public_market_shards_v1` carries stable named shard groups. Group layout and entire market set each receive separate digests.

## Bounded live proof (not a continuous observer)

On the isolated VPS worktree from PR #118, the official public `trades` WS was queried with **five simultaneous 8-market subscriptions**, watched wallets resolved from sealed **P1 + gemini.phase4/E2** (four unique SQLite wallet records).

| Shard | Frames received | Baselines | Post-baseline market activity |
| --- | ---: | ---: | --- |
| Core crypto majors | 402 | 8/8 | 8/8 markets |
| Liquid altcoins | 63 | 8/8 | 8/8 markets |
| Commodities & indices | 69 | 8/8 | 8/8 markets |
| DeFi & L1 | 56 | 8/8 | 8/8 markets |
| Precious metals & alts | 38 | 8/8 | 7/8 (ARB baseline only) |
| **Total, 30-second canary** | **628** | **40/40** | **39/40** |

**Actual matched watched-wallet fills: 0.** Matching failed to produce a positive live sample, but the official independent read-only `userFillsByTime` API returned **zero fills for all four watched wallets in the preceding hour** (166 returned fills across the preceding 24 hours: 72, 50, 44, 0 per wallet). Therefore this 30-second sample does **not** falsify the matching code, but also cannot prove prospective observed wallet matching.

The owner-private independent journal at `/home/quant/.local/share/copytrade/reports/public-trade-top40-canary-20261105` has SQLite integrity `ok`, permissions 0700/0600, 40 baseline + 40 session-end gap records, zero candidate wallet receipts, zero financial events and zero registered paper runs. The subsequent 40-market `--mode plan` returned five named shards, **zero due wallet buckets**, and `financial_events_committed=0`. No existing observer or broker was touched.

**WebSocket frames are not exchange transaction counts**; `public_trade_rows` counts parsed post-baseline trades, not user fills. Zero frames on a listed but quiet market cannot be turned into zero trades or complete coverage. A baseline-only/empty market is explicitly reported without claiming full continuity.

## Positive deterministic wallet-capture verification

The regression `test_five_shard_wallet_buy_sell_captured_for_all_40_and_no_paper_execution` builds the **exact 5x8 configured layout**, injects two counterparty addresses and one post-baseline native public trade for **every** symbol, and verifies:

- **80/80** wallet-side receipt inserts (40 buyer, 40 seller); native symbol/Dex normalization works across default and `xyz:` HIP-3.
- Each of five named groups subscribes to **exactly** its eight requested coins, in supplied order; all 40 receive post-baseline events.
- Independent per-wallet/instrument SHA chain checks persist data; 80 immutable UTC bucket observations preserve +2/-2 signed quantities and remain `BLOCKED` for real whole-book NAV.
- `order_route=NONE`, `paper_admitted=false`, and exactly **zero** PM-03 financial events. Simulated synthetic receipts are not exchange first-known evidence.

Additional tests reject malformed/duplicate shard definitions, removed instruments, and incomplete market groups. Tests and the live canary are **different evidence types** and must not be conflated.

## Commands (opt-in, research-only)

```bash
# Confirm current canonical registry and declared capabilities.
uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev copytrade-pm capabilities show source.public_trades

# Five named groups, 40 verified markets, P1+E2 read-only public source.
uv run --frozen --extra source --group dev copytrade-pm-public-trades \
  --mode observe \
  --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --portfolio P1 --portfolio gemini.phase4/E2 \
  --market-file docs/FORWARD-PAPER-MARKET-TOP40-SHARDS-20261105.json \
  --parallel-shards 5 \
  --state-root /home/quant/.local/share/copytrade/reports/public-trade-top40-canary-20261105 \
  --duration-seconds 30 --max-frames 5000

# Deterministic UTC observation only, no paper fill.
uv run --frozen --group dev copytrade-pm-public-trades \
  --mode plan --timing-policy UTC_BUCKET_CLOSE \
  --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --portfolio P1 --portfolio gemini.phase4/E2 \
  --market-file docs/FORWARD-PAPER-MARKET-TOP40-SHARDS-20261105.json \
  --state-root /home/quant/.local/share/copytrade/reports/public-trade-top40-canary-20261105
```

This is bounded observation, **not a service**. Capture durations max at 120 seconds per shard; continuous production requires a separate protected worker, first-known gap reconciliation, source NAV/opening-book verification, L2 capacity and healthy watchdog. E6's two SQLite prop-firm exclusions remain in force; do not silently switch or weaken its freeze.

The operator may need to rerun a bounded observation later to witness an **actual** watched-wallet trade. No live matched event was seen in the current run, so **end-to-end prospective wallet detection remains UNKNOWN**, despite positive deterministic tests.
