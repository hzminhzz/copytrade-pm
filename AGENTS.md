# copytrade-pm — agent operating contract

This repository owns **research, original source observation, and virtual paper**, not broker authority. ChatGPT is the hands-on engineer. Do not delegate coding without an explicit user request. No broker credentials, live orders, protected Guardian changes, or trading authorization.

## First inspection

1. State the requested outcome, exact target and authorized read/write scope. Use [docs/INDEX.md](docs/INDEX.md) to reach its owner; read [architecture](docs/ARCHITECTURE.md) for cross-boundary work and [the system design](docs/AGENT-SYSTEM-DESIGN.md) when changing agent workflows.
2. Inspect current GitHub branch/issues/PRs (`gh api repos/<owner>/<repo>/issues/<number>` when `gh issue view` fails on deprecated `projectCards` in `gh <= 2.46.0`), local `HEAD`, `git worktree list`, and dirty/untracked work. Preserve other sessions' changes and create an isolated worktree before reading or editing code. Inspect installed services and private journals only when the requested runtime/financial claim needs them and access is authorized.
3. For scoped tickets defined by issue specs and repository docs, inspect the repository directly; reserve OptMem (`~/.optmem/memo recall <regex>` and `zoom <lo>-<hi>`) for cross-repo or ambiguous durable history, and verify every fact against its current owner. Memory and dated reports are navigation, not live truth.
4. Before adding an operation/module or starting data acquisition, replay or backtest, use `copytrade-pm capabilities list`, `copytrade-pm capabilities show <id>`, and `copytrade-pm capabilities validate`, then inspect the public owner and tests. [Agent operations](docs/AGENT-NATIVE-OPERATIONS.md) records current discovery/diagnostic limitations.
5. Run repository checks via `uv run --frozen --group dev` (never bare system `python3`) and review against [coding standards](CODING_STANDARDS.md). Documentation-only work checks links, contract consistency and diff; it does not claim runtime tests. For quick, explicitly non-release feedback use `bash scripts/ci_focused.sh tests/test_module.py`; it does not issue a receipt or replace full CI. Engineering merge/push requires `scripts/ci.sh all` / `.githooks/pre-push` on the exact commit. CI does not prove deployment or authority, and an edited worktree is not a merged or released revision.

## Independent authorities

| Boundary | Source of truth |
| --- | --- |
| Code and accepted engineering contracts | Git exact SHA and [architecture](docs/ARCHITECTURE.md) |
| Wallets, exclusions, portfolio memberships/versions | Private SQLite; [registry-first workflow](docs/WALLET-REGISTRY-AGENT-WORKFLOW.md) |
| Causal source positions and coverage | Original native source journal; never fill gaps with inferred flats |
| Financial virtual paper / risk | PM03/PM04 replay of isolated paper journals |
| Frozen k research | Track C PIT/OOS originals; research is not permission |
| Signed paper-only authority | Independently verified Copy Mandates and new epoch |
| Protected native trading | Guardian in prop-production; broker adapter in trading-connector |
| Cross-repository companion pins | `prop-production:src/prop_production/compatibility.json` — sole pin authority; never copy source SHAs as live pins |
| Deployment and dashboard | Independently bound Ops Control Center installed/runtime process evidence; source/build/Git SHA or HTTP 200 alone is insufficient |

**MANDATORY REGISTRY-FIRST:** Wallet/portfolio identity comes from native SQLite integrity, `inventory_sha256` (with recorded source generation lineage), qualified namespace/version and known-at under the [registry workflow](docs/WALLET-REGISTRY-AGENT-WORKFLOW.md). Use scoped native readers; metadata-only work does not require financial journals or aggregate health. Keep database integrity separate from blocked selection proof; historical import SHA is lineage, not the current roster. [WALLET-STATUS.md](docs/WALLET-STATUS.md) is dated evidence. Verify independent release/runtime/finance only for the corresponding claim. An unsigned seal or healthy observer does **not** establish signed financial admission.

## Source and timing boundaries

