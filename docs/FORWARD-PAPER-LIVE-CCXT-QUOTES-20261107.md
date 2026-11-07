# CCXT Pro continuous quote feed for copytrade forward paper (2026-11-07)

## Ownership and design

**Market data producer:** one persistent public CCXT Pro Hyperliquid WebSocket
collector, `copytrade-pm-market-live-quotes`. **Data contract:** the EXISTING
`PaperJournal.market_quote_heads` and `market_quote_receipts` SQLite
chains, plus the existing `StreamProgress` quote-stream checkpoint.
There is no second price authority, no broker connection, no trade
transmission, no synthetic quote timestamps, and no new trading permission.

**Source producer:** `copytrade-pm-paper-observe --source-only` preserves the
existing P1/P14 selected-wallet first-known receipt capture while disabling
its obsolete short-lived CCXT market WebSocket shards. It retains the exact
original SQLite source tape and heartbeat. Both writers use the existing
per-transaction SQLite flock; the CCXT writer also holds a distinct
`paper-ccxt-quote-writer.lock` for exclusive market-writer ownership.
A source receipt and a quote receipt may briefly compete for the underlying
short-lived `PaperJournal` SQLite writer lease. The quote-only
`SerialWriter` retries **at most 20 times** with bounded backoff, but ONLY
when the original `PAPER_JOURNAL_BUSY_OR_UNAVAILABLE` exception was caused
by a pre-transaction OS `BlockingIOError` (flock rejection). It reuses the
same original quote and first-known clock, and never retries uncertain
SQLite errors, hash divergence, or an already-started transaction. The
source-only public observer opts into a **one-second maximum** wait for the
OS writer lease, before SQLite transaction startup. Every other PM-03 /
`PaperJournal` caller retains the original zero-wait fail-closed behavior.
The source observer's read-only, SHA-chain heartbeat verifier also waits up
to **three seconds** for transient WAL schema contention without bypassing
any individual historical hash/chain checks. This prevents a normal
source/quote lock collision from killing the entire market-data service
without making duplicate financial events possible.
Paper readers keep reading that shared SQLite, without a restart or changing
PM-03 campaign policy, positions, entries, exits, or T+300 execution clocks.

The new quote publisher composes `run_ccxt_markets`,
`ReadOnlyCCXTProHyperliquid`, `CCXTLocalReceiptClock`,
`PersistentMarket` and `SerialWriter`. Raw WS ingress time is retained
before market normalization. Reconnecting starts a new baseline/gap epoch;
it never backdates a missing event or extends quote freshness artificially.
An instrument with no real book update remains stale, even while others are
fresh. A fresh book is sampled at most every 5 seconds per market to bound
SQLite growth; the sample keeps the original WS known-at timestamp and
local hash/chain integrity. The worker checks its SHA-verified P14
selected-wallet source universe and refreshes the subscription set every
300 seconds. No implicit universe expansion beyond the explicit 64-market
cap. A subscription does not prove independent source liquidity or complete
HIP-3 orderability.

**Unchanged consumer contracts:** P1, P14, P16 virtual-paper campaigns,
one attempt at T+300s for entries, immediate one-shot exit/reduction, and
no retry of residual target differences. Each simulated market-order intent
still needs verified fresh executable depth for the FULL intended size.
A silent WebSocket, missing native market, crossed/invalid book or stale
quote fails closed; no fake partial fill or retrospective backfill.
Existing HIP-3 execution restrictions remain unchanged.

## Independent canary

Before touching running services, a finite 55-second CCXT Pro session was
recorded to a NEW private journal, not the shared producer/consumer DB.
Recorded 25/25 native markets and 194 market receipts, each validated by
`PaperJournal.market_quote_status`; no source records, wallet state or
broker orders. Two checkpoints observed all 25 fresh within 20s, while
later 24/25 were fresh. This proves successful public WS ingress for the
canary and proves **individual market staleness remains possible**.

