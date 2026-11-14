# copytrade-pm — agent operating contract

This repository owns **research, original source observation, and virtual paper**, not broker authority. ChatGPT is the hands-on engineer. Do not delegate coding without an explicit user request. No broker credentials, live orders, protected Guardian changes, or trading authorization.

## First inspection

1. State the requested outcome, exact target and authorized read/write scope. Use [docs/INDEX.md](docs/INDEX.md) to reach its owner; read [architecture](docs/ARCHITECTURE.md) for cross-boundary work and [the system design](docs/AGENT-SYSTEM-DESIGN.md) when changing agent workflows.
2. Inspect current GitHub branch/issues/PRs (`gh api repos/<owner>/<repo>/issues/<number>` when `gh issue view` fails on deprecated `projectCards` in `gh <= 2.46.0`), local `HEAD`, `git worktree list`, and dirty/untracked work. Preserve other sessions' changes and create an isolated worktree before reading or editing code. Inspect installed services and private journals only when the requested runtime/financial claim needs them and access is authorized.
3. For scoped tickets defined by issue specs and repository docs, inspect the repository directly; reserve OptMem (`~/.optmem/memo recall <regex>` and `zoom <lo>-<hi>`) for cross-repo or ambiguous durable history, and verify every fact against its current owner. Memory and dated reports are navigation, not live truth.
4. Before adding an operation/module or starting data acquisition, replay or backtest, use `copytrade-pm capabilities list`, `copytrade-pm capabilities show <id>`, and `copytrade-pm capabilities validate`, then inspect the public owner and tests. [Agent operations](docs/AGENT-NATIVE-OPERATIONS.md) records current discovery/diagnostic limitations.
5. Run repository checks via `uv run --frozen --group dev` (never bare system `python3`) and review against [coding standards](CODING_STANDARDS.md). Documentation-only work checks links, contract consistency and diff; it does not claim runtime tests. Engineering merge/push requires `scripts/ci.sh all` / `.githooks/pre-push` on the exact commit. CI does not prove deployment or authority, and an edited worktree is not a merged or released revision.

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

- **V4 first-known T0+300 is RETIRED as an operational policy (owner decision 2026-11-14).** Do not start its source or paper executors or use it as the ANOS real-world E2E acceptance target. Preserve original historical source/finance evidence and read-only replay. See the historical [position-first ADR](docs/decisions/2026-11-08-position-first-t300.md).
- Future Vike-first transport is preferred for scale; Vike observation/fill transport alone is **not** continuous official complete-book proof or permission to cut over. See [Vike-first ADR](docs/decisions/2026-11-11-vike-first-wallet-source.md) and [migration status contract](docs/V4-VIKE-FIRST-MIGRATION-PROGRESS-20261111.md).
- **CWSA 5-minute checkpoints are the sole current source-policy target.** Official REST original-backed checkpoints, independent wallet waves, explicit source/mandate transitions, and immutable freeze remain mandatory. Retirement of V4 does **not** prove CWSA financial admission or authorize trading. The CWSA-owned source entrypoint is `pm_cwsa_source_observer`. Existing pinned processes using `pm_v4_selected_positions --source-mode CHECKPOINT_REST_V3` require a separately verified runtime cutover; never assume a repository rename changed their loaded code. See [checkpoint ADR](docs/decisions/2026-11-11-canonical-5m-checkpoint-grill.md) and [CWSA Chapter 2 runbook](docs/CWSA-CHAPTER2-20261112.md).
- Default sizing is FIXED_K_NATIVE_QUANTITY; historical NAV-relative assumptions remain historical. Never infer executable P&L from market mids, historical leader fills, or a healthy service. See [risk-budgeted k](docs/RISK-BUDGETED-K-SIZING-20261106.md), [qualification](docs/QUALIFICATION.md), and [PM03](docs/PM-03-shadow-account.md).

## Operations and release

- **Single Chapter 2 owner:** [CWSA Chapter 2 runbook](docs/CWSA-CHAPTER2-20261112.md). It owns premerge/predeploy/postdeploy acceptance, unsigned research-to-paper release discipline, CI receipts, nonfinancial observation fallback, and rollback. Report PASS, BLOCKED_EVIDENCE, or FAIL without promoting an empty financial journal.
- **ANOS-12 operator UI (approved 2026-11-13):** use the existing public, read-only Ops Control Center at `ops.hzminhzz.space`, with source in `ops/control-center/src/` and `scripts/dashboard_server.py`. Its Chapter 2 evidence view delegates to the CLI `site-view` owner projection. It is not authenticated by default; public read access is not account permission. Preserve untracked `/home/quant/dev/copytrade-pm/dashboard/` Site work and all uncommitted changes in the pinned running Ops release. A merged Git SHA, local build or running PID alone does not prove a newly installed Ops revision. Grafana/Marimo are historical/retired operator interfaces; no deployment is authorized by ANOS-12.
- **Concurrent unmerged candidate work:** Primary-checkout untracked paths (`wallet_store`, Reservoir docs, Site `dashboard/`, `docs/agents/`) and open [PR #332](https://github.com/hzminhzz/copytrade-pm/pull/332) are unmerged candidate artifacts, not merged `main` or installed authority; see [INDEX](docs/INDEX.md#current-specialist-contracts) for the inventory and preserve them without resetting or overwriting other sessions' work.
- Review [RUNBOOK](docs/RUNBOOK.md), [governance](docs/GOVERNANCE-GATES.md), [merge-versus-deployment ADR](docs/decisions/2026-11-10-merge-vs-runtime-promotion.md), and [blocker recovery](docs/BLOCKER-RECOVERY.md) before a registry, service or financial mutation. Never change protected Guardian/broker or existing journals for an observer deployment.
- Prefect is opt-in Track B research orchestration only; never a hot source, financial, or order authority. See [Prefect](docs/TRACK-B-PREFECT-ORCHESTRATION-20261110.md).
- **MANDATORY contract EV tool:** use native `research.contract_selector` with `copytrade-pm contracts rules` and `copytrade-pm contracts compare --portfolio NAMESPACE/ID --tape PRIVATE_TAPE`. Resolve the portfolio from SQLite and require genuine matched **net follower** evidence. Missing tape means BLOCKED; synthetic EV means SCENARIO_ONLY; neither gives permission to trade. See [contract EV](docs/CONTRACT-PORTFOLIO-EV-TOOL-20261105.md).

## Engineering documentation

Update one canonical owner, docs/INDEX.md navigation, affected capability/tests, and a scoped ADR when a consequential contract decision changes. Keep current contracts, design targets and dated evidence distinct. Retain the smallest reproducible lesson; reuse verified immutable work and recheck mutable preconditions. Preserve historical reports and negative evidence. Confirm cross-repository consumer pins when changed. Keep ephemeral processes, balances, resource values, and P&L out of permanent instructions. Report **IMPLEMENTED / ENGINEERING_VERIFIED / MERGED / DEPLOYED / PROSPECTIVE_PAPER_ACTIVE / ECONOMICALLY_QUALIFIED / SCIENTIFICALLY_QUALIFIED / TRADING_AUTHORIZED** as separate states with exact supporting receipts.
