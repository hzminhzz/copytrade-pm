# copytrade-pm documentation — start here

## Navigate by responsibility (authoritative)

| When working on... | Read first | Source of truth |
| --- | --- | --- |
| First agent session or new work | [AGENTS.md](../AGENTS.md) → [Architecture](ARCHITECTURE.md) | Live Git, OS and private evidence beat written status |
| Wallet/portfolio identity and exclusions | [Registry-first workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md) | Owner-private SQLite, sealed selections |
| New wallet activity ingestion | [Vike-first target ADR](decisions/2026-11-11-vike-first-wallet-source.md) | Approved transport **target**, not live source authority |
| Current complete-position source and T+300 | [Official position-first ADR](decisions/2026-11-08-position-first-t300.md) | Original official complete-book receipts until a qualified replacement is activated |
| Current canonical virtual-paper research | [2026-11-11 campaign runbook](V4-CANONICAL-FRESH-PAPER-20261111.md) | Actual pinned service + immutable private journals, not this document's snapshot |
| Sizing and account risk | [Fixed-k sizing](RISK-BUDGETED-K-SIZING-20261106.md), [PM-03](PM-03-shadow-account.md), [PM-04](PM-04-shadow-hardening.md) | PM03/04 simulated finance; Guardian owns protected finance |
| Data acquisition and recovery | [Data acquisition](DATA-ACQUISITION.md), [Vike recovery](VIKE-DATA-RECOVERY-20261106.md) | Provider-tagged raw evidence, actual local receipt time |
| Safe operator workflow and commands | [RUNBOOK](RUNBOOK.md), [Blocker recovery](BLOCKER-RECOVERY.md) | Verify version and dry-run before runbook mutation |
| Economics, readiness, promotion | [Qualification](QUALIFICATION.md), [Governance](GOVERNANCE-GATES.md), [Merge vs activation](decisions/2026-11-10-merge-vs-runtime-promotion.md) | Independent actual follower outcomes and action-specific signed permissions |

**Authority order:** current code, original evidence, signed registry records and verified installed state define *what is*. An approved ADR defines *what should be*. A newer ADR supersedes only the specific boundary it says it supersedes. Reports, incident snapshots, PR prose and OptMem do not promote proposed designs into live facts. The [Vike-first transport ADR](decisions/2026-11-11-vike-first-wallet-source.md) supersedes scaling direct Hyperliquid user WS as a preferred future transport; the [2026-11-08 ADR](decisions/2026-11-08-position-first-t300.md) still governs currently implemented complete-position signals and T+300.

**Status vocabulary:** APPROVED TARGET → IMPLEMENTED → TESTED → DEPLOYED → SCIENTIFICALLY QUALIFIED → TRADING AUTHORIZED. Each step needs separate evidence. Missing source continuity is NO_TRADE, not a zero position. For current 14-account coverage, inspect the live stream and saved GAP epochs instead of reusing a dated 7/14 claim.

## Current release and historical checkpoints (dated, not instructions)

[2026-11-11 repository-wide documentation disposition and cold-start audit](DOCUMENTATION-AUDIT-20261111.md) records contradictions, historical preservation and remaining implementation boundaries.

**Public observer readiness:** unrelated unsigned research selections do not block independently sealed selected-portfolio preflight. Registry research-selection integrity remains a separate blocked diagnostic; explicit unverified portfolio requests still fail closed. See [continuous observer](FORWARD-PAPER-CONTINUOUS-OBSERVER.md).


The [7 November reconciliation record](RECONCILIATION-20261107.md) explains PR and preserved-work dispositions. The [follow-up preservation and SHADOW verification](RECONCILIATION-FOLLOWUP-20261107.md) corrects the untracked-stash-parent audit and records the pending privileged deployment and degraded legacy observer. The [selected-observer P0 execution audit](SELECTED-OBSERVER-P0-EXECUTION-20261107.md) records the actual shared-IP capacity and selected-provenance blockers; it does not authorize deployment. Refresh live state before using dated evidence.

