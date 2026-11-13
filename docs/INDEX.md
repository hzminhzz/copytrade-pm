# copytrade-pm documentation — start here

**Role:** CURRENT NAVIGATION. Route by the question below, then inspect the named authority at the relevant revision/as-of. This page does not cache live rosters, service state, release pins or P&L.

## Choose the task

| Question | Read next | Evidence owner |
| --- | --- | --- |
| How does the whole system work? | [Architecture](ARCHITECTURE.md); [domain glossary](../CONTEXT.md) when a term is unclear | Independent source, metadata, paper, Guardian and provider authorities |
| How should agent workflows evolve? | [Agent system design and staged plan](AGENT-SYSTEM-DESIGN.md) | Design target; implementation status is separate |
| Which operation already exists? | [Agent-native operations](AGENT-NATIVE-OPERATIONS.md) and the capability catalog | Exact installed/candidate interface and public behavioral tests |
| Which wallet, portfolio, version or exclusion? | [Mandatory registry-first workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md) | Native SQLite integrity, inventory identity, qualified version and known-at |
| Why is Chapter 2 paper blocked; how is it released? | [CWSA Chapter 2 runbook](CWSA-CHAPTER2-20261112.md) | Source-wave receipts, separately signed mandates, independent quotes and PM03 journals |
| What did the CWSA program implement? | [Implementation ledger](CANONICAL-5M-IMPLEMENTATION-313.md), [acceptance dossier](evidence/CWSA-313-DOSSIER-v1-20261112.md) | Exact engineering evidence; original prospective gates remain separate |
| Which source timing policy applies? | [V4 position-first ADR](decisions/2026-11-08-position-first-t300.md), [distinct CWSA ADR](decisions/2026-11-11-canonical-5m-checkpoint-grill.md) | Actual selected release/policy and original source journal |
| Is Vike a qualified source replacement? | [Transport target ADR](decisions/2026-11-11-vike-first-wallet-source.md), [migration evidence](V4-VIKE-FIRST-MIGRATION-PROGRESS-20261111.md) | Original continuous complete-position proof; transport alone is insufficient |
| How do I acquire or reuse research data? | [Data acquisition](DATA-ACQUISITION.md), [Vike recovery](VIKE-DATA-RECOVERY-20261106.md), [bounded work design](AGENT-SYSTEM-DESIGN.md#6-resource-aware-research-and-inspection) | Provider-tagged originals, immutable inputs and existing job/storage owners |
| How do sizing, finance and risk work? | [Fixed-k sizing](RISK-BUDGETED-K-SIZING-20261106.md), [PM03](PM-03-shadow-account.md), [PM04](PM-04-shadow-hardening.md), [Track C recalibration](TRACK-C-K-RECALIBRATION-20261110.md) | Independent source mark/follower quote; each consumer owns finance |
| What can be claimed or promoted? | [Qualification](QUALIFICATION.md), [governance](GOVERNANCE-GATES.md), [merge versus runtime](decisions/2026-11-10-merge-vs-runtime-promotion.md) | Exact action-specific evidence and authority |
| How do I execute or recover an operation? | [RUNBOOK](RUNBOOK.md), [blocker recovery](BLOCKER-RECOVERY.md), [recovery integration](RECOVERY-INTEGRATION.md), [PM04 contract](PM-04-shadow-hardening.md); target recovery model in [design §5](AGENT-SYSTEM-DESIGN.md#5-bounded-actions-and-recovery) | Existing owner (Guardian in prop-production for protected dispatches; PM04/source journals locally), bounded action and verified postcondition |
| How do I hand off or continue a task? | [Registry closeout](WALLET-REGISTRY-AGENT-WORKFLOW.md#mandatory-agent-closeout-and-optmem-discipline), [blocker recovery](BLOCKER-RECOVERY.md); target handoff spec in [design §7](AGENT-SYSTEM-DESIGN.md#7-make-knowledge-accretive) | Exact worktree/revision, changed paths, validated receipts and next unmet dependency |
| How do source facts reach protected finance? | [Production handoff](PRODUCTION-HANDOFF.md), [V4 export](V4-PROP-SOURCE-EXPORT-20261108.md) | prop-production release verification and Guardian; connector supplies native facts |
| What is actually running and displayed? | [Chapter 2](CWSA-CHAPTER2-20261112.md), [registry release](WALLET-REGISTRY-RELEASE-RUNBOOK.md) and the owning deployment runbook | Configured/installed/running identity and authenticated publisher lineage, separately |

Read [AGENTS](../AGENTS.md) before changes. Inspect relevant GitHub issues/PRs and preserve concurrent work. Code/docs tasks do not require blanket financial-journal reads; metadata, runtime and financial questions follow their respective evidence owners.

## Document roles and conflict resolution

- **Current contract:** defines an owner, meaning or supported procedure. Verify the actual implementation/version before execution.
- **Design target:** records intended behavior and remaining work; it is not proof an interface exists.
- **Implementation ledger:** records completed and blocked acceptance against exact evidence.
- **Dated evidence:** preserves what was observed at its stated cutoff; recheck for a current claim.

An ADR governs intent only within its stated scope. Exact code establishes implemented behavior, original evidence establishes observations, and independent release/process checks establish runtime facts. A conflict is a fact to resolve, not permission to pick the most convenient source. Historical “current” statements remain historical.

Software capability, installed release, source health, financial admission, economic/scientific qualification and trading authorization are separate dimensions. Missing evidence stays unknown; a source gap is not a flat account.

## Current specialist contracts

| Task branch | Canonical guide |
| --- | --- |
| SQLite writes, legacy writer lock and rollback | [Native SQLite controls](SQLITE-NATIVE-LEGACY-LOCK-20261105.md), [registry release](WALLET-REGISTRY-RELEASE-RUNBOOK.md) |
| Independent portfolio admission and financial paper | [Registry paper profiles](REGISTRY-PAPER-PORTFOLIOS-20261107.md), [paper boundary](WALLET-REGISTRY-PAPER-CONTRACT-20261104.md), [Chapter 2](CWSA-CHAPTER2-20261112.md) |
| Existing V4 campaign operation | [Canonical campaign runbook](V4-CANONICAL-FRESH-PAPER-20261111.md), [position-first deployment](V4-POSITION-FIRST-DEPLOY-20261108.md) |
| Source continuity and observer recovery | [Continuous observer](FORWARD-PAPER-CONTINUOUS-OBSERVER.md), [subscription recovery](V4-0911-WS-SUBSCRIPTION-RECOVERY-292.md) |
| Protected standby/watchdog staging | [Protected operations](FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md) |
| Track B diagnostics and research scheduling | [Wallet health](WALLET-HEALTH-TRACK-B-20261110.md), [SHADOW rollout](TRACK-B-SHADOW-ROLLOUT-20261111.md), [optional Prefect](TRACK-B-PREFECT-ORCHESTRATION-20261110.md) |
| Track C immutable k proposals | [Recalibration contract](TRACK-C-K-RECALIBRATION-20261110.md) |
| Historical screening and shortlist handoff | [Fast Polars screening](V4-FAST-POLARS-SCREENING-20261110.md), [screening ADR](decisions/2026-11-09-v4-aligned-fast-wallet-screening.md) |
| Contract-level follower EV and scenario research | [Native contract EV](CONTRACT-PORTFOLIO-EV-TOOL-20261105.md), [actuarial scenarios](CONTRACT-ACTUARY-RESEARCH-20261105.md) |
| Independent agent-behavior measurement | [Host trace evaluation](AGENT-TRACE-EVAL-20261105.md); fixtures and CLI smoke are not observed model behavior |
| Typed domain-contract maintenance | [Pydantic acceptance](PYDANTIC-NATIVE-ACCEPTANCE-RESULTS-20261109.md), [cross-repository compatibility](PYDANTIC-CROSS-REPOSITORY-COMPATIBILITY-20261109.md), [engineering record](PYDANTIC-NATIVE-ENGINEERING-20261109.md) |

The authenticated Site is the intended operator interface. Inspect ownership of the frontend source before editing concurrent/untracked work. The [Ops Control Center](OPS-CONTROL-CENTER-20261111.md) is an older read-only sidecar, not proof of deployed Site parity. Grafana/Marimo documents below preserve historical work. The Chapter 2 runbook owns its actual deployment and dashboard acceptance.

For companion repositories, resolve `prop-production:src/prop_production/compatibility.json`, its `README.md` and owning runbooks, and `trading-connector:docs/architecture.md`. Repository locators are not assumed filesystem sibling paths. The application manifest is the only cross-repository pin authority.

Concurrent unmerged work in the primary checkout (`/home/quant/dev/copytrade-pm`: `src/copytrade_pm/wallet_store/`, `docs/WALLET-STORE.md`, `docs/RESERVOIR-*.md`, `docs/DATA-SOURCES-RESERVOIR-VIKE-20261112.md`, `docs/FOLLOWER-5M-BACKTEST-20261112.md`, `dashboard/`, `docs/agents/`) and open [PR #332](https://github.com/hzminhzz/copytrade-pm/pull/332) remain unmerged candidate artifacts, not merged `main` or installed authority; preserve them in place.

## Dated evidence and preserved design records

Use these when auditing lineage, reproducing the named study, or checking an original acceptance criterion. Do not execute an old rollout merely because its document contains commands.

| Evidence family | Preserved references |
| --- | --- |
| Registry status and negative evidence | [Wallet status](WALLET-STATUS.md), [registry checkpoint](WALLET-REGISTRY-STATUS-20261104.md), [acceptance](WALLET-REGISTRY-ACCEPTANCE-20261104.md), [signed negative evidence](WALLET-REGISTRY-SIGNED-NEGATIVE-EVIDENCE-20261104.md), [review hardening](WALLET-REGISTRY-REVIEW-HARDENING-20261104.md) |
| Registry selection lineage | [P1 decision](decisions/2026-11-02-gemini-selected-three-pod.md), [alternatives](decisions/2026-11-03-gemini-alternative-portfolios.md), [Phase 3](decisions/2026-11-03-gemini-phase3-adoption-180d.md), [V2 freeze](decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.md), [V2 JSON roster](decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.json) |
| Pydantic original plan and tests | [Roadmap](PYDANTIC-NATIVE-MIGRATION-ROADMAP-20261109.md), [design closure](PYDANTIC-NATIVE-DESIGN-CLOSURE-20261109.md), [individual matrix](PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md), [combined-fault matrix](PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md) |
| Rollouts and source canaries | [Sixteen-paper release](V4-SIXTEEN-PAPER-20261109.md), [typed rollout](PYDNATIVE-V4-SIXTEEN-SHADOW-20261109.md), [authentic P1 trace](PYDNATIVE-V4-REAL-T300-TRACE-20261109.md), [Vike candidate](FORWARD-PAPER-VIKE-MIGRATION-20261108.md), [public-trade scope](FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.md) |
| Offline Polars engineering and historical oracle | [Milestone acceptance](OFFLINE-MILESTONE2-ENGINEERING-ACCEPTANCE-20261104.md), [verification matrix](OFFLINE-MILESTONE2-ENGINEERING-VERIFICATION-20261104.md), [sealed job](OFFLINE-HL94-ORACLE-JOB-20261104.json), [real-oracle study](OFFLINE-PIT-REAL-ORACLE-20261104.md), [processing](OFFLINE-PIT-PROCESSING-20261104.md), [baseline](OFFLINE-PIT-BASELINE-20261104.md) |
| Trader Intelligence | [Engineering acceptance](TRADER-INTELLIGENCE-ENGINEERING-ACCEPTANCE-20261103.md), [continuation](TRADER-INTELLIGENCE-CONTINUATION-20261104.md), [checkpoint](TRADER-INTELLIGENCE-CHECKPOINT-20261102.md), [prospective study](TRADER-INTELLIGENCE-PROSPECTIVE-STUDY-20261103.md), [negative audit](TRADER-INTELLIGENCE-P1-EXPLORATORY-AUDIT-20261103.md), [native snapshot](TRADER-INTELLIGENCE-P1-NATIVE-SOURCE-20261103.md) |
| Account, allocator and legacy studies | [PM01 ledger](PM-01-prospective-ledger.md), [PM02 gates](PM-02-EVIDENCE-GATES.md), [PM04 acceptance](PM-04-acceptance.md), [legacy NAV sizing](EQUITY-WEIGHT-SIZING.md), [Q3 sparse equity](Q3-SPARSE-EQUITY-PORTFOLIO-EXECUTION-20261102.md), [Q3 trio](Q3-TRIO-W042-W044-W028-20261102.md), [gross proxy](HISTORICAL-THREE-WALLET-COMPARISON.md) |
| Earlier extraction and integration | [PM01 fill-only](PM-01-fill-only.md), [market scope](PM-01-propr-90pct-scope.md), [direct study](PM-01-2026-10-31-direct-execution.md), [Rust replay](PM-01-replay.md), [PM02 research](PM-02-research.md), [old goal](PM-02-goal.md), [migration](PM-MIGRATION-CHECKPOINT.md), [recovery integration](RECOVERY-INTEGRATION.md), [ML4T proposal](ML4T-PROPR-INTEGRATION.md), [provenance](PROVENANCE.md), [Combo2](COMBO2-PAPER.md) |
| UI history | [Retirement](DASHBOARD-RETIREMENT-20261108.md), [phase 1](DASHBOARD-PHASE1.md), [phase 2](DASHBOARD-PHASE2.md), [phase 3](DASHBOARD-PHASE3.md), [final audit](DASHBOARD-FINAL-AUDIT-20261107.md) |
| Repository and documentation audits | [November 7 reconciliation](RECONCILIATION-20261107.md), [follow-up](RECONCILIATION-FOLLOWUP-20261107.md), [selected-observer audit](SELECTED-OBSERVER-P0-EXECUTION-20261107.md), [documentation audit](DOCUMENTATION-AUDIT-20261111.md), [old operator guide](OPERATOR-GUIDE-20261104.md) |
| Retrospective k | [July training / later OOS study](research/2026-11-10-vike-retrospective-k-oos.md); retrospective k is not a historical signed release |

## Maintenance and completion

Update the canonical owner and the relevant route in this index together. Put changed domain meaning in CONTEXT and a scoped ADR when a consequential decision needs a durable rationale. Put test/deployment outcomes in their evidence record; keep temporary counts, PIDs and blockers out of the entry documents.

Research selection and documentation updates make no running roster/service changes. Worker admission and deployment require their separate verified contracts. The two-link portfolio navigation target in [Agent system design](AGENT-SYSTEM-DESIGN.md#9-end-to-end-acceptance-tasks) is an unmeasured structural target, not an observed live-agent metric.

The task is complete when its requested outcome is independently evidenced or its exact unresolved dependency is reported, with unaffected authorized work completed. Record implementation, verification, publication, deployment, prospective effects, qualification and authorization separately, and distinguish merged/released state from an edited worktree.

The [pre-revision index](https://github.com/hzminhzz/copytrade-pm/blob/1c4ac38e76dc7ed31e3421273269750b2f03e086/docs/INDEX.md) preserves the earlier navigation and dated snapshots.
