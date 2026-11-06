# November 5, 2026 — SQLite and ML4T ingestion-evidence audit

**Read-only checkpoint, not a qualification report.** Audit performed on the actual VPS owner-private SQLite v8 using the current pinned read release. No database, source, subscriber, paper service or broker mutation was performed.

## Reproducible entrypoints

    uv run --frozen --group dev copytrade-wallet-registry doctor
    uv run --frozen --group dev copytrade-wallet-registry native status
    uv run --frozen --group dev copytrade-wallet-registry cohort ml4t-top6
    uv run --frozen --group dev copytrade-pm wallets list --cohort ml4t-top6 --limit 20
    uv run --frozen --group dev copytrade-wallet-registry qualification
    uv run --frozen --group dev copytrade-wallet-registry paper
    uv run --frozen --group dev python scripts/registry_release.py verify
    uv run --frozen --group dev copytrade-pm health

## Verified observations

| Domain | Observation |
| --- | --- |
| Installed read-only release | f0fa6e7ebc4c8841f3ad3f00a0846a01d65d036c, ACTIVE_READ_ONLY_VERIFIED |
| Current authoritative inventory SHA | 92cc500c4eaaa5ad78346a3037ebf8dc1c11b464c81fe48e589be5422937d27b |
| SQLite | v8, integrity VERIFIED, authority SQLITE |
| Research cohorts | research-108=108, nansen-20=20, hyperx-30=30, ml4t-top6=6; 164 distinct research identities |
| ML4T cohort | Six registered aliases H31–H36, no observed current tracker subscription or paper admission in its registry projection |
| Import evidence gap | ml4t-top6 has UNVERIFIED_IMPORT_LABEL; membership is valid metadata but not a SHA-pinned independent economic source |
| Owner exclusions | 22 distinct historical identities in authoritative SQLite; no native exclusions applied during this audit |
| Registered portfolio definitions | 11 source-sealed versions; selection E6 primary, E2 challenger is research-only |
| Tracker snapshot | 264 configured / 264 subscribed; live admission/receipt health UNKNOWN |
| Indexed paper runs | 0; protected P1/P14/watchdog OS units NOT_RUNNING |
| Scientific qualification | NOT_ESTABLISHED; no independently verified positive matched follower/control result |
| Trading authorization | False |
| Legacy writer | UNLOCKED_LEGACY_WRITER; PR #112 lock has not been activated |

## Research-screening verdict

The system **can register, resolve and enumerate wallet metadata** from current SQLite; the independently exercised CLI and native tests confirm alias/known-at/privacy behavior. However, the six new ML4T wallets are **not source-provenance-complete** and none of the 164 wallets has been qualified here by real, first-known, account-complete equity, matched follower PnL, execution/fee/funding and an independent paper holdout.

External 90-day return, PSR, skew, regime and slippage CSVs retained outside this branch have not been independently reconciled to complete source NAV or real follower books. They remain **preliminary historical screens**. A high model Sharpe, 180-day fill availability or a hypothetical challenge pass cannot be converted into an approved exclusion or live trade.

The [ML4T methodology](ML4T-METHODOLOGY-LESSONS.md) documents guards for point-in-time provenance, nonnormal returns, costs and risk dependence. It deliberately avoids silently imposing arbitrary screening cutoffs.

## Engineering scope and blockers

- PR #112 contains native cohort writes plus the backed-up legacy lock; current hosted CI fails before jobs start (issue #113), despite local tests.
- This stacked change adds a separately protected append-only native exclusion command (issue #114), checked with disposable test databases; no production exclusion decision was applied.
- Repairing the six-wallet import provenance requires real independent SHA-addressed source artifacts. Do not synthesize a source manifest by dumping SQLite rows or reinterpret the earlier unverified text label as a hash.
- Protected paper readiness still requires whole-wallet account-mode NAV, complete parent/subaccount positions, real first-local receipts, verified market costs and matched follower/control outcomes. Keep NO_TRADE until independent gates pass.

This checkpoint is a dated diagnostic. For any subsequent status question, run the live registry doctor and installed-release check again; neither OptMem nor this document is live authority.
