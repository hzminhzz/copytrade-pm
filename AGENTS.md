# copytrade-pm — agent operating contract

This repository owns **research facts, dynamic seat roster, original source observation, virtual paper, and offline release staging**, not broker authority. ChatGPT is the hands-on engineer. Do not delegate coding without an explicit user request. No broker credentials, live orders, protected Guardian changes, or trading authorization.

## First inspection

1. State the requested outcome, exact target and authorized read/write scope. Check [CHANGELOG.md](CHANGELOG.md) for the Phase D & E cutover, use [docs/INDEX.md](docs/INDEX.md) to reach its owner, read [architecture](docs/ARCHITECTURE.md) for cross-boundary work, and read [the system design](docs/AGENT-SYSTEM-DESIGN.md) when changing agent workflows.
2. Inspect current GitHub branch/issues/PRs (`gh api repos/<owner>/<repo>/issues/<number>` when `gh issue view` fails on deprecated `projectCards` in `gh <= 2.46.0`), local `HEAD`, `git worktree list`, and dirty/untracked work. Preserve other sessions' changes and create an isolated worktree before reading or editing code. Inspect installed services and private journals only when the requested runtime/financial claim needs them and access is authorized.
3. For scoped tickets defined by issue specs and repository docs, inspect the repository directly; reserve OptMem (`~/.optmem/memo recall <regex>` and `zoom <lo>-<hi>`) for cross-repo or ambiguous durable history, and verify every fact against its current owner. Memory and dated reports are navigation, not live truth.
4. Before adding an operation/module or starting data acquisition, replay or backtest, use `copytrade-pm capabilities list`, `copytrade-pm capabilities show <id>`, and `copytrade-pm capabilities validate`, then inspect the public owner and tests. [Agent operations](docs/AGENT-NATIVE-OPERATIONS.md) records current discovery/diagnostic limitations.
5. Run repository checks via `uv run --frozen --group dev` (never bare system `python3`) and review against [coding standards](CODING_STANDARDS.md). Documentation-only work checks links, contract consistency and diff; it does not claim runtime tests. For quick, explicitly non-release feedback use `bash scripts/ci_focused.sh tests/test_module.py`; it does not issue a receipt or replace full CI. Engineering merge/push requires `scripts/ci.sh all` / `.githooks/pre-push` on the exact commit. CI does not prove deployment or authority, and an edited worktree is not a merged or released revision.

## Independent authorities

| Boundary | Source of truth |
| --- | --- |
| Code and accepted engineering contracts | Git exact SHA, [CHANGELOG.md](CHANGELOG.md), and [architecture](docs/ARCHITECTURE.md) |
| Unified market/wallet facts | `copytrade_pm.facts` (`FactStore`, day-partitioned `Decimal(38,12)` Parquet + `facts.sqlite`); see [fact store](docs/FACTS-STORE.md) |
| Seats, leases, CUSUM latches, vetoes, unsigned proposals | `copytrade_pm.roster` (`RosterStore` / `roster.sqlite`); see [roster](docs/ROSTER.md) |
| Causal source positions and coverage | Original native source journal; never fill gaps with inferred flats |
| Financial virtual paper / risk | PM03/PM04 replay via `pm_checkpoint_decision` / `copytrade_kernel.step_checkpoint`; see [PM03 kernel decision](docs/CHECKPOINT-KERNEL-DECISION-PM03.md) |
| Signed paper-only authority | Offline-signed `portfolio_release_v2` + `CopyMandate` and new epoch |
| Protected native trading | Guardian + `copytrade-kernel` in `prop-production`; broker adapter in `trading-connector` |
| Cross-repository companion pins | `prop-production:src/prop_production/compatibility.json` — sole pin authority; never copy source SHAs as live pins |
| Deployment and dashboard | Independently bound Ops Control Center installed/runtime process evidence; source/build/Git SHA or HTTP 200 alone is insufficient |

**Phase-D CLI & Roster authority:** Use the unified `copytrade-pm` CLI (`facts`, `research`, `roster`, `paper`, `release`, `capabilities`). Roster identity comes from `RosterStore` (`roster.sqlite` append-only tables, `inventory_sha()`, `health()`, `verify()`), never the retired `wallet_registry.sqlite` (`wallet_registry*.py` modules were deleted in Phase D, and the legacy SQLite file is archived read-only). An unsigned `ReleaseProposal` or healthy observer does **not** establish signed financial admission or trading authorization.

## Source and timing boundaries

