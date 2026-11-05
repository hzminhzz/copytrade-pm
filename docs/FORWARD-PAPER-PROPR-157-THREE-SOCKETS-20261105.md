# Propr public universe: 157 unique native markets / 3 physical WebSockets (2026-11-05)

**Status:** ENGINEERING-TESTED, PUBLIC-MARKET TRANSPORT VERIFIED SEQUENTIALLY, NOT DEPLOYED AS A WORKER, WALLET MATCHING NOT PROSPECTIVELY OBSERVED, FINANCIAL PAPER NO_TRADE.

## Authoritative inputs (distinct roles)

- **Market *display* source, historical and not an account execution authority:** `/home/quant/.local/share/copytrade/reports/five-pod-20261029-research/PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json`, source SHA256 `1a6cd762634d4f05e88577be1a43a5cf2dede643bf724ab743cf7a278e20179b`, public Propr display snapshot observed **2026-10-30**.
- **Native venue listing:** live Hyperliquid `/info meta` queries for default and `xyz` DEX, independently SHA checked by `validate_public_market_catalog`. This proves present Hyperliquid identifiers, not Propr account-specific market IDs, permissions, contract rules or order routes.
- **Wallet identity/roster:** owner-private, sealed **SQLite wallet registry**, not the Propr snapshot or Markdown. The public collector never contains private source wallet addresses in its committed market configuration.
- **Generated static candidate market config:** [157 native instruments / three physical sockets](FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json). The loader checks its source digest, counts, category and selected native market identities. Invoking the CLI with this schema requires `--propr-snapshot PATH`; it rejects any mismatch between that source's *complete current bytes* and the configured native set.

## Full market scope, without silent truncation

| Propr snapshot category | Display entries | Native DEX | Observation identifiers |
| --- | ---: | --- | ---: |
| Crypto | 96 | `default` | 96 |
| Equities | 55 | `xyz` | 55 |
| Indices | 2 | `xyz` | 2 |
| Commodities | 5 | `xyz` | 5 (one shared with equities) |
| FX | 0 | — | 0 |
| **Total** | **158** | | **157 unique** |

`COPPER` appears in both equities and commodities in the source display; both resolve to the **same** `xyz:COPPER`, subscribed once. This is deliberate deduplication, not dropping a market. All 157 distinct requested Hyperliquid instruments exist in the current mainnet metadata; their Propr *orderability* is UNKNOWN. This snapshot is dated and not an automatic detector of newly added Propr markets. `para:`, `io:`, and other DEX listings with the same symbol are **not** silently substituted for `xyz:`.

## Three physical WebSockets, separate from logical groupings

| Physical WS | Markets | Contents |
| --- | ---: | --- |
| `core_crypto_majors` | 8 | HYPE, NEAR, ZEC, BTC, ETH, XMR, SOL, ENA |
| `other_crypto_perps` | 88 | The **other** Propr-displayed default-perp crypto names from the pinned source, no duplicate majors |
| `xyz_equities_indices_commodities` | 61 | All 55 equities, 2 indices and 5 commodities after duplicate COPPER deduplication |

The original **five logical Top-40 reporting groups** remain in the config at `logical_reporting_groups`. They are categorization, **not additional WebSocket connections**, and are strictly a subset of the 157 physical observation markets. The new `paper_public_physical_sockets_v1` schema supports explicit physical socket groups of up to **128 markets**. This is a **local bounded collector limit**, not an exchange limit; older `paper_public_market_shards_v1` (8 markets each) and flat 128-market allowlists remain backward-compatible.

**Connection-budget caveat:** Other services (`hl-tracker`, source rotation and bounded observers) already connect to Hyperliquid from the same VPS public IP. To avoid exceeding the published per-IP connection limit, the live smoke was deliberately run with `--parallel-shards 1` (each 15-second group sequentially). It **did not** demonstrate three always-on concurrent sockets sharing that IP. The CLI requires explicit `--ack-shared-ip-connection-budget` when the Propr 3-socket configuration requests `--parallel-shards` greater than 1, before any network/journal effects. This is a conservative operator acknowledgement, not automatic detection of other services' real WebSocket sessions. Only start a three-socket always-on worker after an independently measured connection budget, sustained backpressure/latency, reconnect/coverage and fail-closed tests.