The canary's local receipt SHA chain is local tamper evidence; it is not
provider signature, complete trade-volume evidence, order execution, or
scientifically qualified follower P&L.

## Deployment

Use the reviewed pinned release from Git (never an editable working tree).
Install **both** optional dependency sets in its exact Python environment:
`uv sync --frozen --extra market-stream --extra source --group dev`.
The original source collector imports `websockets==15.0.1` while the CCXT
collector imports `ccxt==4.5.91`; installing only `market-stream` makes the
market service appear healthy but leaves all wallet-source captures broken.
The source unit's versioned `ExecStartPre` checks both modules at process
start and fails instead of silently reporting zero wallet observations.
The initial 2026-11-07 source-only cutover encountered this missing extra,
resulting in five source-capture errors. After installing `source` and
restarting only the source observer, all five selected parent streams wrote
fresh first-known receipts and the next source epoch had zero gaps.
The initial quote worker had one automatic restart caused by a concurrent
source/quote `PaperJournal` writer-lock collision. The quote-only bounded
pre-transaction retry was added with adversarial regression tests before
releasing the corrected collector. A source heartbeat also restarted after
the verifier used SQLite `timeout=0` on the actively written quote tape;
the source-only writer lease and verified-reader waits above address that
independent contention failure. These are engineering reliability fixes,
not proof of a complete forward T+5 fill/exit.

Do not stop any Guardian, Bybit, Propr, dashboard, ensemble or unrelated
systemd unit. Capture original unit ExecStart, PIDs, SHA, tape state and
health before modifying the observer. Verify that the monitored P1/P14/P16
virtual accounts have no unclosed finance blockers, and preserve their
ledger files. Install a versioned **user** systemd drop-in for the original
`copytrade-public-observer-p1p14.service`, overriding ONLY its
`WorkingDirectory` and `ExecStart` to the pinned code with `--source-only`.
Restart only this read-only source service, preserving its original
`--state-root` and all other arguments.

Install a separate enabled `copytrade-ccxt-live-quotes-0711.service` which
subscribes to the verified native P14 source union and writes to the exact
same private observed tape. Resource bounds: CCXT dial limiter at six
attempts/minute, max 64 markets, five-second per-market persistence floor,
512-item async writer queue, 12GB SQLite main-file cap and bounded systemd
memory. `quant` user needs `Linger=yes` for reboot persistence. Do not
deploy duplicate CCXT quote writers or a second copy of source observation.
The old bounded CLI is still available for isolated tests but no longer
owns the **running** forward-paper market feed.

Initial checks:

```bash
copytrade-pm-market-live-quotes --source-db /PRIVATE/.../paper-events.sqlite3 \
  --registry-db /PRIVATE/wallet_registry.sqlite --primary-dir /FROZEN/primary \
  --secondary-dir /FROZEN/secondary --preflight

systemctl --user is-enabled copytrade-ccxt-live-quotes-0711.service
systemctl --user show copytrade-ccxt-live-quotes-0711.service \
  -p ActiveState -p NRestarts -p ExecStart
journalctl --user -u copytrade-ccxt-live-quotes-0711.service -n 20
```

Inspect per-market `known_at`, source timestamp and native depth in the
append-only market tape. A successful process, all-green canary and fresh
quotes alone do NOT prove a successful T+5 executable order. Confirm
later authentic ledger receipts `PM04_PAPER_EXECUTE` and
`PM04_PAPER_EXIT` separately, including requested/native qty, modeled
VWAP/slippage, fees, and no repeated market-order intent.

## Rollback

Stop and disable only the new CCXT quote unit. Remove its **versioned**
observer override and restore its captured original command. Restart only
the public source observer. Do not rewind or overwrite any legacy SQLite
market/source sequence; old stamped quotes and missing intervals remain
honest historical evidence. Existing paper campaigns continue fail-closed.
Never loosen quote age or silently discard HIP-3 hedges to manufacture PnL.
