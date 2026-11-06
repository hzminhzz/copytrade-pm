# Continuous public observer

Owner: [program #129](https://github.com/hzminhzz/copytrade-pm/issues/129),
implementation #130–#140. Operational gates: #141 and #142.
This contract extends the existing public observer; it does not authorize a
financial worker, change a frozen portfolio, or submit orders.

## Interfaces and owners

| Purpose | Native interface / owner |
| --- | --- |
| Registry and frozen membership | Existing SQLite registry doctor, sealed portfolios and exclusions |
| Candidate preflight | `copytrade-pm-paper-observe --continuous-config CONFIG --preflight-only` |
| Persistent capture | Same command without `--preflight-only` |
| Independent current health | `copytrade-pm-paper-observer-health --continuous --state-root ROOT` |
| Independent continuous witness | Same health command with `--watch --expected-revision SHA` |
| Measured shadow report | `copytrade-pm-paper-observer-health --shadow-report --state-root ROOT` |
| Aggregate status | `copytrade-pm --observer-state-root ROOT health` |
| Bounded real market probe | `copytrade-pm-market-ccxt --continuous-canary-seconds 135` with explicit instrument, private new root and shared-IP acknowledgment |
| Atomic progress / legacy receipts | `PaperJournal` plus additive `pm_forward_stream_journal` tables |
| Recovery comparison | `reconcile_public_wallet_fills` in the existing public-trade owner |
| Uninstalled shadow-unit templates | `pm_forward_public_unit.continuous_unit_templates` |
| Unsigned wheel staging | Existing `stage_unprotected_release_candidate` / candidate verifier |

The default bounded CLIs remain supported. Continuous capture creates no PM-03
run and commits no financial event. Independent status always retains
`financial_admission=BLOCKED_NO_TRADE`, `paper_observed=false` and
`order_route=NONE`. Current feed health is a different field.

## Candidate configuration and preflight

Use an absolute private state directory outside all existing journals and
worktrees. Never point the candidate at the active observer or an account WAL.
The CLI verifies the exact clean Git revision, or the separately hashed source
release tree. A dirty checkout is not a pinned release.

Example configuration (replace every capitalized placeholder with measured,
pinned values; do not deploy this example unchanged):

```json
{
  "schema": "paper_continuous_observer_config_v1",
  "revision": "EXACT_40_HEX_COMMIT",
  "inventory_sha256": "ACTUAL_64_HEX_REGISTRY_INVENTORY",
  "portfolio_ids": ["P1", "P14"],
  "protected_roots": ["/absolute/existing/observer"],
  "market_scope_file": "/absolute/release/docs/FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json",
  "propr_snapshot": "/absolute/private/PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json",
  "duration_seconds": 0,
  "refresh_seconds": 300,
  "queue_size": 256,
  "min_free_bytes": 2000000000,
  "max_journal_bytes": 10000000000,
  "budget": {
    "reserved_connections": 7,
    "reserved_users": 5,
    "reserved_subscriptions": 100,
    "ccxt_markets_per_socket": 80,
    "public_markets_per_socket": 128,
    "max_markets": 200
  }
}
```

The reservation numbers above illustrate the syntax; they are not current
shared-IP evidence. Measure all other consumers, including rotating users and
services outside this checkout. A successful connection alone does not prove
capacity. The planner limits 10 connections, 10 user identities and 1000
subscriptions, including reservations. One account socket, two subscriptions
per CCXT market and one native public trade subscription per market are counted.
Every actual CCXT and native dial goes through a shared process limiter of six
attempts per minute. Existing callers have independent rate budgets; reserve
their headroom too.

The owner-selected Top-40 grouping is preserved in the configuration manifest.
The physical Propr-157 JSON additionally requires `propr_snapshot` pointing to
its exact SHA-verified external display snapshot. That displayed universe is
not proof of account orderability. Do not silently replace unavailable symbols,
drop HIP-3 prefixes or shrink the required denominator.

Preflight example, from the pinned environment:

```bash
copytrade-pm-paper-observe \
  --registry /absolute/private/wallet_registry.sqlite \
  --primary-dir /absolute/wallet_fills_90d \
  --secondary-dir /absolute/nansen_smart_money_fills_90d \
  --state-root /absolute/new/private/shadow \
  --continuous-config /absolute/private/continuous-config.json \
  --preflight-only
```

Preflight is read-only. It checks native registry integrity and signed-selection
proofs, exact sealed identity/exclusions, inventory-generation stability,
private paths, symlinks/hardlinks, writer lease, financial-journal collisions,
protected legacy heads and resource plan. It creates no journal and opens no
network connection. Missing NAV is not a startup gate. A real integrity,
selection-provenance or exclusion failure remains a gate and must not be waived.

## Frame semantics and first-known clocks

A connection or subscription acknowledgment is transport evidence. It is not
a position update, transaction, or guarantee of historical continuity.

Each account is keyed independently by its native identity. Parent aliases own
the existing source tape; child account hashes remain distinct inside it.
A successful official `perpDexs` and `subAccounts` census discovers all required
accounts. Failed refresh retains prior held hedge requirements and reports
unknown census. A removed child's last known hedge remains required until
explicitly resolved; absence never becomes a verified close.

The account parser accepts only the complete catalogued all-DEX replacement
shape. Missing DEX states, unknown delta fields, malformed snapshot flags,
wrong users and clock regressions are rejected. The first valid frame in every
new epoch is BASELINE. A later position difference is OBSERVED_STATE_CHANGE,
with `trade_verified=false`; it is not a verified fill. An explicit snapshot is
excluded from new-change signals. Incomplete equity stays null. Asynchronous
spot quote-collateral and account-mode diagnostics never become an atomic NAV.

Native WebSocket first-known time is captured immediately after raw receive,
before JSON decode or queueing. The exact raw string is hashed and retained in
private evidence. The pinned CCXT 4.5.91 hook captures inbound time before its
JSON/provider dispatch, and binds each native trade to its earliest local clock.
Upgrading CCXT requires a new instrumentation check. Native trade identity uses
coin, block time and `tid`; `tid` alone is not globally unique.

Source time, local first-known time, SQLite commit time, financial decision time
and hypothetical fill time remain separate. The trade cache is cloned for
validation and published only after its receipt and stream checkpoint commit.
A saturated queue, failed fsync, failed transaction or competing writer cannot
silently advance a checkpoint. Cancellation waits for an already queued commit
before a replacement processor can reopen its head.

## Scope, gaps and recovery

Required markets are configured native markets union all last valid held
positions, including hedge legs. Metadata validates exact native DEX identity.
Unsupported markets remain missing in the required denominator while valid
siblings continue. Scope changes restart affected shards and explicitly record
new epochs; they do not claim continuous coverage through a resubscription.

Every startup/reconnect writes GAP then obtains a fresh excluded baseline.
No missing interval is silently called complete. Public candidate deduplication
uses immutable native event identities and original earliest receipt clocks.
Replayed data cannot create a second wallet-side receipt or improve its clock.

Independent public `userFillsByTime` comparisons run at the refresh cadence.
The API returns at most 2000 rows per response and only the most recent 10000
fills remain available. The implemented comparison is explicitly bounded to
returned official rows, not a claim of complete exchange history. Comparisons use
the exact inclusive integer-millisecond request boundaries; original microsecond
UTC bounds and later local response clocks remain in the audit record. A repeated
boundary row cannot create a new prospective signal. Results are
INDEPENDENT_MATCH, RECOVERED_AT_LATER_TIME or UNRESOLVED. Recovered fills are
audit records only and are never inserted as earlier prospective candidates.
No late recovery resets the existing FIRST_SIGNAL_PLUS_5M deadline.

If disk headroom falls below its bound, journal size exceeds its cap, or SQLite
fails, the candidate stops. The process supervisor can restart it after storage
is repaired. Never remove a WAL file, rewrite old receipts or truncate a failed
audit log to make a gate pass.

## Independent health and real shadow accounting

Run the watchdog as a separate OS process. It verifies PID identity, heartbeat
age, release/config binding, stream-head prefixes, full stream and referenced
legacy hashes, required feed census, baseline validity, native ACKs, per-market
quote freshness, transport age, queue bounds and disk headroom.

A quiet wallet with fresh transport can remain connected. Its last state age
is reported independently and is not reset by heartbeat updates. The CCXT
acknowledgment field remains explicitly UNKNOWN where no independent ACK
record is retained; receiving parsed market data is counted separately.

The watchdog writes a private atomic current status and an append-only,
SHA-linked `continuous-watchdog.samples.jsonl`. The history is bounded to
100 MB and has an exclusive writer lease. It records process identity,
revision, feed summary hash, gap totals, queue/disk and process resource metrics.
A separate shadow report verifies that history and measures actual first-to-last
witness time. It reports latency percentiles from persisted post-baseline
source/quote/public frames, canonical wallet matches, reconciliation checkpoints
and stream counts. Sparse samples never become zero latency or 100% coverage.

Full independent lineage verification is intentionally conservative and grows
with the journal. Measure watchdog runtime, write rate and 72-hour disk
projection on the selected scope before accepting resource adequacy. A bounded
BTC probe does not qualify Top-40 or Propr-157 throughput.

## Stop, backup and restart

SIGTERM stops capture, drains queued commits and appends STOP/GAP evidence.
The exclusive observer lease prevents simultaneous lifecycle owners; every
SQLite transaction also uses the existing writer lock.

Use `PaperJournal.backup(destination)` during a quiesced candidate window for a
consistent new private copy. It verifies financial/source/quote heads plus
additive stream heads. Reopen and independently verify the copy. Never overwrite
a journal to roll back code. Retain both release and journal artifacts.

On process death, SQLite recovers committed WAL transactions; the next observer
reads durable heads and starts fresh epochs. Tests kill a writer before and
after COMMIT and verify exactly which progress survives. These are real process
crash tests, not a claim that the VPS was rebooted.

## Shadow installation and public cutover

`continuous_unit_templates` renders two distinct, uninstalled shadow units,
using exact release and config paths, preflight before capture, separate
watchdog, restart limits, private umask, restricted writes, CPU/memory/task
bounds and no credentials. It cannot authorize or activate them.

Before installing shadow units, require live registry/preflight success,
resource reservations for the shared IP, private new state, pinned verified
code and existing-service baselines. The mission authorizes a safe isolated
read-only shadow; it does not waive a failed selection or resource gate.

Keep collecting through 72 actual hours with independent witness coverage and
incident records. Review discrepancies only within a verifiably complete audit
scope; otherwise report UNKNOWN. Even a complete elapsed window returns
OPERATOR_ACCEPTANCE_REQUIRED, never automatic deployment authority.

Public cutover is a separate operation under the existing
[public-service release/rollback contract](FORWARD-PAPER-PUBLIC-OBSERVER-SERVICE-20261105.md).
Require accepted real shadow evidence, exact reviewed release/build provenance,
the existing independently trusted release checks, recorded operator
authorization, old unit/release hashes and verified rollback journals.
The current installer still enforces its release gate. No new template bypasses it.

Rehearse candidate installation, bad launch, bad health and restoration using
isolated unit names and separate state. Check the prior pinned reader against
the copied additive schema. Then stop the rehearsal units and preserve their
evidence. Actual public cutover may change only its specifically authorized
unit/release. Tracker, source-ABC, ensemble, broker and financial services remain
outside this program.

## Primary provider references

- [Hyperliquid WebSocket subscriptions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions)
- [Hyperliquid rate limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)
- [Hyperliquid info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
- Installed and locked CCXT 4.5.91 client/Hyperliquid dispatch code, verified by
  the raw-message regression test and separately scoped real transport evidence.
