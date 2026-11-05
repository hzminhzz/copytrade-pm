# SQLite-primary operational registry — 2026-11-05

## Decision and scope

**Approved:** SQLite is the only authoritative mutable registry for **current** wallet identity, research cohort membership, exclusions, operational portfolio selections, and versioned registry state. Legacy CSV/JSON/Markdown exports are not live rosters. They cannot overwrite an activated SQLite registry.

This policy does **not** make SQLite the source of unobserved economics, historical first-known data, source account NAV, real subscriptions, running services, scientific qualification, or order authorization. Distinguish these authorities:

| Question | Authority | Legacy / supplemental reference |
| --- | --- | --- |
| What wallets and research cohorts are indexed? | Private SQLite `wallets`, `cohorts`, `cohort_memberships` | Historical vendor CSV, discovery reports |
| Alias identity at a cutoff | Private SQLite `wallet_aliases` as-known, conflict gated | Private alias evidence hash; no retroactive mapping |
| Which portfolios are selected *now*? | SQLite `research_selections` with signed/immutable definitions | Dated Git decision JSON evidence |
| Which portfolios have immutable historical definitions? | SQLite `portfolio_versions` / `portfolio_seals`, SHA references | Git source snapshots as historical provenance |
| Which research runs are indexed? | SQLite metadata **when imported and verified** | Original immutable JSON/Parquet job artifacts |
| Which subscriptions actually run? | Live tracker configuration, ledger, subscriptions and worker | SQLite monitoring snapshot is **observation**, not a runtime write contract |
| Is real paper economically running? | Independently verified worker, journal, fresh source and market receipts | Registry pointer alone is insufficient |
| What was actually filled or paid? | Signed financial/broker journal and original immutable receipts | SQLite metadata index is not economic truth |
| Scientific qualification, broker trading authority | Separate protected attestation and explicit owner authorization | No auto-promotion from status/CI |

Parquet and DuckDB remain the analytical interface for large historical fills, minute bars, and sweeping portfolios. Do not copy bulk market or raw fill data into SQLite.

## Authority modes

- `LEGACY_IMPORTED_V1` (historical/default): `sync --apply` can bootstrap or refresh from the dated source importer. `doctor` compares source SHA/count parity and may fail on legitimate later SQLite-only additions.
- `SQLITE_PRIMARY_V1` (activated): SQLite is authoritative for operational registry reads. `doctor` checks SQLite integrity and reports the generation. The legacy importer is *disabled for writes*. `sync --dry-run` remains diagnostic only, and its counts are not current authority.

All CLI results must disclose the effective authority mode and registry generation. In primary mode, `freshness=CURRENT` means a valid indexed database, **not** up-to-date subscription/financial receipts. The separate `source_snapshot_freshness` field retains the last independently observed legacy snapshot age.

### Safe cutover

The cutover is an explicit protected operation, **never run as a side effect of import, read, CI, application startup, or release installation**.

1. Read `AGENTS.md`, the live registry-first workflow, `origin/main`, actual GitHub CI and installed release. Preserve dirty worktrees and all running service PIDs.
2. Inspect `copytrade-wallet-registry status`, `doctor`, `authority status`, original migration history and `PRAGMA quick_check` / `foreign_key_check`. Confirm which of 158 legacy and additional manually registered cohorts should remain. **Never delete new cohorts to match a 158-wallet CSV cut.**
3. Verify the reviewed primary-capable code and pinned-release candidate against a disposable copy of the current database in both modes. Store an independently verified SQLite backup. In particular, a pre-cutover `LEGACY_IMPORTED_V1` doctor may fail because of legitimate SQLite-only cohorts; do not misreport this as source parity. The reviewed cutover sequence is backup → primary-mode activation → compatible pinned release activation and verification, with the original pointer preserved until the final activation is verified.
4. Preview using the current, **exact** generation from `authority status`:

   ```bash
   uv run --frozen --group dev copytrade-wallet-registry authority status
   uv run --frozen --group dev copytrade-wallet-registry authority activate --expected-generation GENERATION_SHA
   ```