- **V4 T0+300 retired (2026-11-14):** Do not start V4 executors or use them as ANOS targets; keep historical records read-only. See [position-first ADR](docs/decisions/2026-11-08-position-first-t300.md).
- **Future Vike-first transport:** Transport receipts alone do not prove complete-book coverage or cutover readiness. See [Vike-first ADR](docs/decisions/2026-11-11-vike-first-wallet-source.md) and [migration status contract](docs/V4-VIKE-FIRST-MIGRATION-PROGRESS-20261111.md).
- **CWSA 5-minute checkpoints (sole source-policy target):** `pm_cwsa_source_observer` owns source observation. Repo edits never imply financial admission or trading authorization. See [checkpoint ADR](docs/decisions/2026-11-11-canonical-5m-checkpoint-grill.md) and [CWSA Chapter 2 runbook](docs/CWSA-CHAPTER2-20261112.md).
- **Sizing & kernel decision:** Default is `FIXED_K_NATIVE_QUANTITY`; `pm_checkpoint_decision` and `pm_mandate` delegate directly to `copytrade_kernel.step_checkpoint`. Never infer executable P&L from mids, leader fills, or service health. See [risk-budgeted k](docs/RISK-BUDGETED-K-SIZING-20261106.md), [qualification](docs/QUALIFICATION.md), [PM03](docs/PM-03-shadow-account.md), and [PM03 kernel decision](docs/CHECKPOINT-KERNEL-DECISION-PM03.md).
- **Fact store vs legacy wallet store:** New research and wallet-health capture (`copytrade-pm facts capture-health`) write to `FactStore` (`copytrade_pm.facts`, `Decimal(38,12)` Parquet + `facts.sqlite`, strict `as_of_ms` PIT scanning). The legacy `wallet_store` write path is **retired** (reads remain available strictly for historical archive migration; see [fact store](docs/FACTS-STORE.md) and [wallet store archive](docs/WALLET-STORE.md)).
- **Reservoir research (#332):** Reservoir shards record no capture clock (`first_known_at_ms = NULL`) and remain invisible to strict `as_of_ms` PIT scans unless `allow_unknown_known_at=True` is explicitly passed for retrospective research.

## Operations and release

- **Single Chapter 2 owner:** [CWSA Chapter 2 runbook](docs/CWSA-CHAPTER2-20261112.md) (premerge/predeploy/postdeploy gates, `copytrade-pm release chapter2`, 3-unit `cwsa-ops-<sha12>` immutable release contract, CI receipts, rollback, PASS/`BLOCKED_EVIDENCE`/FAIL reporting).
- **Ops Control Center (ANOS-12, read-only):** `ops.hzminhzz.space` (`ops/control-center/src/`, `scripts/dashboard_server.py`, `site-view` CLI owner projection). Public read access is not account permission; Grafana/Marimo are retired. Preserve untracked `/home/quant/dev/copytrade-pm/dashboard/` Site work and never treat a merged commit or PID alone as an installed runtime proof.
- **Pre-mutation docs & orchestration:** Check [RUNBOOK](docs/RUNBOOK.md), [governance](docs/GOVERNANCE-GATES.md), [merge-versus-deployment ADR](docs/decisions/2026-11-10-merge-vs-runtime-promotion.md), and [blocker recovery](docs/BLOCKER-RECOVERY.md) before roster/service/financial mutations (never touch Guardian/broker or existing journals for observer deploys). [Prefect](docs/TRACK-B-PREFECT-ORCHESTRATION-20261110.md) is Track B opt-in only.
- **MANDATORY contract EV tool:** Use `research.contract_selector` via `copytrade-pm research contracts`, resolving on genuine matched **net follower** evidence (missing tape = `BLOCKED`, synthetic EV = `SCENARIO_ONLY`, neither gives permission to trade). See [contract EV](docs/CONTRACT-PORTFOLIO-EV-TOOL-20261105.md).

## Engineering documentation

Update one canonical owner, [docs/INDEX.md](docs/INDEX.md) navigation, affected capability/tests, and a scoped ADR when a consequential contract decision changes. Keep current contracts, design targets and dated evidence distinct. Retain the smallest reproducible lesson; reuse verified immutable work and recheck mutable preconditions. Preserve historical reports and negative evidence. Confirm cross-repository consumer pins when changed. Keep ephemeral processes, balances, resource values, and P&L out of permanent instructions. Report **IMPLEMENTED / ENGINEERING_VERIFIED / MERGED / DEPLOYED / PROSPECTIVE_PAPER_ACTIVE / ECONOMICALLY_QUALIFIED / SCIENTIFICALLY_QUALIFIED / TRADING_AUTHORIZED** as separate states with exact supporting receipts.

## Agent skills

- **Issue tracker:** GitHub Issues in `hzminhzz/copytrade-pm` via the `gh` CLI. See [issue-tracker.md](docs/agents/issue-tracker.md).
- **Triage labels:** default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See [triage-labels.md](docs/agents/triage-labels.md).
- **Domain docs:** single-context glossary at [CONTEXT.md](CONTEXT.md) and ADRs in `docs/decisions/`. See [domain.md](docs/agents/domain.md).
