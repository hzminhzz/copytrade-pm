# Changelog

All notable changes to `copytrade-pm` are documented in this file.

## [Single-owner appliance] - 2026-11-28

### Changed

- One configured CWSA workflow, generic paper portfolios, shared quote acquisition and daily wallet health through native systemd.
- One software checkout, frozen environment, private state root and lifecycle with CLI status, reconcile, update, recover and adoption operations.
- RosterStore schema 2 adopts immutable observation selections with original provenance and a separate adoption clock; no synthetic seat promotions.
- Discovery derives real parser leaves without the former AST inspection framework.

### Removed

- Ops Control Center, Site-related publication paths, dashboard infrastructure, frontend dependencies and CI.
- Prefect, independent worker deployment/release mechanisms and superseded historical experiment engines.
- Tests and comments for deleted features; retained accounting, PIT, checkpoint, mandate, fault and historical replay contracts remain tested.

Historical evidence and original journals remain authoritative. Runtime activation and verification are recorded separately from this code change. No scientific qualification or trading authority is granted.

## [Phase D Agent Onboarding Overhaul] - 2026-11-24

### Changed
- Streamlined `AGENTS.md` using `writing-for-agents` context pointers and checkable startup steps (`FactStore`, `RosterStore`, PM03 kernel decision, `copytrade-pm` CLI).
- Updated `docs/INDEX.md` top-level routing to `FACTS-STORE.md`, `ROSTER.md`, `CHECKPOINT-KERNEL-DECISION-PM03.md`, and `CHANGELOG.md`, and moved retired `WALLET-REGISTRY-*` guides to the historical evidence table.
- Updated `CONTEXT.md` with Portfolio/Seat/Style sleeve/`k`/Trailing DD/Paper-vs-Shadow-vs-Live terminology and noted `wallet_registry.sqlite` retirement.

## [Phase D & E — Unified FactStore, Dynamic Roster & Kernel Cutover] - 2026-11-20

### Added
- `copytrade_pm.facts`: day-partitioned `Decimal(38,12)` Parquet `FactStore` (`fills`, `positions`, `equity`, `funding`, `ledger`, and bi-temporal `bars_1m`), SQLite manifest (`facts.sqlite`), ingest-time `arrival_seq` burst repair, strict `as_of_ms` / `allow_unknown_known_at` PIT scanning, `coins=` filter, and causality enforcement (`first_known_at_ms >= event_ts_ms`).
- `copytrade_pm.roster`: `SeatBook`, `SeatSpec`, `SeatLease`, `DrainingOwner`, `AllocationMode.FLAT`, terminal epoch-latched `RosterCUSUMState`, `OperatorVeto`, `RosterStore` (`roster.sqlite` append-only triggers and `authority_health`), `select_sealed_book`, and daily batched unsigned `ReleaseProposal` staging.
- `copytrade_pm.pm_checkpoint_decision` & `pm_mandate`: PM03 thin adapter over `copytrade_kernel.step_checkpoint` and `CopyMandateSpec`.
- Documentation: `docs/FACTS-STORE.md`, `docs/ROSTER.md`, `docs/CHECKPOINT-KERNEL-DECISION-PM03.md`, and `docs/decisions/2026-11-19-unified-bi-temporal-fact-store.md`.

### Changed
- Consolidated 41 experiment CLI entrypoints into `copytrade-pm` (`facts`, `research`, `roster`, `paper`, `release`, `capabilities`).
- Cut over `pm_forward_continuous`, `dashboard/adapter.py`, `wallet_health_official`, and `ops/wallet-health/daily.sh` from `wallet_registry.sqlite` to `RosterStore` / `FactStore` (`copytrade-pm facts capture-health`).
- Repinned `copytrade-kernel` in `pyproject.toml` and `uv.lock` from worktree-local path to the `prop-production` git revision (`#subdirectory=packages/copytrade-kernel`).

### Removed
- Deleted all 10 `wallet_registry*.py` modules, `pm_copy_mandate.py`, `wallet_health.py`, `scripts/registry_release.py`, `scripts/audit_wallet_registry_docs.py`, `scripts/verify_wr_fp_journal_contract.py`, and retired Grafana wallet-health dashboards/alerts.
- Retired the legacy `wallet_store` write path (reads remain available for historical archive migration only).
