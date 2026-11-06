# Vike data recovery: observed contract and safe next integration

2026-11-06. Research-only implementation checkpoint, based on a live MCP query.
This is **not** a production authorization or a verified vendor WebSocket.

## Actual observation

- The Vike `hl.fills` contract documents a **$1,000 USD default** minimum fill notional.
- Live `stream_check_filter` accepted an explicit `min_usd: 0` with one syntactically valid address, but its echoed normalized `filter` contained only the wallet, **not the zero**. Thus acceptance of the request does **not** prove that the subscribed WebSocket includes fills below $1,000.
- The REST `stream_events` call with `min_usd: 0` returned a historical fill of approximately $28.28 among three sampled records. This is **only REST evidence**, not streaming coverage or a measured parity rate.
- The current copytrade-pm source implementation uses native Hyperliquid account snapshots. Vike is an independent candidate, not a substitute for native source/account reconciliation.
- At inspection, main worktree contained extensive third-party/indexed changes and diverged from origin/main; all new files are isolated in an origin/main-based DevSpace worktree.
- An isolated `copytrade-wallet-registry doctor` emitted `database_integrity: FAILED` without a diagnostic cause. The source checkout did not expose that CLI. Verify the actual installed release, private database path, schema, and signed selection proofs before *any* registry mutation.

## Guard

`pm_vike_contract.verify_fill_subscription` refuses to approve a normalized subscription with an omitted or nonzero `min_usd`, missing wallets, or an invalid channel. A successful result explicitly remains `PREFLIGHT_ONLY` and `production_admitted=false`.

The live Vike normalized response currently fails this guard. Do not deploy a feed based solely on `valid=true`.

## Required next steps before integration

1. Confirm vendor's actual WS semantics for explicit zero with a real socket and raw fill-level comparison against its REST catch-up and independent native Hyperliquid source over a time-bounded, representative sample.
2. Establish stable trade identifiers (wallet, DEX, instrument, native trade ID) and independently measured local receipt timestamps. Preserve raw evidence and catch-up cursors.
3. Reconcile W028's historical 84 additional provider records without retroactively inventing prospective local knowledge times.
4. Establish whole-account equity/positions across DEXs and relevant parent/subaccounts, with freshness gates. Never assume adding independent per-DEX NAV gives whole-account equity.
5. Verify commercial licensing, VPS credentials, quota budgets, outages, restart/replay and monitoring before any persistent unattended integration.
6. Repair/verify the SQLite authority through its canonical release process with backups and authorized signed selection evidence. Never forge missing signatures or silently rebase frozen cohorts.

All tasks remain blocked for data-production admission until independently verified.
