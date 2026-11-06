# copytrade-pm handbook — start here

**Continuous observer program #129:** [Authoritative lifecycle, preflight, first-known clocks, health, recovery and release runbook](FORWARD-PAPER-CONTINUOUS-OBSERVER.md); [dated implementation and verification evidence](PERSISTENT-OBSERVER-IMPLEMENTATION-20261106.md); [2026-11-06 post-merge independent live blocker diagnostics](PERSISTENT-OBSERVER-POSTMERGE-GATES-20261106.md); [resource remediation and 50-default/50-HIP-3 public socket probes](PERSISTENT-OBSERVER-RESOURCE-REMEDIATION-20261106.md). Engineering, bounded transport observation, real 72-hour shadow acceptance and public service authorization are separate statuses.

**Current Propr public display capture (2026-11-05, research-only):** [157 unique native markets on 3 physical sockets, source SHA, live transport and zero-financial-event tests](FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.md) and [pinned complete configuration](FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json). All 158 displayed categories reconcile to 157 unique markets (COPPER deduplicated); the Top-40 five-group layout is retained for logical reporting, not the current physical connection requirement. This is NOT an authenticated Propr account market list or deployed paper worker.

**Exact 40-market five-shard source layout (2026-11-05):** [Sealed 5×8 market scope](FORWARD-PAPER-MARKET-TOP40-SHARDS-20261105.json) and [live/positive deterministic verification](FORWARD-PAPER-TOP40-FIVE-SHARD-20261105.md). Forty markets verified against official metadata; bounded WebSocket smoke received 628 frames, but P1/E2 had zero fills in the preceding hour and live wallet detection remains UNPROVEN. No financial paper activation.

**Forward public market trades (2026-11-05, research-only):** [Causal market-wide wallet fills and UTC bucket planning](FORWARD-PAPER-PUBLIC-TRADES-20261105.md) extend the native SQLite PaperJournal without financial orders. Public trade receipts and top-level quote estimates are provisional; leader NAV, capacity, protected worker activation and forward economics remain BLOCKED. The existing P1/P14 observer is unchanged.

**Protected paper-worker operations (2026-11-05, staged only):**
[P1/P14 no-order standby, independent HALT-latching watchdog, pinned root
systemd candidate and rollback gates](FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md).
Real root-managed units are **not installed**; the coding user lacks unattended
sudo, source NAV and market admission remain blocked. No financial paper promotion.

**P1/P14 prospective wallet-identity reseal preflight (2026-11-06):**
[read-only PIT audit and unsigned research-selection candidate](P1-P14-PROSPECTIVE-RESEAL-PREFLIGHT-20261106.md).
Original historical seals remain blocked; independent operator signature,
complete account NAV and market execution evidence are still required.

**SQLite metadata authority (2026-11-05):** The private wallet registry is the
single source of truth for current wallets, cohorts and saved portfolios.
[Mandatory registry lookup contract](WALLET-REGISTRY-AGENT-WORKFLOW.md) and
[read-only pinned release/rollback guide](WALLET-REGISTRY-RELEASE-RUNBOOK.md)
distinguish the SQLite inventory SHA from legacy CSV import evidence.


**Pod portfolio contract comparison (research only):** [native read-only EV ranking tool, input schema and blocked-evidence behavior](CONTRACT-PORTFOLIO-EV-TOOL-20261105.md). Run `copytrade-pm contracts rules` or `copytrade-pm contracts compare --portfolio gemini.phase4/E6 --portfolio gemini.phase4/E2`. A positive modeled score is not scientific qualification or account authorization.

**Research-only actuarial simulator:** [challenge-to-payout contract assumptions, reproducible 100,000-path scorecards and limitations](CONTRACT-ACTUARY-RESEARCH-20261105.md). Run `copytrade-pm-actuary --help` after installing the optional `actuary` dependency. This is synthetic economics, not real follower qualification or an account purchase recommendation.

