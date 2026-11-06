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

The lock operation requires the owner-private 0700 directory and 0600 file, a verified `sqlite3.Connection.backup()` copy in the private `backups/` directory, and an optimistic comparison against the **complete authoritative inventory SHA**. It then writes only the `legacy_import_locked_at` marker and four database triggers. A locked marker without the exact expected triggers is an integrity failure in `doctor` and cannot be reported as a healthy disabled legacy writer. Both Python `sync --apply` and the older SQLite importer `import_runs` insert are blocked. The triggers also prevent an older writer from resetting the SQLite `monitoring` snapshot. The real tracker is not restarted or modified.

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

Registration is an explicit backed-up, transactional, generation-checked write. It preserves existing wallet rows and full prior cohort versions, appends an alias only if it has no conflicting canonical identity, stores an immutable owner-private 0600 manifest snapshot under `evidence/native-cohorts/<sha256>.json`, and indexes its content SHA plus path. The source can be re-verified without relying on a mutable original input file. Revising a cohort adds a version containing all existing members plus new valid members, rather than silently deleting previously admitted wallets. Original PM-01/36-wallet and legacy 108/20/30 imports cannot be overwritten via this native path. Reapplying an identical manifest is idempotent only after the original archived bytes and native cohort versions have been verified. The registry doctor also checks SHA-addressed native cohort archive and membership consistency, including prior versions; deleted or corrupt evidence fails closed. A content hash proves bytes, not that a person independently signed the manifest.

**No automatic admission:** native registration does not subscribe a wallet, declare profitable behavior, promote portfolio selection, launch a paper worker, infer source equity or authorize trading. New owner-approved portfolio selections still use the existing signed-selection workflow; protected immutable portfolio versions remain authoritative in SQLite.

## Native append-only owner exclusion decisions (issue #114)

This interface is **separately protected** from cohort registration. It accepts only registered Hyperliquid mainnet addresses as resolved by the current SQLite inventory. It does not accept aliases, database-local wallet IDs, backdated timestamps, revocations or wildcard status changes. The decision file must be reviewed, private (0600 under a 0700 directory) and contain short uppercase reason codes.

Example using a **synthetic address**, not a real blacklist:

    {
      "schema": "sqlite_wallet_exclusions_v1",
      "decisions": [
        {"address": "0x0000000000000000000000000000000000000001", "reason_code": "OWNER_REJECTED"}
      ]
    }

The address must already exist in SQLite. The manifest's **raw-byte SHA-256** is an explicit second input, distinct from the live SQLite inventory SHA. No reviewer should apply a decision against changed source bytes or a different inventory generation.

Read-only review:

    uv run --frozen --group dev copytrade-wallet-registry native exclude --manifest PRIVATE_0600_MANIFEST --expected-manifest-sha REVIEWED_RAW_SHA256 --expected-inventory-sha LIVE_SQLITE_INVENTORY_SHA

Protected mutation, only after backup, owner review and explicit cutover authorization:

    uv run --frozen --group dev copytrade-wallet-registry native exclude --manifest PRIVATE_0600_MANIFEST --expected-manifest-sha REVIEWED_RAW_SHA256 --expected-inventory-sha LIVE_SQLITE_INVENTORY_SHA --apply

The writer checks both hashes, existing decisions and unique identities, backs up SQLite, seals exact input bytes under private immutable evidence, then atomically appends evidence_artifacts, evidence_versions and exclusions with the **actual first-known receipt time**. A content SHA establishes byte identity, not who approved a decision; the result explicitly reports owner_review_attested=false until a separate independent approval contract exists. Reapplying the same manifest is idempotent after archive and database-row verification. A different reason for an already excluded wallet fails closed for a separately reviewed policy. A pre-commit error rolls back all database rows. Archived immutable source bytes may remain after an error, but no exclusion or authorization is committed.

The original 22 owner exclusions remain untouched. An exclusion is **not** paper admission, scientific qualification or a command to change tracker subscribers. Revoking earlier exclusions is explicitly out of scope. Read-only wallets list --excluded and as-of filters reflect native decisions without legacy CSV sync.

**Deployment dependency:** this work is stacked on PR #112. Do not apply to production before the base release passes hosted core/market checks, is reviewed/merged/pinned, and the backup-protected legacy lock passes PID and integrity gates. Live blacklist changes need a separate approved manifest. No automatic cleanup is authorized.

[ML4T evidence principles](ML4T-METHODOLOGY-LESSONS.md) guide screening but cannot automatically create exclusion decisions.

## Acceptance and operational safety

Before merged release or live lock: test core and market suites, Ruff lint/format, build and capability validation; verify no missing docs links; validate `doctor`, private backup integrity, import idempotency, conflict/permission failures, SQLite triggers against legacy writers, original frozen portfolios and live running service PID parity. Confirm the current release pointer remains usable; code merge alone is not deployment. No broker, paper worker or production tracker mutation is part of this work.

**Known remaining scope:** global automatic indexing of all disparate immutable research report formats is not implemented by this change. `copytrade-pm research list --cache-root` remains scoped to SHA-verified native offline-job reports. Do not claim that every historical Markdown experiment has been ingested or qualified.
