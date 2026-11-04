# SQLite wallet registry — 2026-11-04 engineering checkpoint

**State: PARTIAL IMPLEMENTATION. Do not claim all WR-01–WR-12 acceptance is complete.**

This checkpoint describes the initial implementation of the owner-private registry, not a source-account book, trading service, qualified wallet roster, or production adoption signoff. [Approved design](WALLET-REGISTRY-SQLITE-ADOPTION-PLAN-20261104.md), GitHub issues #44–#55.

## Source snapshot, independently observed 2026-11-04

- Research cohorts: 108 + 20 + 30 = **158 distinct**. Verified by direct normalization of the three owner-private source CSVs.
- Tracker configured desired: **215** addresses, read from `TRACKER_DESIRED_WALLETS` only.
- Subscriber SQLite: **150** distinct addresses; **19** research overlap desired and **9** research overlap subscribed.
- New50 independent vendor audit: **113,273** vendor fill records / **1,196** vendor instrument pairs. This is retrospective vendor coverage, **not** whole-account or follower-economic completeness.
- Exclusions: the current owner rejected **22**-wallet file is imported; the full 28-rejection lineage and dated overrides require further independent reconciliation.
- Tracker/ensemble/source-ABC services were active at the initial systemd inspection. The optional `runtime` command executes index-backed, read-only last-outbox-event lookups bounded at 500 addresses. On the live 215 configured wallets, 215 had an outbox event timestamp in the prior hour at inspection. This demonstrates *recent ledger emission*, **not** runtime admission, subscriber-specific health, or end-to-end receipt completeness. Both admission and receipt-level health remain **UNKNOWN**.
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
uv run --group dev copytrade-wallet-registry cohort research-108
uv run --group dev copytrade-wallet-registry portfolio P1
uv run --group dev copytrade-wallet-registry portfolio P1 --asof 2026-11-03T00:00:00+00:00
uv run --group dev copytrade-wallet-registry report --redacted
```

**Important:** `sync --apply` mutates **only the new private registry**. Other databases are opened with SQLite `mode=ro` + `query_only`. It requires private directory mode 0700 and database mode 0600. All imported portfolio versions are research-only, with no derived running status. Each source SHA is included in the private registry, not its raw source contents in Git.

## Initial implementation and required work

Current module: `src/copytrade_pm/wallet_registry.py` with core identity normalization, cohort overlap checks, vendor-audit count reconciliation, owner rejected exclusions, privacy-safe source digests, SQLite migrations, WAL/FULL, writer locking, transactional replay, read-only subscriber access, portfolio proposal metadata, unknown admission/qualification and CLI.

**Not complete:** complete P1 private alias resolution and independently versioned portfolio selection timestamps (the CLI's current as-of queries conservatively use the registry import knowledge time); all 28 exclusion decisions; independently verified PM-01 consumer output SHA parity (frozen 36 identities and source SHA pointers are checked); independently established runtime admission and receipt health (bounded outbox observation is implemented but insufficient for either); independent paper/demo run manifest/heartbeat validation; independent scientific evidence ingestion; archive and stale status hygiene; comprehensive concurrency, crash/restart, backup/restore and out-of-disk fault matrix (synthetic online backup/restore smoke now passes); refreshed-source atomic generation semantics; release timer; production activation signoff.

The initial import deliberately blocks replacing a database that contains run/qualification records; a non-destructive versioned import is required before those can be safely indexed. Do not treat a successful `sync --apply` as completion of WR-11.

No live services were restarted or subscription/broker configurations modified by the registry implementation. Keep the registry as an isolated owner-private inventory until the remaining gates pass.

## Handling uncertain state

- SOURCE_EVENT_TIME is vendor retrospective clock and must never become FIRST_KNOWN_TIME.
- Missing account completeness, reconstructed episodes, signed execution outcomes and independent auditor reports remain UNKNOWN/BLOCKED.
- Configured, subscribed, admitted, healthy, proposed portfolio, active portfolio run, qualified wallet and trading authorization are separate facts.
- Existing 36-wallet PM-01/PM-02 evidence and original research pages stay immutable.