**Agent-native entrypoint:** [capability discovery and read-only operator CLI](AGENT-NATIVE-OPERATIONS.md).
Before implementing new features, use `copytrade-pm capabilities list`, `show`
and `validate` to identify the authoritative native interface; wallet/portfolio
queries additionally require the live registry-first workflow. For native
wallet inventory use `wallets list --cohort ...`; for independently SHA-verified
executed Polars jobs use `research list --cache-root PRIVATE_CACHE`.
For prospective public P1/P14 receipts, see the [pinned observer-only service and rollback](FORWARD-PAPER-PUBLIC-OBSERVER-SERVICE-20261105.md); it is not a protected financial paper worker.
See [P1 operational discovery acceptance](AGENT-OPERATIONS-P1-ACCEPTANCE-20261105.md)
and [P2 agent trace evaluator](AGENT-TRACE-EVAL-20261105.md). P2 engineering
may pass while independent observed model-choice evidence is still blocked.


**Audience:** an engineer/researcher taking over `hzminhzz/copytrade-pm`, or an operator tracing one wallet from HyperX evidence through PM-01, PM-02, and PM-03. **Canonical entry point for this repo.** Recovery inspection: **2026-11-01**, PR17 verified at `d3e0ce916c2f0b64ad36593f55b261607ec0cbdd`; E0/E4 recovery merged through PR18 at `7a8be42dbee374f7ce3d5702f98dadc638853f4a`. Recheck live Git and private source manifests before acting.

## Read in this order

**Agent requirement:** any live wallet, evaluation, exclusion, portfolio, paper status or deployment question must first follow [the mandatory registry-first workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md), including `doctor` source SHA/as-of and installed release verification. OptMem and dated narrative reports only point to sources; they do not authorize live status.

| Goal | Authoritative guide | Contains |
| --- | --- | --- |
| **VPS operator quick start (read-only)** | [Operator guide](OPERATOR-GUIDE-20261104.md) | Pinned-release commands, saved wallet/portfolio discovery, service checks, evidence statuses and safe rollback boundaries |
| **Mandatory registry-first agent workflow** | [Registry lookup and evidence contract](WALLET-REGISTRY-AGENT-WORKFLOW.md) | Required commands, source generation, namespace/as-of, release vs paper vs scientific/trading authority; incident and OptMem discipline |
| **Current portfolio selections and wallet/evaluation queries** | [Research catalog interface](WALLET-REGISTRY-STATUS-20261104.md), [Gemini Portfolio Freeze V2](decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.md), [V2 JSON roster](decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.json) | **E6 new primary, E2 challenger, P1 baseline, P14 archived from new priority**; no running roster/service changes; distinguish saved research from active paper |
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
| Implement wallet-equity-relative sizing, including missed trades | [Equity-normalized wallet exposure](EQUITY-WEIGHT-SIZING.md) | Source notional/equity, follower pod capital, catch-up and historical NAV availability |
| Execute equity-weighted Q3 3-pod portfolio research | [Q3 sparse-equity execution results](Q3-SPARSE-EQUITY-PORTFOLIO-EXECUTION-20261102.md) | 84 hindsight combinations; source-NAV carry, A/B/C risk and exposure fidelity, 3 capacity-stress follow-ups; zero qualified |
| Inspect the W042/W044/W028 replay and mark-ordering regression | [Q3 W042 + W044 + W028 results](Q3-TRIO-W042-W044-W028-20261102.md) | Four executed equity-weight scenarios, SHA audit, missed risk exposure and PM03 quote-mark correction; not qualified |
| Review archived gross-notional proxy run | [Q3 conditional observed-chain replay](HISTORICAL-THREE-WALLET-COMPARISON.md) | Historical 84-combo predecessor, not the source-equity sizing objective |
| Operate registered prospective PM02 decisions | [PM02 evidence gates](PM-02-EVIDENCE-GATES.md) | Whole-account v2 audits, immutable OOS looks, multiplicity, lifecycle and conservative risk |
| Review the future broker interface boundary | [ML4T/Propr integration specification](ML4T-PROPR-INTEGRATION.md) | Actual installed source findings, native identity, mandatory mismatch veto and offline-only contract tests |
| Understand the extraction itself | [Provenance](PROVENANCE.md) | Filtered source history and verified original PM-01/PM-02 byte parity |

Start a task with `AGENTS.md`, this index, the relevant source code/tests, then the **live** issue and PR; do not treat an archived report as a current service or data state.

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
