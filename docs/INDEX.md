# copytrade-pm handbook — start here

**Audience:** an engineer/researcher taking over `hzminhzz/copytrade-pm`, or an operator tracing one wallet from HyperX evidence through PM-01, PM-02, and PM-03. **Canonical entry point for this repo.** Last code/GitHub inspection: **2026-10-31**, `main` at `1434f55`. Recheck live Git and private source manifests before acting.

## Read in this order

| Goal | Authoritative guide | Contains |
| --- | --- | --- |
| Understand why modules exist and what is *not* connected | [Architecture and contracts](ARCHITECTURE.md) | Two evidence pipelines, module ownership, immutable boundaries |
| Research source-faithful position sizing | [E0 wallet replica](E0-WALLET-REPLICA.md) | Complete-book source sizing, fidelity metrics, A/B/C migration, evidence gates |
| Start with a wallet, vendor fills, source gaps, OHLCV, or a new cohort | [Wallet data and acquisition](DATA-ACQUISITION.md) | Frozen 36 cohort, private paths, HyperX/ML4T sources, bounded repairs and fresh observations |
| Execute the supported research steps | [Research operator runbook](RUNBOOK.md) | Verified commands, exact artifact handoffs, safe test and incident responses |
| Decide what counts as evidence or authorization | [Qualification gates](QUALIFICATION.md) | Provenance clocks, source/follower PnL, PIT, Propr universe, states and blockers |
| Audit the independent signed receipt contract | [PM-01 prospective ledger](PM-01-prospective-ledger.md) | `RECEIPT → AUDIT → OUTCOME → PM-02`, signatures and CLI |
| Audit the account model | [PM-03 shadow simulator](PM-03-shadow-account.md) | Frozen public rulebook, reconciliation, HALT, stress and no-order boundary |
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

**E0 source-fidelity contract:** The independently verified *whole-wallet* intended book is the baseline, not individually normalized fill episodes. See [E0 wallet replica](E0-WALLET-REPLICA.md). Existing A/B/C E1/E2/E3 results remain historical partial-episode diagnostics. E0's risk and execution fidelity metrics do not prove source economics.

**Critical separation:** the historical branch does *not* feed genuine first-known follower observations to the forward branch. The signed-receipt adapter is present, but an **independent, real-world verified matched-outcome producer is not implemented**. A passed unit test, vendor fill time or account-simulator win is not alpha.

## What is on `main` vs elsewhere

- `main`: PM-01 historical replay, bounded HyperX recovery/WS/REST probes, 36-wallet source contracts, minute-market and Propr-scope audits, PM-02 evidence/lifecycle/allocator, signed local prospective ledger adapter, PM-03 deterministic **synthetic** account simulator, versioned Wave C two-wallet intake (`pm_wave_c`: frozen 36 + 2 = 38, window-limited), first-party CI.
- **Draft PR #7** (`feat/pm36-synchronized-challenge-research`) is **not on `main`** as of this inspection. Its 2026Q3 wallet research and command entrypoints must not appear in mainline runbooks until merged. Its VPS worktree has been observed with concurrent uncommitted changes: never reset, stash or clean it.
- Scientific successor [PM-01 Issue #4](https://github.com/hzminhzz/copytrade-pm/issues/4) and [PM-02 Issue #5](https://github.com/hzminhzz/copytrade-pm/issues/5) remain open. PM-03 [Issue #2](https://github.com/hzminhzz/copytrade-pm/issues/2) closed **engineering-only**, not authorized for live trading.
- Latest verified on `main` for this snapshot: **234 passing market-extra tests**, `uv build` and Ruff, GitHub CI green. These are *dated engineering results*, not a live quote for future commits.

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
