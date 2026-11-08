# V4 position-first virtual-paper deployment (2026-11-08)

## Scope and authority

Approved for merging and deploying the **read-only official source observer and
isolated virtual paper** under the `quant` user (operator instruction
2026-11-08). This does not authorize a real broker order, Guardian changes,
prop-production changes, or assumptions of positive source follower PnL.
See [the binding position-first decision](decisions/2026-11-08-position-first-t300.md).

## Dependencies and durable separation

- Release: commit-pinned clean GitHub `copytrade-pm` main archive, frozen
  uv environment. Record full SHA, artifact hashes, pinned lock and build
  evidence; never run a working-tree import in long-lived services.
- Source: `python -m copytrade_pm.pm_v4_selected_positions --registry-db
  /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite
  --portfolios P1,P14,P16 --state-root
  /home/quant/.local/share/copytrade/prospective/v4-selected-positions-0811`.
  Resolve the current SQLite P1/P14/P16 seals, deduplicate *five selected
  parent accounts*, fetch the official `perpDexs` census once, and open **one
  persistent official allDexsClearinghouseState WS**. Every begin/reconnect
  creates an epoch and first complete baseline. Immutable source receipts and
  official stream checkpoints share a transaction in one private
  `paper-events.sqlite3`. Failed validation is a GAP, never a flat.
- Price: one shared Vike 1m latest-price REST collector, with its dedicated
  private EnvironmentFile and
  `--propr-catalog /absolute/release/docs/FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json`.
  Vike market price (and its hypothetical participation cap) is independent
  from the official source-position authority. Public displayed catalog is
  *not* Propr account order permission. Missing native price rows are explicit.
- Paper: **three separate** read-only V4 paper services P1, P14 and P16. Each
  uses the shared official source DB and shared price DB but a distinct
  `--state-root` and `--run-id`, with `--price-mode vike_minute
  --propr-catalog`. The native contract sizing/min-notional value is a
  versioned scenario assumption. V4 never opens a broker connection.
- Preserve original P1/P14/P16 V3 paper, CCXT quote, Grafana, Guardian and
  all prior tapes. The first deployment is additive; do **not** stop CCXT
  until actual post-baseline source transitions, live T+300 modeled attempts,
  exit integrity and independent physical feed availability have evidence.

## Verify

1. `systemctl --user show` each V4 service: pinned path, correct argument
   schema, `MainPID`, `ActiveState`, restarts and private state root. Verify
   exact release SHA and source tree from the merge, not just `active`.
2. Run `copytrade_pm.pm_forward_stream_journal.verify_streams` on the source
   journal. Confirm selected aliases and valid first-known BASELINEs. Distinguish
   `OBSERVATION` counts and gaps from transport-only heartbeats.
3. For each paper root, inspect `manifest.json` and the PM-03 ledger. Confirm
   independent run IDs, portfolio seals, fixed k, synthetic risk budget, no
   `real_broker_fills`, `order_route=NONE`. No stale/open old baseline may
   turn into a new entry.
4. Test initial startup and clean restart (ideally during a no-risk baseline),
   re-open with the original rulebook/catalog hash. It must fence pending
   old-epoch new-risk intents without fabricating a close.
5. Monitor real provider coverage, native market and minute price availability,
   source event/first-known latency and T+300 when authentic transitions
   occur. Absence of authentic transitions leaves that acceptance UNKNOWN.
   Unit tests alone do not qualify scientific follower PnL.
6. Compare with V3 fallback and review the actual service identities; never
   merge paper journals or overwrite a confirmed financial receipt.

## Reversible rollback

Stop/disable only the **new** `copytrade-v4-` user services, paper first,
then source and price. Leave V4 journals in place as immutable negative/positive
evidence, preserve the pinned release, and re-check the original running
`copytrade-paper-research-p1-0711`,
`copytrade-registry-paper-p14-0711`,
`copytrade-registry-paper-p16-0711`, and
`copytrade-ccxt-quote-feed-0711`. The existing official/public observer
remains independent. No schema migration or financial live-order rollback is
part of this isolated V4 deployment.