- **V4 T0+300 retired (2026-11-14):** Do not start V4 executors or use them as ANOS targets; keep historical records read-only. See [position-first ADR](docs/decisions/2026-11-08-position-first-t300.md).
- **Future Vike-first transport:** Transport receipts alone do not prove complete-book coverage or cutover readiness. See [Vike-first ADR](docs/decisions/2026-11-11-vike-first-wallet-source.md) and [migration status contract](docs/V4-VIKE-FIRST-MIGRATION-PROGRESS-20261111.md).
- **CWSA 5-minute checkpoints (sole source-policy target):** `pm_cwsa_source_observer` owns source observation (`pm_v4_selected_positions` pinned runtimes require verified cutover). Repo edits never imply financial admission or trading authorization. See [checkpoint ADR](docs/decisions/2026-11-11-canonical-5m-checkpoint-grill.md) and [CWSA Chapter 2 runbook](docs/CWSA-CHAPTER2-20261112.md).
- **Sizing & qualification:** Default is `FIXED_K_NATIVE_QUANTITY`; never infer executable P&L from mids, leader fills, or service health. See [risk-budgeted k](docs/RISK-BUDGETED-K-SIZING-20261106.md), [qualification](docs/QUALIFICATION.md), and [PM03](docs/PM-03-shadow-account.md).
- **Canonical wallet store:** Historical fills/snapshots live in `data/private/wallet_store/` via `copytrade_pm.wallet_store` (`scan`, `coverage`, `verify`, `ingest`; verify `partitions` before assuming coverage). See [wallet store contract](docs/WALLET-STORE.md).
- **Reservoir research (#332):** Verify 269-wallet completion via the offline catalog verifier (not systemd presence). See [two-DEX DuckDB plan](docs/RESERVOIR-WALLET-DUCKDB-PLAN-20261112.md) and [frozen cohort/runbook](docs/RESERVOIR-MONITORED-PLUS-SIX-269-20261112.md).

## Operations and release

- **Single Chapter 2 owner:** [CWSA Chapter 2 runbook](docs/CWSA-CHAPTER2-20261112.md) (premerge/predeploy/postdeploy gates, 3-unit `cwsa-ops-<sha12>` immutable release contract, CI receipts, rollback, PASS/`BLOCKED_EVIDENCE`/FAIL reporting).
- **Ops Control Center (ANOS-12, read-only):** `ops.hzminhzz.space` (`ops/control-center/src/`, `scripts/dashboard_server.py`, `site-view` CLI owner projection). Public read access is not account permission; Grafana/Marimo are retired. Preserve untracked `/home/quant/dev/copytrade-pm/dashboard/` Site work and never treat a merged commit or PID alone as an installed runtime proof.
- **Pre-mutation docs & orchestration:** Check [the 5-minute follower backtest](docs/FOLLOWER-5M-BACKTEST-20261112.md), [RUNBOOK](docs/RUNBOOK.md), [governance](docs/GOVERNANCE-GATES.md), [merge-versus-deployment ADR](docs/decisions/2026-11-10-merge-vs-runtime-promotion.md), and [blocker recovery](docs/BLOCKER-RECOVERY.md) before registry/service/financial mutations (never touch Guardian/broker or existing journals for observer deploys). [Prefect](docs/TRACK-B-PREFECT-ORCHESTRATION-20261110.md) is Track B opt-in only.
- **MANDATORY contract EV tool:** Use `research.contract_selector` via `copytrade-pm contracts rules` and `copytrade-pm contracts compare --portfolio NAMESPACE/ID --tape PRIVATE_TAPE`, resolving from SQLite on genuine matched **net follower** evidence (missing tape = `BLOCKED`, synthetic EV = `SCENARIO_ONLY`, neither gives permission to trade). See [contract EV](docs/CONTRACT-PORTFOLIO-EV-TOOL-20261105.md).

## Engineering documentation

Update one canonical owner, docs/INDEX.md navigation, affected capability/tests, and a scoped ADR when a consequential contract decision changes. Keep current contracts, design targets and dated evidence distinct. Retain the smallest reproducible lesson; reuse verified immutable work and recheck mutable preconditions. Preserve historical reports and negative evidence. Confirm cross-repository consumer pins when changed. Keep ephemeral processes, balances, resource values, and P&L out of permanent instructions. Report **IMPLEMENTED / ENGINEERING_VERIFIED / MERGED / DEPLOYED / PROSPECTIVE_PAPER_ACTIVE / ECONOMICALLY_QUALIFIED / SCIENTIFICALLY_QUALIFIED / TRADING_AUTHORIZED** as separate states with exact supporting receipts.

## Agent skills

- **Issue tracker:** GitHub Issues in `hzminhzz/copytrade-pm` via the `gh` CLI. See [issue-tracker.md](docs/agents/issue-tracker.md).
- **Triage labels:** default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See [triage-labels.md](docs/agents/triage-labels.md).
- **Domain docs:** single-context glossary at [CONTEXT.md](CONTEXT.md) and ADRs in `docs/decisions/`. See [domain.md](docs/agents/domain.md).
