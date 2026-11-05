# SQLite-native operations and legacy import write lock — 2026-11-05

## Decision

**SQLite is the canonical operational registry** for current wallet identity, cohort membership, aliases, exclusions, and saved research portfolio selections. This was established by PR #111. The historical CSV/JSON source importer is an optional **legacy acquisition/provenance adapter**, not an authority for current identities or research selections.

The SQLite registry does not own independently observed tracker subscriptions, active execution, paper account NAV, real broker orders, point-in-time fills, research market data or scientific qualification. These remain under their respective original authorities. The owner-private database is an index, not a substitute for immutable SHA-verified research evidence. Large historical fill/OHLCV data remains in Parquet/DuckDB.

## Source-authority separation

| Question | Current authority | Historical evidence |
| --- | --- | --- |
| Registered research wallets/cohorts | SQLite `wallets`, `cohorts`, `cohort_memberships` | Dated CSV/JSON vendor imports (legacy) |
| Canonical aliases | SQLite `wallet_aliases`, as-of known-at | Private identity manifests by SHA |
| Saved research portfolios and current selection | SQLite `portfolio_versions`, `portfolio_seals`, `research_selections` | Frozen signed Git decision JSON |
| Exclusions/eligibility metadata | SQLite `exclusions` and independently verified negative evidence | Archived owner decisions |
| Research run outcome/index | SQLite where validated evidence metadata exists | Original immutable JSON/Parquet report |
| Real subscriptions/worker health | Tracker actual config/database/ledger and systemd evidence | SQLite monitoring observations are a timestamped cache |
| Source NAV, positions, economic PnL | Independent source/broker/journal attestations | SQLite never synthesizes missing books |
| Qualification and trading authorization | Protected independent review and signed evidence | Cannot be inferred from registry presence or backtests |

## Read-only defaults

```bash
uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev copytrade-wallet-registry native status
uv run --frozen --group dev copytrade-wallet-registry cohort ml4t-top6
uv run --frozen --group dev copytrade-wallet-registry portfolio --current
uv run --frozen --group dev copytrade-pm wallets list --cohort research-108
```

`doctor` verifies SQLite integrity, schema v8 and a deterministic `inventory_sha256`. It does not need CSV files and does not treat the 158-wallet historical importer as the canonical research universe. `doctor --legacy-audit` is optional evidence-lineage diagnostics, not an authority gate. `native status` shows `SQLITE` and whether *legacy mutation paths* are locked.

The unified `copytrade-pm` read facade uses the **actual SQLite inventory SHA**, not the age of `snapshot_meta.observed_at` from a historical CSV import, for registry correctness and provenance. Legacy source age and live tracker receipt freshness remain independent dimensions.

## Controlled one-time legacy write lock

**Code installation does not mutate the database.** Activation is an explicit protected action. Verify source revision, installed release, running services, independent paper no-trade state and an online SQLite backup beforehand.

From a clean, reviewed checkout with the live DB available:

```bash
uv run --frozen --group dev copytrade-wallet-registry native status
uv run --frozen --group dev copytrade-wallet-registry doctor

# Substitute the exact inventory_sha256 returned by doctor.
uv run --frozen --group dev copytrade-wallet-registry native lock --expected-inventory-sha INVENTORY_SHA

# Protected metadata mutation, only after backup/rollback review:
uv run --frozen --group dev copytrade-wallet-registry native lock --expected-inventory-sha INVENTORY_SHA --apply

uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev copytrade-pm health
```

The lock operation requires the owner-private 0700 directory and 0600 file, a verified `sqlite3.Connection.backup()` copy in the private `backups/` directory, and an optimistic comparison against the **complete authoritative inventory SHA**. It then writes only the `legacy_import_locked_at` marker and four database triggers. Both Python `sync --apply` and the older SQLite importer `import_runs` insert are blocked. The triggers also prevent an older writer from resetting the SQLite `monitoring` snapshot. The real tracker is not restarted or modified.

**Rollback:** a code release pointer rollback does not automatically revert the on-disk lock or database. Older importer-capable releases should not be reactivated for writes. If the owner explicitly decides to reverse the protected cutover, use the verified pre-lock database snapshot through the existing offline recovery runbook. This requires separate review and must not overwrite later valid native registrations. There is no automatic destructive unlock command.

## Native wallet/cohort registration

Use owner-private 0600 JSON under a 0700 directory; never commit real wallet addresses, passwords or trading identifiers.

```json
{
  "schema": "sqlite_wallet_import_v1",
  "cohort": "research-next",
  "wallets": [
    {"address": "0x0000000000000000000000000000000000000001", "aliases": ["NATIVE001"]}
  ]
}
```

```bash
uv run --frozen --group dev copytrade-wallet-registry native register --manifest PRIVATE_MANIFEST --expected-inventory-sha INVENTORY_SHA
uv run --frozen --group dev copytrade-wallet-registry native register --manifest PRIVATE_MANIFEST --expected-inventory-sha INVENTORY_SHA --apply
```

Registration is an explicit backed-up, transactional, generation-checked write. It preserves existing wallet rows and full prior cohort versions, appends an alias only if it has no conflicting canonical identity, stores an immutable owner-private 0600 manifest snapshot under `evidence/native-cohorts/<sha256>.json`, and indexes its content SHA plus path. The source can be re-verified without relying on a mutable original input file. Revising a cohort adds a version containing all existing members plus new valid members, rather than silently deleting previously admitted wallets. Original PM-01/36-wallet and legacy 108/20/30 imports cannot be overwritten via this native path. Reapplying an identical signed manifest is idempotent.

**No automatic admission:** native registration does not subscribe a wallet, declare profitable behavior, promote portfolio selection, launch a paper worker, infer source equity or authorize trading. New owner-approved portfolio selections still use the existing signed-selection workflow; protected immutable portfolio versions remain authoritative in SQLite.

## Acceptance and operational safety

Before merged release or live lock: test core and market suites, Ruff lint/format, build and capability validation; verify no missing docs links; validate `doctor`, private backup integrity, import idempotency, conflict/permission failures, SQLite triggers against legacy writers, original frozen portfolios and live running service PID parity. Confirm the current release pointer remains usable; code merge alone is not deployment. No broker, paper worker or production tracker mutation is part of this work.

**Known remaining scope:** global automatic indexing of all disparate immutable research report formats is not implemented by this change. `copytrade-pm research list --cache-root` remains scoped to SHA-verified native offline-job reports. Do not claim that every historical Markdown experiment has been ingested or qualified.
