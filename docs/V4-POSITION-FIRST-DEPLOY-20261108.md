# V4 position-first virtual-paper deployment (2026-11-08)

> **RETIRED / NON-EXECUTABLE HISTORICAL RECORD (2026-11-14):** The V4 first-known T0+300 operational policy and sixteen-portfolio paper executors (`pm_v4_selected_positions`, `pm_v4_sixteen_paper`) were retired and removed from the repository per [the V4 retirement ADR](decisions/2026-11-14-retire-v4-t300-source-policy.md). Do not execute commands in this document; use CWSA (`copytrade-cwsa-5m-source-chapter2.service` / `copytrade-cwsa-5m-paper-chapter2.service`, see [CWSA Chapter 2](CWSA-CHAPTER2-20261112.md)).

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

## Track A source-writer incident and 14-account SHADOW canary (2026-11-10)

This is a **preparation checklist**, not installation authorization. Issue #256
Track A changes only the existing SQLite `PaperJournal` writer. Its failure was
observed in `copytrade-v4-sixteen-source-0911.service`: 36 systemd restarts,
`sqlite3.OperationalError: database is locked` from `PaperJournal._writer()`.
The installed source database was approximately 5.74 GB with a 3.56 GB WAL;
two independent 16-portfolio consumers had open source DB handles. One legacy
consumer was in kernel `D` state. These measurements establish the incident,
not proof that a specific reader held the blocking SQLite lock at failure time.

`PRAGMA journal_mode=WAL` must be negotiated at journal initialization, not
on every receipt transaction. Writer lease contention is terminal for the
second process; SQLite BUSY/LOCKED is retried for at most two seconds **only
before any application transaction begins**. Permanent SQLite errors and
errors during BEGIN/COMMIT are not blindly replayed: the latter need durable
cursor inspection, source GAP and fresh excluded baseline after restart.
The independent consumer has no permission to repair source timestamps or
reconstitute missed receipts. Never delete, truncate, checkpoint manually or
move a live WAL while readers or source service are running.

Before an explicitly authorized canary:

1. Record `git rev-parse HEAD`, artifact and `uv.lock` hashes, `systemctl --user
   show copytrade-v4-sixteen-source-0911.service -p ExecStart -p MainPID -p
   NRestarts -p FragmentPath`, owner UID and exact selected 14-parent roster.
   Revalidate campaign manifest SHA, SQLite seals and provider connection budget.
2. Observe `fuser -v` of source DB/WAL/SHM/lock; record per-process reader
   ownership, `ps -o pid,stat,etime,args`, and source journal sizes and free
   disk. A blocked or uninterruptible reader is a preflight failure, not a
   reason to increase the SQLite timeout or force a checkpoint.
3. After identifying and resolving reader interference **under separate service
   authorization**, obtain `PaperJournal.backup` to a fresh private destination
   using its verified online backup contract; verify the backup heads, source
   `verify_streams` chain integrity, and preserve the immutable original WAL.
   Backups may be substantial: confirm physical free space first.
4. Pin a clean feature release with its exact commit and wheel hash. Prepare
   an uninstalled unit/rollback plan targeting the **same 14 selected parent
   accounts**, not an expanded registry. Keep original unit, original release
   and database available. Do not operate two source writers simultaneously.
5. Only after independent approval, conduct a bounded SHADOW source canary.
   Compare restart delta, writer failures by phase (lease, SQLite open/PRAGMA,
   transaction, commit), queue high-water, writer per-receipt latency, disk/WAL
   growth, cursor monotonicity, SHA integrity, real source GAP/baseline,
   consumer progress and original first-known timestamps. The bounded
   observer's `writer_health` on orderly stop reports `write_count`,
   `write_failures`, `max_write_ms`, `total_write_ms` and `queue_high_water`;
   production abnormal exits still require independent systemd/journal
   inspection rather than treating an absent final report as healthy.
   An authentic exit remains independently unverified until one occurs.

**Rollback after separately approved cutover:** stop only the candidate source
unit, confirm it has released its lease, select the previous verified pinned
release and restore its unit configuration without replacing or merging the
original journal. If source continuity was interrupted, preserve a genuine GAP
and new non-actionable baseline; never replay a historical receipt as a fresh
T0. Keep all 16 existing paper financial journals and Guardian unchanged.
The existing earlier V4 rollback below remains applicable to its own scope.

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
