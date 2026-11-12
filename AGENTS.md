# copytrade-pm — agent operating contract

This repository owns **research, original source observation, and virtual paper**, not broker authority. ChatGPT is the hands-on engineer. Do not delegate coding without an explicit user request. No broker credentials, live orders, protected Guardian changes, or trading authorization.

## First inspection

1. Read [docs/INDEX.md](docs/INDEX.md), the owning architecture decision, and the canonical runbook for the task.
2. Inspect current origin/main, actual GitHub issues/PRs, branch, worktrees, dirty and untracked files, installed service PIDs, release SHAs, and real SQLite journals. Never reset, clean, overwrite, or commandeer another session's work. Use an isolated worktree.
3. Run OptMem wake and recall for context; repository, original receipts, SQLite, and live OS facts override memory. Do not use dated status notes as current truth.
4. Discover existing CLI capabilities before adding a module: `copytrade-pm capabilities list`, `copytrade-pm capabilities show`, and `copytrade-pm capabilities validate`. See [agent-native operations](docs/AGENT-NATIVE-OPERATIONS.md).
5. Run the existing `scripts/ci.sh all` / `.githooks/pre-push` gate and verify its exact-commit receipt. Passing CI does not prove an installed release, financial admission, or trading authorization.

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
| Deployment and dashboard | Actual service PID, executable SHA, authenticated Site revision and publisher proof |

**MANDATORY REGISTRY-FIRST:** For any portfolio/paper question, verify the registry with `copytrade-wallet-registry doctor`, `copytrade-wallet-registry status`, `copytrade-wallet-registry native status`, and `scripts/registry_release.py verify`. Resolve the SQLite **source generation** (manifest SHA/as-of), namespace/version/as-of, and authoritative source receipts. [WALLET-STATUS.md](docs/WALLET-STATUS.md) is dated historical evidence, not current truth. An unsigned seal, research portfolio, or healthy observer does **not** establish signed financial admission.

## Source and timing boundaries

- Current approved V4 entry timing is genuine first locally known complete-book transition T0 + 300 seconds for one new-risk attempt; verified reductions and protective exits are immediate. See [position-first ADR](docs/decisions/2026-11-08-position-first-t300.md).
- Future Vike-first transport is preferred for scale; Vike observation/fill transport alone is **not** continuous official complete-book proof or permission to cut over. See [Vike-first ADR](docs/decisions/2026-11-11-vike-first-wallet-source.md) and [migration status contract](docs/V4-VIKE-FIRST-MIGRATION-PROGRESS-20261111.md).
- The distinct canonical five-minute CWSA policy uses official REST original-backed checkpoints, independent wallet waves, explicit source/mandate transitions, immutable freeze, and no implied state machine. It does not silently replace V4. See [checkpoint ADR](docs/decisions/2026-11-11-canonical-5m-checkpoint-grill.md) and [CWSA Chapter 2 runbook](docs/CWSA-CHAPTER2-20261112.md).
- Default sizing is FIXED_K_NATIVE_QUANTITY; historical NAV-relative assumptions remain historical. Never infer executable P&L from market mids, historical leader fills, or a healthy service. See [risk-budgeted k](docs/RISK-BUDGETED-K-SIZING-20261106.md), [qualification](docs/QUALIFICATION.md), and [PM03](docs/PM-03-shadow-account.md).

**Reservoir retrospective research:** for wallet-scoped S3 queries, use the [two-DEX DuckDB plan](docs/RESERVOIR-WALLET-DUCKDB-PLAN-20261112.md) and [269-wallet monitored-plus-six cohort runbook](docs/RESERVOIR-MONITORED-PLUS-SIX-269-20261112.md). The new 269-wallet data acquisition is blocked on AWS login; old 14-wallet evidence is a separate narrower cohort. Historical exchange time is not local first-known or paper admission.

## Operations and release

- **Single Chapter 2 owner:** [CWSA Chapter 2 runbook](docs/CWSA-CHAPTER2-20261112.md). It owns premerge/predeploy/postdeploy acceptance, unsigned research-to-paper release discipline, CI receipts, nonfinancial observation fallback, and rollback. Report PASS, BLOCKED_EVIDENCE, or FAIL without promoting an empty financial journal.
- **Current intended operator UI:** the user-facing Site source in /home/quant/dev/copytrade-pm/dashboard/. It is untracked in the main checkout and belongs to another session until ownership is verified. Grafana and Marimo are historical/retired operator interfaces. The older ops-control-center service is a read-only sidecar; a running sidecar is not proof that the Site projection is deployed.
- Review [RUNBOOK](docs/RUNBOOK.md), [governance](docs/GOVERNANCE-GATES.md), [merge-versus-deployment ADR](docs/decisions/2026-11-10-merge-vs-runtime-promotion.md), and [blocker recovery](docs/BLOCKER-RECOVERY.md) before any mutation. Never change protected Guardian/broker or existing journals for an observer deployment.
- Prefect is opt-in Track B research orchestration only; never a hot source, financial, or order authority. See [Prefect](docs/TRACK-B-PREFECT-ORCHESTRATION-20261110.md).
- **MANDATORY contract EV tool:** use native `research.contract_selector` with `copytrade-pm contracts rules` and `copytrade-pm contracts compare --portfolio NAMESPACE/ID --tape PRIVATE_TAPE`. Resolve the portfolio from SQLite and require genuine matched **net follower** evidence. Missing tape means BLOCKED; synthetic EV means SCENARIO_ONLY; neither gives permission to trade. See [contract EV](docs/CONTRACT-PORTFOLIO-EV-TOOL-20261105.md).

## Engineering documentation

Update one canonical owner, docs/INDEX.md navigation and the relevant ADR when contracts change. Preserve historical reports and negative evidence. Confirm cross-repository consumer pins when changed. Keep ephemeral processes, balances, resource values, and P&L out of permanent instructions. Report **IMPLEMENTED / TESTED / MERGED / DEPLOYED / PROSPECTIVE_PAPER_ACTIVE / ECONOMICALLY_QUALIFIED / SCIENTIFICALLY_QUALIFIED / TRADING_AUTHORIZED** as separate states with exact supporting receipts.
