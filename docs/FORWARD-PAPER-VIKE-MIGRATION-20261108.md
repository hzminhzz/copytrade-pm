# Vike forward-paper migration — isolated v4 engineering candidate (2026-11-08)

**Scope:** read-only selected-wallet observation and modeled virtual-paper prices.
**No Grafana, Guardian, broker, funded account, trading authority, or old v3
journal modification.** This branch is based on the existing single-shot
paper work in PR #179; its v3 campaign semantics remain unmodified by default.

## Minimal data contract

1. **Selected wallet fills:** one shared `hl.fills` Vike WebSocket. Supply
   **`min_usd: 0`** and exact wallet allowlist. Keep native event IDs,
   native trade IDs, symbol, DEX, event time, first-local receive, raw event SHA,
   durable SQLite cursor, restart and gap evidence. Each selected fill event
   is a trade, **not** a full selected-account position snapshot. Gaps and REST
   recovery are retrospective, never eligible as invented first-known events.
2. **Position state:** retain the existing official read-only
   `allDexsClearinghouseState` complete selected-account DEX census and
   published SHA-chained `paper_first_known_source_v1` receipts.
   The Vike fill collector does **not yet drive a complete-position
   reconciliation into this paper source journal**. Its output is diagnostic
   until that integration and independent live completeness are verified.
   Selected parent-only policy never requires unrelated subaccount NAV.
3. **Market price:** one shared GET
   `/v1/hyperliquid/ohlcv/latest?market=perp&interval=1m`, covering all
   selected native Hyperliquid perpetual/HIP-3 symbols in a single request.
   The latest bar can be forming: its latest trade close is known only **at
   actual REST receipt**, never at the start of the minute. Persist into a
   **new independent SQLite Vike-price chain**, not `market_quote_receipts`.
   Reject missing markets, stale data, outcome symbols and fabricated depth.
4. **Paper execution:** explicit opt-in
   `--price-mode vike_minute --price-db /absolute/private/vike-prices/paper-events.sqlite3`.
   The new **v4** model estimates half-spread 4 bps, slippage 8 bps, taker
   fees 5 bps, and size-dependent impact up to 10 bps at 10% observed
   minute-volume participation. This is a **scenario**, not proven
   instantaneous capacity or executable broker P&L. Orders exceeding the
   configured participation cap are **unpriceable**, not partial fills.
   Entry due `first_known_at + 300 seconds`; one terminal entry attempt.
   Genuine reductions and risk exits have no extra five-minute wait.
   Unpriceable exits remain unresolved. PM03/04 own risk/accounting.
   Always label modeled results `ESTIMATED_EXECUTION`, not broker executed.

## Isolation and preflight

- Use a **dedicated Vike key for read-only client operations** in private
  runtime configuration. Vike keys are not scoped by permission; this software
  has no mutating provider or broker API. ChatGPT Vike MCP OAuth credentials
  are **not** a VPS credential.
  Do not store credentials in Git, command lines or WebSocket query strings.
  Vike imposes **one active socket per key/path**; close 4410 means another
  connection replaced this one. Never create a replacement storm.
- Use a sealed SQLite registry allowlist with
  `--registry-db /private/wallet_registry.sqlite --portfolios P1,P14,P16`.
  Every selected alias must map unambiguously to the independently verified
  current frozen portfolio definition. A private explicit `--wallets-file`
  (`0600`) remains an opt-in alternate mode. Use separate fills (`0700`)
  and price (`0700`) state directories.
- On 2026-11-08, a dedicated Vike key was provisioned for the `quant` user
  at `/home/quant/.local/share/copytrade/vike-dedicated.env` (`0600`, in a
  parent directory with `0700` permissions). **Never commit or print its
  value.** Access through a private environment file.
- For **finite read-only** research observation, with the credential loaded:
  `copytrade-pm-vike-fills --registry-db /private/wallet_registry.sqlite --portfolios P1,P14,P16 --state-root /private/vike-fills --seconds 60 --dedicated-key-only`.
  A separate shared price check:
  `copytrade-pm-vike-minute --state-root /private/vike-prices --markets BTC,ETH,xyz:BRENTOIL`.
  Neither CLI starts trading or is a qualified complete-position signal source.
- Only after an independently verified source journal and sealed portfolio
  election, start an isolated v4 paper consumer:
  `copytrade-pm-paper-observed --source-db /private/verified-source.sqlite3 --price-db /private/vike-prices/paper-events.sqlite3 --price-mode vike_minute --registry-db /private/wallet_registry.sqlite --state-root /private/v4-paper --run-id p1_vike_estimated_v4 --portfolio P1`.
  The same price producer may serve separately isolated P14/P16 PM03 accounts.
  **Never** run it against the v3 state root/run identity.

## Initial authenticated VPS evidence (2026-11-08 UTC)

- 01:23:32: bulk 1m REST request authenticated; BTC/ETH were captured,
  `xyz:AAOI` absent, so the three-market request correctly returned
  `BLOCKED_INCOMPLETE_MARKET_SCOPE`. A separate BTC/ETH request passed.
- 01:23:42–01:24:42: native W028 `hl.fills` WS subscribed, zero delivered
  fill events, zero gap notices; no authenticated matched REST/WS parity.
- 01:25:49–01:27:09: selected P1/P14/P16 registry-resolved wallet stream
  stayed connected 80 seconds, with zero matching wallet fills, zero gaps,
  no reconnect. Vike's independent connection list confirmed two distinct
  clean close-code-1000 sessions and zero events sent.
- Neither stream test supports claims of follower performance, fill
  completeness, 24–48-hour uptime, or verified selected-account positions.
- Official published API budget: **20,000 REST requests/hour and 200/minute
  per key**, while WS connections and frames are not counted. A 20-second
  bulk quote polling cadence uses nominally **180 REST requests/hour**.
  Source: https://vike.io/data/api.

## Before any service cutover

1. Validate independent original selected-wallet identities and complete
   all-DEX position receipts (including required HIP-3 and deliberately selected
   subaccount scope), Vike native IDs and sub-$1,000 fills in the same live
   window. Do not mistake one selected-wallet canary for full completeness.
2. Prove authentic
   `live Vike fill → verified selected position state → durable new source receipt
   → T+300 one modeled entry → immediate modeled exit → PM03 accounting`.
   This precise production-like chain is **not yet verified** by the tests
   of the isolated price execution path.
3. Run bounded restart, socket 4410 replacement, three-day cursor expiry,
   REST catch-up, missing HIP-3 symbol and stale price fault tests against real
   provider traffic. Measure latency, minute price availability, fees,
   resource usage and post-restart gaps.
4. Preserve the old P1/P14/P16 v3 journal identities and verified rollback
   service definitions. A successful short canary is engineering evidence
   only, never 24–48-hour reliability or follower profitability.
5. Retire the CCXT public L2 service **only** after every above live gate
   is met, with a commit-pinned reversible release under `quant`.
   Do not stop the original official read-only position observer unless its
   necessary state is genuinely replaced. Do not touch funded services.

**Current outcome:** v4 isolated estimated-price engineering path is runnable
from synthetic first-known source receipts and test price receipts. Vike WS
transport and price collector are implemented as independent read-only
intakes. Authenticated live end-to-end source reconciliation and release
cutover are still **BLOCKED**. No claim of alpha, protected trading
authorization or broker execution follows from tests.
