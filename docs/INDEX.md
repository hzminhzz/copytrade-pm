# copytrade-pm handbook — start here

**Audience:** an engineer/researcher taking over `hzminhzz/copytrade-pm`, or an operator tracing one wallet from HyperX evidence through PM-01, PM-02, and PM-03. **Canonical entry point for this repo.** Recovery inspection: **2026-11-01**, PR17 verified at `d3e0ce916c2f0b64ad36593f55b261607ec0cbdd`; E0/E4 recovery merged through PR18 at `7a8be42dbee374f7ce3d5702f98dadc638853f4a`. Recheck live Git and private source manifests before acting.

## Read in this order

| Goal | Authoritative guide | Contains |
| --- | --- | --- |
| Understand why modules exist and what is *not* connected | [Architecture and contracts](ARCHITECTURE.md) | Two evidence pipelines, module ownership, immutable boundaries |
| Choose wallets and compose fixed-loss prop challenge pods | [Wallet selection and three-pod checklist](WALLET-POD-SELECTION.md) | $200 pod-loss hypothesis, whole-book sizing, archetypes, source-quality checklist, clone and execution checks, qualification gates |
| Review the Gemini 5-wallet report without promoting simulated profits | [2026-11-02 independent Gemini methodology audit](GEMINI-REPORT-METHODOLOGY-AUDIT-20261102.md) | Verified CSV counts, source PnL, clone correlation, and unverified 50-200ms follower/pass claims |
| Investigate new **non-carry directional** Nansen wallets | [2026-11-02 Nansen 10-wallet shortlist and funding audit](NANSEN-DIRECTIONAL-POD-SHORTLIST-20261102.md) | Ten historical source research candidates, live books, independent signed funding cashflows, hedge/carry vetoes, missing HyperX/equity replay gates |
| Start with a wallet, vendor fills, source gaps, OHLCV, or a new cohort | [Wallet data and acquisition](DATA-ACQUISITION.md) | Frozen 36 cohort, private paths, HyperX/ML4T sources, bounded repairs and fresh observations |
| Execute the supported research steps | [Research operator runbook](RUNBOOK.md) | Verified commands, exact artifact handoffs, safe test and incident responses |
| Decide what counts as evidence or authorization | [Qualification gates](QUALIFICATION.md) | Provenance clocks, source/follower PnL, PIT, Propr universe, states and blockers |
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

- `main`: PM-01 historical replay, bounded HyperX recovery/WS/REST probes, 36-wallet source contracts, minute-market and Propr-scope audits, PM-02 evidence/lifecycle/allocator, signed local prospective ledger adapter, PM-03 deterministic **synthetic** account simulator, first-party CI.
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