5. Apply only with reviewed owner approval and a verified rollback path:

   ```bash
   uv run --frozen --group dev copytrade-wallet-registry authority activate --expected-generation GENERATION_SHA --apply
   uv run --frozen --group dev copytrade-wallet-registry doctor
   uv run --frozen --group dev copytrade-pm health
   ```

Activation takes a consistent **online** pre-cutover backup under the private registry `backups/` directory (0700 parent, 0600 file). It records `authority_mode`, `authority_activated_at`, `authority_updated_at` and a new generation SHA transactionally. SQLite-level triggers also reject legacy `import_runs` inserts and monitoring-table writes after activation, including attempts from older Python release binaries; future tracker synchronization requires a separately reviewed versioned path. No portfolio membership, source identity, exclusion, paper, or monitoring row is replaced. Duplicate activation is idempotent.

A pinned release built for `LEGACY_IMPORTED_V1` may not understand primary mode: deploy and verify compatible code as part of the cutover; do not turn off safety gates to achieve activation. **Code rollback alone cannot revert a SQLite schema/mode cutover.** Full restoration requires a separately reviewed offline restoration from the verified pre-cutover backup; never blindly overwrite the active database.

### Native wallet/cohort registration (only after cutover)

Submit an owner-private 0600 JSON manifest under a 0700 directory; never put addresses in Git, shell arguments, Telegram or logs. Example with synthetic placeholder addresses:

```json
{
  "schema": "sqlite_wallet_import_v1",
  "cohort": "next-research-wave",
  "wallets": [
    {"address": "0x0000000000000000000000000000000000000001", "aliases": ["RESEARCH001"]}
  ]
}
```

Preview with `authority register --manifest PRIVATE_MANIFEST --expected-generation GENERATION_SHA`; add `--apply` only after review. Native registration:

- validates private permissions, addresses, duplicate aliases, cross-namespace identity conflicts and generation;
- creates a transactionally backed-up new `cohorts` version; existing cohort members persist, rather than being dropped by a short input;
- appends first-known `wallet_aliases` under the `sqlite_primary` namespace; never rewrites prior or frozen mappings;
- records manifest SHA and an updated SQLite generation with no disclosed private wallet addresses;
- leaves live tracker configuration/subscriptions, exclusion decisions, sealed portfolio selections, qualification and paper journals unchanged.

The existing `signed-selection` contract remains the controlled input for a new research-only portfolio selection. Its signed manifest is **evidence submitted to SQLite**, not a competing current selection index. Historical frozen Git decisions are preserved.

### Failure semantics and remaining work

- A wrong expected generation means another writer acted: **fail closed** and re-query. Do not retry by guessing a SHA.
- A corrupt database, FK violation, alias collision, loose permissions, or invalid manifest stops registration without changing the active generation.
- New wallet registration does **not** imply tracking, subscription, wallet profitability, permission to trade, or paper-worker admission.
- Partial source files remain `LEGACY` evidence; the database must not manufacture scientific evidence to fill gaps.
- Automatic indexing of *all* immutable research run types remains a follow-up. Current `copytrade-pm research list` still supports a scoped canonical offline job cache and is not a global historical research ledger.
- Future approved changes may add a separately validated registry-backed current eligibility/roster publisher for the tracker, with independent runtime acknowledgments. No automatic subscription mutation is included in this cutover.

## Acceptance

Run original core, optional market dependency tests, Ruff, format, build, registry doc audit, end-to-end native CLI, source/SQL integrity, and pinned-release preview/rollback checks. Before and after activation, verify wallet/cohort/portfolio/seal/exclusion row counts and hashes, source/tracker service PIDs, protected paper units, and no broker-order route. Do not label `DEPLOYED` until the installed pinned release is verified.