**Read-only Track B wallet health (#256):** [versioned daily as-of registry assessment, private immutable report, and redacted Grafana projection](WALLET-HEALTH-TRACK-B-20261110.md). The health research layer has no wallet or financial command authority; current field diagnosis depends on authentic, independently supplied provider evidence.

**Track C risk-budgeted k research (#256):** [strict trial-aware proposals, immutable read-only research reports, nonactivating SHADOW release preflight and rollback](TRACK-C-K-RECALIBRATION-20261110.md). Proposal-level evidence is not verified follower alpha, signed release or activation.

**0911 official source subscription recovery (#292):**
[7-at-a-time, 14-parent official WS SHADOW rotation, explicit GAPs and reversible source/paper deployment](V4-0911-WS-SUBSCRIPTION-RECOVERY-292.md). This does not establish simultaneous 14-account source continuity or authorize trading.

**2026-11-11 canonical 16-portfolio SHADOW campaign:** [Versioned $10k / 5% daily / 8% trailing paper rules, original-journal archive and reversible pinned paper-only release](V4-CANONICAL-FRESH-PAPER-20261111.md). Old paper data is not rewritten, and only 7 of 14 source parents are presently continuously observed.

**V4-aligned fast wallet screening (#255):** [opt-in v2 Polars retrospective screen, frozen-k inputs, engineering evidence and explicit PM03 shortlist handoff](V4-FAST-POLARS-SCREENING-20261110.md). This is not a prospective first-known wallet qualification or trading signal.

**Vike post-window research-k follow-up (2026-11-10):** [94-wallet July-training / August–November OOS v3 experiment, research-only rankings, SQLite exclusions, and immutable receipt](research/2026-11-10-vike-retrospective-k-oos.md). Retrospectively calculated k is not a historical signed release or trading qualification.

**Opt-in Prefect 3 Track B research orchestration (owner decision 2026-11-10):**
[Private crash-replay-safe batch jobs](TRACK-B-PREFECT-ORCHESTRATION-20261110.md),
[workflow boundary ADR](decisions/2026-11-10-track-b-prefect-optional-orchestration.md).
No new persistent service or source/finance/trading authority.

**Engineering merge versus runtime promotion (owner decision 2026-11-10):**
[Gate requested actions, not source-code existence](decisions/2026-11-10-merge-vs-runtime-promotion.md).
Nonactivating code may merge after engineering verification without prospective
alpha, deployment or trading authorization; execution gates remain fail closed.

Use live GitHub, private SQLite, original source evidence, financial journals and
verified deployment metadata for current facts. OptMem and dated studies provide
context. [AGENTS.md](../AGENTS.md) defines the execution workflow.

## Canonical guides

**Pydantic-native program (#213):** [final 28-family / 13-fault engineering acceptance](PYDANTIC-NATIVE-ACCEPTANCE-RESULTS-20261109.md), [cross-repository compatibility](PYDANTIC-CROSS-REPOSITORY-COMPATIBILITY-20261109.md), [migration engineering evidence](PYDANTIC-NATIVE-ENGINEERING-20261109.md), [preserved Q3–Q39 design closure](PYDANTIC-NATIVE-DESIGN-CLOSURE-20261109.md), [domain glossary](../CONTEXT.md), [28-family acceptance matrix](PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md), [13 combined-fault cases](PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md), and [migration roadmap](PYDANTIC-NATIVE-MIGRATION-ROADMAP-20261109.md). Historical design documents retain their original status; current implementation authorization and evidence are recorded separately. #229 requires separate deployment authorization.

The Marimo operator dashboard was **retired early on 2026-11-08** at operator direction while #190/#191 remained unaccepted; #192 is not closed or technically accepted. See [the retirement record](DASHBOARD-RETIREMENT-20261108.md) for preserved artifacts, local recovery evidence and the untested 8443 restoration. Grafana remains the only protected operator surface (`ops/grafana-phase1/`). The separately published [Copytrade Ops Control Center](OPS-CONTROL-CENTER-20261111.md) is a public read-only, nonauthoritative sidecar; it is not a Guardian, registry writer, or Grafana replacement. The earlier [Phase 1](DASHBOARD-PHASE1.md), [Phase 2](DASHBOARD-PHASE2.md), [Phase 3](DASHBOARD-PHASE3.md) and [final audit](DASHBOARD-FINAL-AUDIT-20261107.md) records are historical evidence and no longer describe current runtime.

| Responsibility | Guide |
| --- | --- |
| Repository ownership and data flow | [Architecture](ARCHITECTURE.md) |
| Wallet/cohort/portfolio discovery | [Registry-first workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md) |
| Protected native metadata writes | [Native SQLite controls](SQLITE-NATIVE-LEGACY-LOCK-20261105.md) |
| Registry release, verification and rollback | [Registry release runbook](WALLET-REGISTRY-RELEASE-RUNBOOK.md) |
| Default fixed-k sizing; leader NAV optional | [Sizing policy](RISK-BUDGETED-K-SIZING-20261106.md) |
| Signed producer/Guardian handoff | [Production handoff](PRODUCTION-HANDOFF.md), [V4 source export](V4-PROP-SOURCE-EXPORT-20261108.md) |
| Source acquisition and retrospective recovery | [Data acquisition](DATA-ACQUISITION.md), [Vike contract](VIKE-DATA-RECOVERY-20261106.md) |
| Persistent public observation | [Continuous observer](FORWARD-PAPER-CONTINUOUS-OBSERVER.md) |
| Approved official position-first T+300 policy | [2026-11-08 position authority ADR](decisions/2026-11-08-position-first-t300.md) |
| Approved fast-wallet Polars screening design (planning only; no changes to old oracle/V4) | [2026-11-09 1m three-scenario screening ADR](decisions/2026-11-09-v4-aligned-fast-wallet-screening.md) |
| Position-first v4 isolated release and rollback | [V4 deployment runbook](V4-POSITION-FIRST-DEPLOY-20261108.md) |
| Owner-requested 16-portfolio prospective virtual-paper campaign (not SQLite promotion) | [16-portfolio paper release and exclusions](V4-SIXTEEN-PAPER-20261109.md) |
| Pydantic V4 16-portfolio SHADOW deployment and first authentic P1 T+300 evidence | [16-portfolio rollout](PYDNATIVE-V4-SIXTEEN-SHADOW-20261109.md), [real T+300 P1 trace](PYDNATIVE-V4-REAL-T300-TRACE-20261109.md) |
| Additive Vike selected fills + 1m estimated paper candidate (not cutover) | [Vike migration and reversible observer deployment](FORWARD-PAPER-VIKE-MIGRATION-20261108.md) |
| Isolated, registry-sealed virtual paper portfolio deployments | [Registry paper profiles](REGISTRY-PAPER-PORTFOLIOS-20261107.md) |
| Protected standby/watchdog staging | [Protected operations](FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md) |
| Native capability discovery and operator commands | [Agent operations](AGENT-NATIVE-OPERATIONS.md), [Runbook](RUNBOOK.md) |
| Scientific evidence and signoff | [Qualification](QUALIFICATION.md), [Governance](GOVERNANCE-GATES.md) |
| Track B v2 read-only rollout, Prefect and rollback | [Track B SHADOW rollout](TRACK-B-SHADOW-ROLLOUT-20261111.md), [Prefect research adapter](TRACK-B-PREFECT-ORCHESTRATION-20261110.md) |
| Portfolio/prop-challenge comparisons | [Native contract EV tool](CONTRACT-PORTFOLIO-EV-TOOL-20261105.md) |
| Recover and resume blocked work | [Blocker recovery](BLOCKER-RECOVERY.md) |

Private SQLite governs indexed metadata; Guardian in prop-production governs
protected follower finance. A public observer is not a financial paper worker.
The current research selection can remain BLOCKED_MISSING_EXTERNAL_PROOF while
physical SQLite integrity and explicit historical lookups verify successfully.
Default fixed-k does not require leader whole-account NAV. Legacy NAV-relative
studies below retain their original assumptions.

The reviewed default branches are copytrade-pm/main, trading-connector/main and
prop-production/feat/account-guardian-program. Recheck GitHub rather than assuming
those pointers never change. The application owns the single compatibility pin
manifest and local cross-repository runner; installed revisions require separate
OS/release verification.

## Detailed and historical references

**Agent requirement:** any live wallet, evaluation, exclusion, portfolio, paper status or deployment question must first follow [the mandatory registry-first workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md), including `doctor` source SHA/as-of and installed release verification. OptMem and dated narrative reports only point to sources; they do not authorize live status.

| Goal | Authoritative guide | Contains |
| --- | --- | --- |
| **VPS operator quick start (read-only)** | [Operator guide](OPERATOR-GUIDE-20261104.md) | Pinned-release commands, saved wallet/portfolio discovery, service checks, evidence statuses and safe rollback boundaries |
| **Mandatory registry-first agent workflow** | [Registry lookup and evidence contract](WALLET-REGISTRY-AGENT-WORKFLOW.md) | Required commands, source generation, namespace/as-of, release vs paper vs scientific/trading authority; incident and OptMem discipline |
| **Current portfolio selections and wallet/evaluation queries** | [Research catalog interface](WALLET-REGISTRY-STATUS-20261104.md), [Gemini Portfolio Freeze V2](decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.md), [V2 JSON roster](decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.json) | Dated V2: E6 primary, E2 challenger, P1 baseline, P14 archived; query SQLite for the current selection and its provenance |
| Operate private SQLite inventory (standalone research read; WR/FP acceptance partial) | [wallet status](WALLET-STATUS.md), [acceptance matrix](WALLET-REGISTRY-ACCEPTANCE-20261104.md), [registry checkpoint](WALLET-REGISTRY-STATUS-20261104.md), [paper boundary](WALLET-REGISTRY-PAPER-CONTRACT-20261104.md), [negative evidence](WALLET-REGISTRY-SIGNED-NEGATIVE-EVIDENCE-20261104.md), [release/rollback](WALLET-REGISTRY-RELEASE-RUNBOOK.md), [review hardening / future signed selections](WALLET-REGISTRY-REVIEW-HARDENING-20261104.md) | SHA-bound metadata, 158 research wallets in dated snapshot, 22 exclusions, read-only runtime adapters; **NOT** trading authority |
| **Run approved Polars milestone #2 engineering tests and check scientific blockers** | [Milestone #2 two-track acceptance](OFFLINE-MILESTONE2-ENGINEERING-ACCEPTANCE-20261104.md), [engineering verification matrix](OFFLINE-MILESTONE2-ENGINEERING-VERIFICATION-20261104.md), [sealed 90-day historical-oracle research job](OFFLINE-HL94-ORACLE-JOB-20261104.json), [operator runbook](RUNBOOK.md) | Single manifest-driven CLI yields immutable PM-03 synthetic fixture report or SHA-sealed real historical-oracle SCREEN_ONLY report; no genuine first-known, real contractual PASS or trading authorization |
| **Audit real local Hyperliquid historical fills and Polars minute matching** | [90-day real historical-oracle evidence](OFFLINE-PIT-REAL-ORACLE-20261104.md) | 94 SHA-pinned source files, 450,172 in-window perp fills, 216 markets and SHA-verified 1m alignment; **not** historical NAV/PIT follower P&L |
| Inspect offline Polars 2.x source/market preprocessing | [Offline PIT processing checkpoint](OFFLINE-PIT-PROCESSING-20261104.md) | Strict per-fill delay, whole-book guard, native exact minute join and immutable cache — partial engineering only |
| Audit offline Polars 2.x sweep baseline | [Offline PIT baseline (2026-11-04)](OFFLINE-PIT-BASELINE-20261104.md) | Synthetic historical-oracle benchmark, frozen PM-01/PM-03 contracts and resource limitations; not an optimizer or live evidence |
| Review original P1 selection | [2026-11-02 three-wallet decision](decisions/2026-11-02-gemini-selected-three-pod.md) | Historical frozen P1 remains unchanged; no automatic FP worker change |
| Review Gemini Phase 2 alternatives | [2026-11-03 alternative portfolio registry](decisions/2026-11-03-gemini-alternative-portfolios.md) | Preserved exploratory sets |
| Review Phase 3 historical freeze | [2026-11-03 Phase 3 adoption](decisions/2026-11-03-gemini-phase3-adoption-180d.md) | Original P1/P14/P16/P15 decisions remain immutable; V2 changes new-study priority only |
| Understand why modules exist and what is *not* connected | [Architecture and contracts](ARCHITECTURE.md) | Two evidence pipelines, module ownership, immutable boundaries |
| Review Trader Intelligence engineering acceptance and the outstanding science gates | [2026-11-03 engineering acceptance](TRADER-INTELLIGENCE-ENGINEERING-ACCEPTANCE-20261103.md) | Exact merged commits, core/native and ensemble tests, C/X delivery smoke, frozen future design, independent-outcome gaps and rollback |
| Continue engineering for TI-04/05/06 and inspect observed P1 source blockers | [November 4 TI continuation](TRADER-INTELLIGENCE-CONTINUATION-20261104.md) | Native minute-window verifier, 300s/600s model stresses, strict matched control v2, real 141-event SHA-pinned source and 99/42 market coverage audit; science still blocked |
| Review in-progress Trader Intelligence A/B/C/X research | [Trader Intelligence checkpoint](TRADER-INTELLIGENCE-CHECKPOINT-20261102.md) | PIT roster and journal intake, five-minute hypothetical follower replay, matched control scaffold, unqualified research grade, Telegram shadow consumer |
| Prepare a future scientific holdout and inspect signed economic evidence | [Trader Intelligence prospective study](TRADER-INTELLIGENCE-PROSPECTIVE-STUDY-20261103.md) | Proposed P1/P14 30-day future holdout, five policies, required native evidence, read-only signed-outcome readiness CLI; registration **not yet operational** |
| Inspect observed P1 negative/uncertain economics without reusing a holdout | [P1 exploratory evidence audit](TRADER-INTELLIGENCE-P1-EXPLORATORY-AUDIT-20261103.md) | Private SHA-pinned real journal/outcome report; matched source/market samples, source coverage and Holm-corrected uncertainty; **no qualification** |
| Review P1 current native 11-DEX private snapshot | [P1 source snapshot](TRADER-INTELLIGENCE-P1-NATIVE-SOURCE-20261103.md) | Bounded official REST read-only 3-wallet snapshot, per-DEX immutable SHA receipts, account consistency and non-atomic/unknown equity limits |
| Start with a wallet, vendor fills, source gaps, OHLCV, or a new cohort | [Wallet data and acquisition](DATA-ACQUISITION.md) | Frozen 36 cohort, private paths, HyperX/ML4T sources, bounded repairs and fresh observations |
| Execute the supported research steps | [Research operator runbook](RUNBOOK.md) | Verified commands, exact artifact handoffs, safe test and incident responses |
| Decide what counts as evidence or authorization | [Qualification gates](QUALIFICATION.md) | Provenance clocks, source/follower PnL, PIT, Propr universe, states and blockers |
| Handle independent review without per-turn judge overhead | [Governance decision boundaries](GOVERNANCE-GATES.md) | Routine exemptions, protected operations, signed review checks, fail-closed limitations |
| Audit the independent signed receipt contract | [PM-01 prospective ledger](PM-01-prospective-ledger.md) | `RECEIPT → AUDIT → OUTCOME → PM-02`, signatures and CLI |
| Audit the account model | [PM-03 shadow simulator](PM-03-shadow-account.md) | Frozen public rulebook, reconciliation, HALT, stress and no-order boundary |
| Inspect optional PM-04 three-pod shadow hardening | [PM-04 contract](PM-04-shadow-hardening.md) | Versioned pod targets, batching, risk budgets, read-only external evidence and no-live-order gate; Issue #12 |
| Reproduce PM-04 18-case engineering acceptance | [PM-04 acceptance matrix](PM-04-acceptance.md) | Fixed-input 18 scenarios, fault recovery, comparison and manual halt/reconciliation runbook |
| Review integrated A/B/C intent and source operations | [Recovery integration](RECOVERY-INTEGRATION.md) | PR7/15/16 lineage, exact whole-book handoff, bounded durable source capture |
| Reproduce explicit legacy wallet-equity-relative sizing | [Equity-normalized wallet exposure](EQUITY-WEIGHT-SIZING.md) | Source notional/equity, follower pod capital, catch-up and historical NAV availability |
| Execute equity-weighted Q3 3-pod portfolio research | [Q3 sparse-equity execution results](Q3-SPARSE-EQUITY-PORTFOLIO-EXECUTION-20261102.md) | 84 hindsight combinations; source-NAV carry, A/B/C risk and exposure fidelity, 3 capacity-stress follow-ups; zero qualified |
| Inspect the W042/W044/W028 replay and mark-ordering regression | [Q3 W042 + W044 + W028 results](Q3-TRIO-W042-W044-W028-20261102.md) | Four executed equity-weight scenarios, SHA audit, missed risk exposure and PM03 quote-mark correction; not qualified |
| Review archived gross-notional proxy run | [Q3 conditional observed-chain replay](HISTORICAL-THREE-WALLET-COMPARISON.md) | Historical 84-combo predecessor, not the source-equity sizing objective |
| Operate registered prospective PM02 decisions | [PM02 evidence gates](PM-02-EVIDENCE-GATES.md) | Whole-account v2 audits, immutable OOS looks, multiplicity, lifecycle and conservative risk |
| Review the future broker interface boundary | [ML4T/Propr integration specification](ML4T-PROPR-INTEGRATION.md) | Actual installed source findings, native identity, mandatory mismatch veto and offline-only contract tests |
| Understand the extraction itself | [Provenance](PROVENANCE.md) | Filtered source history and verified original PM-01/PM-02 byte parity |

Start a task with `AGENTS.md`, this index, the relevant source code/tests, then the **live** issue and PR; do not treat an archived report as a current service or data state.

Research selection and documentation updates make no running roster/service changes. Worker admission and deployment require their separate verified contracts.

**Combo 2 paper-only development:** [single-issue, five-minute paper tracker guide](COMBO2-PAPER.md) links the frozen spec and one-work-item plan. This is a local synthetic engineering preview, not a live Propr automation.

## End-to-end mental model

```text
Wallet research and frozen HyperX roster (PRIVATE, upstream of this repo)
    |
    +--> historical vendor fill pages + manifest SHAs ----+
    |                                                     |
    +--> bounded new HyperX generations (optional) -------+--> PM-01 source/market audit
    |                                                             |
    |          native Hyperliquid 1m from ml4t-data ----------------+
    |                                                             |
    |                                        PM-01 36x(5m,15m,60m) historical replay v2
    |                                                             |
    |                                        PM-02 research card / EMPTY-or-R proposal
    |                                                             |
    |                                        PM-03 shadow-only bridge and stress studies
    |
    +--> bounded WS / REST future receipts (PRIVATE)
                  |
           receipt SHA ledger --> independent signed audit
                  |                      |
                  +--> independently signed, matured follower/control economics
                                             |
                                  PM-02 as-of consumer (optional)
```

**Critical separation:** the historical branch does *not* feed genuine first-known follower observations to the forward branch. The signed-receipt adapter is present, but an **independent, real-world verified matched-outcome producer is not implemented**. A passed unit test, vendor fill time or account-simulator win is not alpha.

## What is on `main` vs elsewhere

- `main` at 2026-11-04 merge **2479365**: PM-01 historical replay, bounded HyperX recovery/WS/REST, frozen 36-wallet contracts, native minute/Propr-scope audits, PM-02 evidence/lifecycle/allocator, independent signed prospective-ledger seam, PM-03/04 synthetic risk, first-party CI **and read-only Trader Intelligence**. TI PR #36 merged as **da9afcdf**, strict PIT/matched research through PR #40 as **5456690**, design/acceptance docs PR #41 as **309a71c**, and the TI #31-33 research engineering follow-up PR #75 as **2479365**.
- Trader Intelligence remains **C/X at 0R**, without independent calibrated A/B, real executable follower/control economics or trading permission. The companion ensemble C/X digest PR #9 merged into the ensemble **feature branch**, with a separate digest-only pinned release; it is not a production trading engine, an account-risk policy or a qualified predictor. See the [November 4 continuation](TRADER-INTELLIGENCE-CONTINUATION-20261104.md) and live issues #31-33.
- **Draft PR #7** (`feat/pm36-synchronized-challenge-research`) is **not on `main`** as of this inspection. Its 2026Q3 wallet research and command entrypoints must not appear in mainline runbooks until merged. Its VPS worktree has been observed with concurrent uncommitted changes: never reset, stash or clean it.
- Scientific successor [PM-01 Issue #4](https://github.com/hzminhzz/copytrade-pm/issues/4) and [PM-02 Issue #5](https://github.com/hzminhzz/copytrade-pm/issues/5) remain open. PM-03 [Issue #2](https://github.com/hzminhzz/copytrade-pm/issues/2) closed **engineering-only**, not authorized for live trading.
- PR18 integration verified **363 passing core and market-extra tests**, build, Ruff and green GitHub CI. Later recovery validation is recorded with its exact commit and evidence in [the recovery disposition](RECOVERY-DISPOSITION-2026-11-01.md). These are dated engineering results, not scientific qualification.

## Historical documents — use as dated evidence, not an execution playbook

| Document | Safe interpretation |
| --- | --- |
| [PM-01 fill-only](PM-01-fill-only.md) | Progressive October 30–31 source and replay investigations; early counts superseded by later sections |
| [PM-01 Propr 90%](PM-01-propr-90pct-scope.md) | Dated 90% **market-day** milestone; commands contain a legacy checkout and frozen artifact paths |
| [PM-01 direct execution](PM-01-2026-10-31-direct-execution.md) | Forensic historical result; not executable/qualified follower economics |
| [PM-01 Rust replay](PM-01-replay.md) | *Separate* historical Rust observation path, not required by HyperX fill-only PM-01 |
| [PM-02 research](PM-02-research.md) | Source-era partial-engineering claims; compare to current `pm_manager` and tests |
| [PM-02 old goal](PM-02-goal.md) / [migration checkpoint](PM-MIGRATION-CHECKPOINT.md) | Archived source/migration milestones; do not resume obsolete automations or PR numbers |

Where a historical document says “current,” “staging,” an old checkout path, or “PR #7” without a repository name, the live `copytrade-pm` code/GitHub state and the guides above take precedence. Preserve the old document as provenance rather than silently rewriting its scientific results.

## Recovery on blockers

On blocked data, tests, tools or evidence, use [Autonomous blocker recovery](BLOCKER-RECOVERY.md). Repair and verify recoverable dependencies, resume the wider approved objective, and keep affected scientific results fail-closed.

## Safe default for a new work session

1. Verify repository path, HEAD, branch, dirty/untracked work and remote; read `AGENTS.md`. Use an isolated worktree from fetched `origin/main` for changes.
2. Confirm the private 36-wallet manifest and market root exist **without printing raw pages, address maps or credentials**.
3. Check `git ls-files`, the relevant `src/copytrade_pm` code and its tests before relying on a doc command. Run CLI `--help` for flags.
4. Choose one stage in the [runbook](RUNBOOK.md). Save a new SHA-addressed private artifact; preserve frozen inputs.
5. Report **ENGINEERED / VERIFIED / SCIENTIFICALLY QUALIFIED / AUTHORIZED** separately. Unknown stays UNKNOWN. Do not start a live order adapter or alter the separately deployed ensemble.

## Documentation ownership

- This index is the single navigation and live-snapshot page; [ARCHITECTURE](ARCHITECTURE.md) owns module boundaries; [DATA-ACQUISITION](DATA-ACQUISITION.md) owns vendor/data operations; [RUNBOOK](RUNBOOK.md) owns command examples and triage; [QUALIFICATION](QUALIFICATION.md) owns acceptance terminology.
- Detailed PM-01 signed-audit fields and PM-03 risk formulas stay in their existing specialist docs; link there instead of duplicating the contracts.
- Update these guides **in the same PR as any CLI/schema/source-path change**, and verify links/commands/CI. Do not insert transient report counts into evergreen sections without date, commit SHA, and evidence scope.