## Test evidence

### Deterministic three-concurrent-WebSocket fake transport

`tests/test_pm_forward_propr_universe.py` supplies exactly one baseline message and one subsequent trade message per native symbol across the three physical sessions, with two watched counterparties. It validates exact subscriptions, native DEX mapping (including `xyz`), single-record dedup, synthetic **314 buyer/seller receipts**, 157 first-known buckets for each of two synthetic wallets, and **zero** PM-03 events. This proves software routing, not observed live wallet trading or executable PnL. Negative tests refuse missing markets, source drift, mutated layout, ambiguous/invalid source status and unavailable live native metadata.

### VPS live bounded canary (sequential, not protected)

- Configuration: `--parallel-shards 1 --duration-seconds 15 --max-frames 3500`, sealed portfolios P1 and E2, four unique SQLite wallet identities.
- Frame counts: 264 (core majors), 395 (other crypto), 895 (`xyz`) = **1,554**.
- **157/157 baselines**, **114/157 post-baseline-active**, **43/157 baseline-only**, zero with no messages. Quiet baselines are **not** continuous coverage proofs.
- Matched watched-wallet fills: **0**. This run cannot verify real first-known wallet trade detection. Previous independent REST observations found none in the preceding hour for these P1/E2 wallets, but that does not prove subsequent activity.
- Owner-private journal: `/home/quant/.local/share/copytrade/reports/public-trade-propr157-candidate-20261105/paper-events.sqlite3`; SQLite `integrity_check=ok`, directory mode 0700, DB mode 0600, **157 initial-baseline gaps**, **157 normal-end gaps**, **0 wallet receipts**, **0 financial events**, **0 registered paper runs**.
- Read-only UTC planning over the same 157 selected markets and three named groups reports **0 due wallet buckets**, `financial_events_committed=0`, `order_route=NONE`, `paper_running=false`.

## Reproducible commands

```bash
uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev copytrade-pm capabilities show source.public_trades

# One bounded live observation pass. Start sequential to respect shared VPS WS budget.
uv run --frozen --extra source --group dev copytrade-pm-public-trades \
  --mode observe \
  --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --portfolio P1 --portfolio gemini.phase4/E2 \
  --market-file docs/FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json \
  --propr-snapshot /home/quant/.local/share/copytrade/reports/five-pod-20261029-research/PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json \
  --parallel-shards 1 --duration-seconds 15 --max-frames 3500 \
  --state-root /home/quant/.local/share/copytrade/reports/public-trade-propr157-candidate-20261105

# Causal observation-only 5m planning, no finance mutation.
uv run --frozen --group dev copytrade-pm-public-trades \
  --mode plan --timing-policy UTC_BUCKET_CLOSE \
  --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --portfolio P1 --portfolio gemini.phase4/E2 \
  --market-file docs/FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json \
  --propr-snapshot /home/quant/.local/share/copytrade/reports/five-pod-20261029-research/PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json \
  --state-root /home/quant/.local/share/copytrade/reports/public-trade-propr157-candidate-20261105
```

To regenerate an identical candidate layout on a VPS with the same pinned private public snapshot:

```python
from pathlib import Path
import json
from copytrade_pm.pm_forward_propr_universe import build_propr_public_socket_layout

source = Path("/home/quant/.local/share/copytrade/reports/five-pod-20261029-research/PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json")
layout = build_propr_public_socket_layout(
    source, top40_layout_path=Path("docs/FORWARD-PAPER-MARKET-TOP40-SHARDS-20261105.json")
)
print(json.dumps(layout, indent=2))
```

**No live trading authorization.** Market metadata, synthetic fills, and provisional public receipts are not source NAV/position attestations, full feed continuity, L2 capacity, actual Propr orderability, or verified follower performance. The existing PM-03/PM-04 admission and risk gates remain controlling. This change does not install a protected paper service or modify the deployed tracker/ensemble.
