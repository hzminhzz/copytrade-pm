# SQLite wallet registry — 2026-11-04 engineering checkpoint

For a short entrypoint consult [the dated canonical wallet status](WALLET-STATUS.md) and [the WR acceptance matrix](WALLET-REGISTRY-ACCEPTANCE-20261104.md). This checkpoint records engineering details; none substitute for live source checks.

**State: PARTIAL IMPLEMENTATION. Do not claim all WR-01–WR-12 acceptance is complete.**

This checkpoint describes the initial implementation of the owner-private registry, not a source-account book, trading service, qualified wallet roster, or production adoption signoff. [Approved design](WALLET-REGISTRY-SQLITE-ADOPTION-PLAN-20261104.md), GitHub issues #44–#55.

## Source snapshot, independently observed 2026-11-04

- Research cohorts: 108 + 20 + 30 = **158 distinct**. Verified by direct normalization of the three owner-private source CSVs.
- Tracker configured desired: **215** addresses, read from `TRACKER_DESIRED_WALLETS` only.
- Subscriber SQLite: **150** distinct addresses; **19** research overlap desired and **9** research overlap subscribed.
- New50 independent vendor audit: **113,273** vendor fill records / **1,196** vendor instrument pairs / **1,197** pages. Both the independently produced integrity report (`fe292a469d80...`), final roster (`e104e945ac73...`), and source manifest (`8852d5415b7c...`) are SHA-cross-checked on import. The audit explicitly says `scientifically_qualified=false` and `qualified_whole_hyperliquid_account_books=false`. This is retrospective vendor coverage, **not** whole-account or follower-economic completeness.
- Exclusions: **22 unique owner-rejected wallets confirmed** for the 2026-11-03 private source generation: 14 truncated short-span Nansen, five underwater bagholders, three passive maker scalpers. The source file SHA-256 is `06b90eed43ce32636a2ceefab2449d73a134529749f0a03b702237f676ad36ee`. The prior 28-count requirement was an unsupported planning assumption, not six missing exclusions. Keep all 22 excluded; future additions require source evidence and a new versioned import.
- Tracker/ensemble/source-ABC services were active at the initial systemd inspection. The optional `runtime` command executes index-backed, read-only last-outbox-event lookups bounded at 500 addresses. On the live 215 configured wallets, 215 had an outbox event timestamp in the prior hour at inspection. This demonstrates *recent ledger emission*, **not** runtime admission, subscriber-specific health, or end-to-end receipt completeness. Both admission and receipt-level health remain **UNKNOWN**.
- **WR-05 evidence limitation verified against deployed SQLite ledger schema (2026-11-04):** only `ledger_meta`, `receipts`, `position_checkpoints`, `outbox_events` were present. `outbox_events` has a bounded wallet index; `receipts` has a status index but no independently verified per-wallet admission/completeness interface. Even a recent `ACCOUNT_SNAPSHOT` outbox event and a generic `SUCCESS` receipt cannot establish runtime admission or continuous receipt health; both remain **UNKNOWN**.
- Paper/demo **RUNNING** statuses **UNKNOWN**, not inferred from portfolio proposals or previous account canaries.
- Scientifically qualified and trading-authorized wallets **NOT ESTABLISHED**. Original PM-01 36-wallet contract unchanged.

## Initial commands (read-only existing production sources)

The local Python package installs `copytrade-wallet-registry`. From the repository:

```bash
uv run --group dev copytrade-wallet-registry sync --dry-run
uv run --group dev copytrade-wallet-registry sync --apply
uv run --group dev copytrade-wallet-registry status
uv run --group dev copytrade-wallet-registry doctor
uv run --group dev copytrade-wallet-registry runtime
uv run --group dev copytrade-wallet-registry wallet --alias W028
uv run --group dev copytrade-wallet-registry cohort research-108
uv run --group dev copytrade-wallet-registry portfolio P1
uv run --group dev copytrade-wallet-registry portfolio P1 --asof 2026-11-03T00:00:00+00:00
uv run --group dev copytrade-wallet-registry paper
uv run --group dev copytrade-wallet-registry report --redacted
```

**Important:** `sync --apply` mutates **only the new private registry**. Other databases are opened with SQLite `mode=ro` + `query_only`. It requires private directory mode 0700 and database mode 0600. All imported portfolio versions are research-only, with no derived running status. Each source SHA is included in the private registry, not its raw source contents in Git.

## Initial implementation and required work

Current modules: `wallet_registry.py`, `wallet_registry_portfolios.py`, `wallet_registry_runs.py`, and `wallet_registry_fp_journal.py`: core identity normalization, vendor-audit count reconciliation, owner rejected exclusions, private SHA references, schema migrations v1–v5, WAL/FULL writer locking, read-only subscriber/ledger adapters, SHA-sealed portfolio declarations, conservative as-of selection, and a strictly read-only paper-status observer. The paper observer now reads FP PR #73's **actual SQLite `PaperJournal` contract** through `mode=ro` and `query_only`. An actual cross-branch FP writer HALT smoke verified P1 SHA, manifest, cursor and bounded hash tail without changing the source; **no independent live P1/P14 worker is verified**. The obsolete incompatible JSONL v1 projection is rejected. A durable publisher/worker heartbeat remains missing for FP-10, so no paper RUNNING claim is established. Subsequent source generations use **non-destructive transactional import**: canonical wallet IDs remain stable, historical cohort and evidence SHA versions survive, monitoring generation metadata is retained, and existing external run/qualification index entries are not erased. Source drift and frozen alias collisions fail closed.

**Not complete:** complete P1 private alias and independent source-account identity proof (source-commit-backed selection timestamps and deterministic portfolio SHA are now implemented); future exclusion decision lineage and source-drift verification (all current 22 owner rejections imported); independent consumer parity beyond the existing PM-02 frozen-36 artifact regression (the installed `pm02-7bf28ee5...` artifact was verified by its read-only regression: 36 wallets, zero qualified, SHA pinned); independently established runtime admission and receipt health (bounded outbox observation is implemented but insufficient for either); independent real paper/demo worker and heartbeat publication (actual FP journal read-only interoperability is established, but not worker liveness); independent scientific evidence ingestion; archive and stale status hygiene; comprehensive concurrency, crash/restart, backup/restore and out-of-disk fault matrix (synthetic online backup/restore smoke now passes); refreshed-source atomic generation semantics; release timer; production activation signoff.

The importer preserves existing run/qualification rows even across source generation changes. Seven proposal selection declarations now have deterministic hashes and anchored public document revisions. Only an explicitly published paper run with fresh transport/quote heartbeats and process identity can be observed as running. There are **no actual forward-paper runs indexed in the current release**. No independently audited scientific or authorization decisions have been imported. A v5 fail-closed SQLite trigger now rejects any attempt to write a positive science/authorization verdict into the research index until an independent signed-economics signoff and separate owner authorization protocol actually exist. Do not treat a successful `sync --apply` as completion of WR-11.

No live services were restarted or subscription/broker configurations modified by the registry implementation. Keep the registry as an isolated owner-private inventory until the remaining gates pass.

## Handling uncertain state

- SOURCE_EVENT_TIME is vendor retrospective clock and must never become FIRST_KNOWN_TIME.
- Missing account completeness, reconstructed episodes, signed execution outcomes and independent auditor reports remain UNKNOWN/BLOCKED.
- Configured, subscribed, admitted, healthy, proposed portfolio, active portfolio run, qualified wallet and trading authorization are separate facts.
- Existing 36-wallet PM-01/PM-02 evidence and original research pages stay immutable.
