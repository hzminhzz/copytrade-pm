# SQLite wallet registry — acceptance evidence, 2026-11-04

**Branch:** `feat/wallet-registry-wr01-12-20261104`, draft PR #57. Scope: owner-private metadata **only**. This record describes implementation evidence from the feature worktree and the owner-private registry database. A passing test is **engineering verification**, not paper execution, scientific qualification, or trading authorization.

The wallet/source facts below were verified against the private source SHA generation recorded in [the dated status](WALLET-STATUS.md). To assess current state, **re-run `doctor` and `paper`**, not this historical summary.

| Ticket | Stage | Engineering evidence | Remaining acceptance / limitations |
| --- | --- | --- | --- |
| [WR-01 #44](https://github.com/hzminhzz/copytrade-pm/issues/44) | ENGINEERING VERIFIED | Three SHA-checked 108/20/30 cohorts ->158 unique. Independent New50 113,273 fills/1,196 source pairs/1,197 pages. Frozen PM-01 36 aliases and original source SHA references preserved. | No full source-account reconstruction; not the objective of registry |
| [WR-02 #45](https://github.com/hzminhzz/copytrade-pm/issues/45) | ENGINEERING VERIFIED | Versioned SQLite v1–v5, stable wallet IDs, private perms 0700/0600, WAL/FULL, writer lock, no-op imports, rollback on error, online backup. | No need to turn metadata into a trading source |
| [WR-03 #46](https://github.com/hzminhzz/copytrade-pm/issues/46) | ENGINEERING VERIFIED | Owner-confirmed 22 exclusions (14/5/3), zero research overlap, source SHA. Independent vendor artifact manifest/SHA cross-check. Older wallet account completeness UNKNOWN. | Future changed owner rejection requires a new source/evidence generation |
| [WR-04 #47](https://github.com/hzminhzz/copytrade-pm/issues/47) | ENGINEERING VERIFIED | Read-only subscription DB schema and tracker.env allowlisted keys. 215 desired/150 subscribed, 19/9 research overlaps. No chat-ID output or live config write. | Source counts are snapshot-specific |
| [WR-05 #48](https://github.com/hzminhzz/copytrade-pm/issues/48) | PARTIAL / FAIL CLOSED | Indexed bounded ledger read-only observation, source-ledger identity SHA, cursor/retention checks, activity distinct from admission. | Independent admission and complete receipt-health proof are **UNKNOWN**; outbox activity does not prove them |
| [WR-06 #49](https://github.com/hzminhzz/copytrade-pm/issues/49) | ENGINEERING VERIFIED | Seven document/Git-SHA sealed research decisions, conservative source-known selection, deterministic definition SHA, PIT queries and source drift guards. P1/P14 both $600 nominal research budget. | P1/P14 actual source-account identity/equity and full books unproven; never activate from selection alone |
| [WR-07 #50](https://github.com/hzminhzz/copytrade-pm/issues/50) | CONTRACT VERIFIED, PUBLISHER MISSING | Read-only owner-private v1 paper manifest/status/journal observer; stale worker/feed/quote/PID/identity tests; separate run/account refs. | **0 currently registered runs**. FP-10 #67 requires a genuine paper publisher to validate the interface; **draft FP PR #73's `paper_run_manifest_v1` fields/SQLite journal currently differ from the provisional registry projection**, so cross-program acceptance is explicitly BLOCKED until the final adapter is reconciled; global running count UNKNOWN |
| [WR-08 #51](https://github.com/hzminhzz/copytrade-pm/issues/51) | GUARD VERIFIED, EXTERNAL EVIDENCE BLOCKED | SQLite v5 rejects unsupported positive qualification or trading authorization; status remains NOT_ESTABLISHED. Existing PM02 frozen-36 regression and signature verification components remain authoritative. | Independent positive signed 300s follower/control economics **not operational/verified**. No invented qualification or owner authorization |
| [WR-09 #52](https://github.com/hzminhzz/copytrade-pm/issues/52) | ENGINEERING VERIFIED | `sync --dry-run/apply`, `status`, `doctor`, `runtime`, `wallet`, `cohort`, `portfolio --asof`, `paper`, `backup`, `report --redacted`. SHA and freshness/unknown checks. | No publication of raw wallets/secrets or automatic public status writer |
| [WR-10 #53](https://github.com/hzminhzz/copytrade-pm/issues/53) | PARTIAL ACCEPTANCE | Core/native tests, Ruff/format/build, concurrent writes, SIGKILL rollback, source drift, SQLite full rollback, WAL reader continuity, online backup, symlink/private permissions and untrusted paper manifests; actual original PM02 36-wallet frozen report regression passed. | Complete independently reviewed production fault/recovery and private user/service parity signoff still open |
| [WR-11 #54](https://github.com/hzminhzz/copytrade-pm/issues/54) | PRIVATE ON-DEMAND PREVIEW ONLY | Owner-private SQLite at `/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite`, permissions, restore-able verified backups and live read-only source doctor. Existing three services active and never restarted. | No autonomous systemd timer or final controlled release acceptance. **Do not claim production registry deployed** |
| [WR-12 #55](https://github.com/hzminhzz/copytrade-pm/issues/55) | CANONICAL DOCS IMPLEMENTED | [Wallet status](WALLET-STATUS.md), [status checkpoint](WALLET-REGISTRY-STATUS-20261104.md), [paper boundary](WALLET-REGISTRY-PAPER-CONTRACT-20261104.md), INDEX, RUNBOOK, AGENTS and DATA-ACQUISITION updated. | Historical archival withheld until reference audit; never delete frozen source reports |

## Tests and recovery

- Core command: `uv run --group dev python -m pytest -q tests`.
- Native-market command: `uv run --extra market --group dev python -m pytest -q tests`.
- Ruff, Ruff format, `uv build`, `git diff --check` executed from this feature worktree.
- Read-only original PM-02 parity: `tests/test_pm03_scenarios.py::test_real_36_wallet_pm02_parity_if_owner_private_fixture_available` passed against the original private SHA-pinned report; **36 wallets, zero qualified**.
- Backup verification uses owner-private SQLite online backup then integrity check; no source/tracker/connector journal copying. The owner-private registry can be rebuilt from currently available original source files, but cannot repair missing first-known prospective observations by replaying vendor timestamps.

## Hard fail-closed boundaries

1. **No automatic subscription or broker mutation.** Production tracker/ensemble/source-ABC and Propr/Bybit journals are outside the registry's write authority.
2. **No paper-running inference from research selection**. Runtime is only observed on genuine per-run worker/status/publisher artifacts; missing publisher means UNKNOWN, not fictitious running.
3. **No scientific alpha inference** from vendor fill totals, past Gemini results, provider PF, a synthetic SQLite journal, or passing tests.
4. **No forward-paper publisher substitution**. FP-09/#66 and FP-10/#67 own delivery and integration of actual paper finance/runtime; the registry is an optional read-only consumer.
5. **No unverified positive qualifications**. The prospective matched-source/control signoff producer and explicit trading authorization are independent prerequisites. v5 guard cannot be bypassed by changing a report field.
6. **No production cutover without independent fault review**. This draft PR stays open until the actual external and release gates have evidence; an on-demand private inventory is not the final deployment.
