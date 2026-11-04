# Forward-paper real-input readiness and cost stress — 2026-11-04

**Decision: BLOCKED_NO_TRADE for P1 and P14.** This report is based on bounded, true first-local public observations. It is *not* a paper trade, a backtest, a production service, or scientific qualification.

## Evidence and actual admission gaps

The read-only `copytrade-pm-paper-readiness` command joins three separate authorities without modifying any of them: (1) sealed WR-06 portfolio identity + owner-private historical address locator (identity only), (2) official all-DEX per-parent Hyperliquid source receipts and (3) CCXT Pro first-local L2 quote receipts.

| Portfolio | Frozen version | Wallet identities resolved in membership | Source accounts with live per-parent observations | Independently complete wallet NAV | Required **native** markets from signed observed inventory | Markets with bounded L2 receipt | Status |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| P1 | 2 | **0/3** | 3/3 (3 receipts each) | **0/3** | 9 | 8 | BLOCKED_NO_TRADE |
| P14 | 2 | **0/5** | 5/5 (S064: 3, Whale: 2) | **0/5** | 23 | 22 | BLOCKED_NO_TRADE |

All five native account addresses are found in the registry's wallet table, but frozen portfolio membership `wallet_id` is NULL, therefore paper source activation cannot be inferred from matching files. Independent parent/subaccount/spot/vault NAV, collateral denominator, source position marks, complete trade volume, quoted market session and protected worker identity remain unavailable. The observed portfolio inventory includes hedges/cross-pairs: selecting only ENA/BTC/HYPE or the headline coin would silently omit exposures.

Public L2 expansion scanned current native inventory in bounded shards of 5–6 per client, using official Hyperliquid symbols from live captured source positions. The only market not accepted as an L2 quote was `hyperliquid/mainnet:perp:para/ANSEM`: the observed book spread exceeded the safety threshold (`CCXT_BOOK_SPREAD_TOO_WIDE`). The code **did not relax that threshold**. HIP-3 `para`/`xyz` quote availability never proves trading-session authorization, and earlier short bounded quotes turn STALE after the freshness window. Full 24-hour continuity, exchange fill capacity and source equity remain UNKNOWN.

## Reproduction — no trading permissions

```bash
uv run --group dev copytrade-pm-paper-readiness \
  --portfolio P1 \
  --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --primary-dir /home/quant/dev/copytrade-pm/data/wallet_fills_90d \
  --secondary-dir /home/quant/dev/copytrade-pm/data/nansen_smart_money_fills_90d \
  --source-db /home/quant/dev/copytrade-pm/data/private/paper_scope_observations_20261104/paper-events.sqlite3 \
  --market-db /home/quant/dev/copytrade-pm/data/private/p1p14_market_observation_20261104/paper-events.sqlite3
```

Use `--portfolio P14` for the challenger. All database connections use SQLite URI `mode=ro`, `query_only=ON`; source and market SHA chains are verified with independent financial-tape rules and do not create new receipts. A source identity mismatch, broken SHA chain or invalid market frame fails closed. The sample counts reflect the bounded 2026-11-04 canary, not a continuously updating production feed.

## Forward-paper 1x/2x/3x modeled execution costs

`copytrade-pm-paper-report ... --cost-stress` optionally replays committed **synthetic** PM-03/PM-04 event decisions with cost assumptions at 2× and 3× (model fees, full spread, slippage, impact); it reprices the same as-known events under the existing PM-03/04 accounting authority and rehashes modeled market cost contracts within the **read-only report process**. It does **not** rewrite the original journal, rerun Gemini research, create new paper runs or claim predictive alpha. If no modeled execution evidence exists, the scenario explicitly reports `NO_MODELED_EXECUTION_EVIDENCE`. This is a diagnostic cost stress only, not a separate validated strategy.

## Remaining gates

1. WR-06 must authoritatively seal wallet ID links in a new owner-approved registry version, without overwriting frozen version 2.
2. Live producer must independently establish full parent/subaccount/spot/vault position + equity/mark and collateral coverage; a single all-DEX parent WS cannot satisfy this.
3. Native market quote and complete execution-capacity continuity must cover every signed open/hedging market; `para/ANSEM` remains unsupported by observed spread and HIP-3 session status requires separate attestation.
4. Dedicated OS users, immutable paper releases and supervised worker/watchdog identity must pass protected preflight.
5. Then a separate authorized 72h real paper pilot and a 24h 50-account soak may begin; no previous fixture can replace elapsed observations.
