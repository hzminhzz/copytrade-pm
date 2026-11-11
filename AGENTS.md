# copytrade-pm — agent operating contract

**Start here.** Research, source observation and virtual paper only. No broker credentials, real orders or trading authorization in this repository. ChatGPT executes work directly; preserve other sessions' changes. This file is the agent entrypoint; [docs/INDEX.md](docs/INDEX.md) is the navigation directory.

## First 5 minutes

1. Read this file, [docs/INDEX.md](docs/INDEX.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Read the *owning* contract/runbook for the task before changing it. Dated studies are evidence, not standing instructions.
2. Inspect real `origin/main`, PRs/issues, the current branch, dirty/untracked work and all worktrees. Use an isolated worktree if the main checkout is dirty or owned by another session. Never reset, clean, overwrite or repurpose another agent's work.
3. Run `~/.optmem/memo wake`, completing all pages; use `memo recall` and `memo zoom` for durable decisions. Memory does not override Git, SQLite, live source receipts or OS evidence. Update memory after binding decisions with short `memo note` (maximum 280 bytes); never edit memory storage directly.
4. Discover the real owner before adding a capability: `uv run --frozen --group dev copytrade-pm capabilities list`, `uv run --frozen --group dev copytrade-pm capabilities show <id>`, `uv run --frozen --group dev copytrade-pm capabilities validate`. See [agent-native operations](docs/AGENT-NATIVE-OPERATIONS.md).
5. Verify actual installed release SHA, service PID, original source/financial journals, registry identity and provider coverage before claiming a service is running correctly. **MERGED != DEPLOYED != RUNNING VERIFIED != SCIENTIFICALLY QUALIFIED != TRADING AUTHORIZED.**

## Authority — one owner per fact

| Fact | Owner |
| --- | --- |
| Reviewed code and accepted ADRs | GitHub exact SHA; [documentation directory](docs/INDEX.md) |
| Wallets, exclusions, aliases, sealed portfolios | Private **SQLite** registry; [registry-first workflow](docs/WALLET-REGISTRY-AGENT-WORKFLOW.md) |
| Original observations, first-known clocks, coverage gaps | Immutable private source and market journals |
| Research position accounting, paper risk and portfolio simulation | PM-03/PM-04 in this repository |
| Signed risk permits, actual follower inventory and broker finance | Guardian in `prop-production` |
| Provider transport and broker-specific normalization | `trading-connector` |
| Running version | Real service PID + OS configuration + exact deployed checkout |
| Long-lived context | OptMem; never runtime truth |

## MANDATORY REGISTRY-FIRST workflow

For wallet/portfolio/paper/readiness questions, first run from the verified checkout:

```bash
uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev copytrade-wallet-registry status
uv run --frozen --group dev copytrade-wallet-registry native status
uv run --frozen --group dev python scripts/registry_release.py verify
```

Verify the SQLite **source generation** (manifest SHA/as-of) against the actual query and compare the dated [WALLET-STATUS.md](docs/WALLET-STATUS.md) only as historical evidence. Physical SQLite integrity, unsigned selection, selected signed seal, original source coverage, running financial worker and Guardian permit are **different gates**. A `BLOCKED_MISSING_EXTERNAL_PROOF` result is not database corruption and does not permit an unsigned selection. Verify original namespace/version/as-of; `q3/B` is not `gemini.phase5/B`. Read-only observer preflight checks *requested independently sealed* portfolios without requiring unrelated unsigned priorities; it still rejects an unsealed requested portfolio. See [the registry policy](docs/WALLET-REGISTRY-AGENT-WORKFLOW.md) and [release/rollback](docs/WALLET-REGISTRY-RELEASE-RUNBOOK.md). Do not perform native registry writes as diagnostics.

## Source: Vike-first **target**, official position authority **now**

**Approved future transport:** prefer a shared, wallet-filtered **Vike** stream for new wallet ingestion instead of scaling direct Hyperliquid user-specific WebSockets across this VPS shared IP. Read the [binding Vike-first migration ADR](docs/decisions/2026-11-11-vike-first-wallet-source.md) before touching provider ingestion. Direct Hyperliquid remains bounded independent verification/fallback. **The shared 14-parent Vike observation collector and bounded official REST census have been implemented as opt-in, nonactivating engineering only; the complete reconciled source and paper cutover remain unimplemented.** The live `hl.positions` canary observed a provider GAP, not a qualified book. See [current migration evidence and blockers](docs/V4-VIKE-FIRST-MIGRATION-PROGRESS-20261111.md).

**Current V4 contract:** only a genuine observed change of a complete **official** selected-account all-DEX perp position book after a non-actionable baseline can initiate new risk. Vike `hl.fills` and `hl.positions` are not independently full account-position authority. A fill-reconstructed book requires an independently reconciled complete baseline, full continuity and matching official proof before paper admission. A gap/stale/mismatch blocks new risk; never infer an exit or create an earlier first-known timestamp from historical REST recovery. See [current position-first ADR](docs/decisions/2026-11-08-position-first-t300.md) and [0911 budget incident](docs/V4-0911-WS-SUBSCRIPTION-RECOVERY-292.md). Historic 7-of-14 coverage is a dated observation, not a guaranteed present count.

**Timing:** first genuine locally known transition T0 → one new-risk attempt at **T0+300 seconds** under existing grace and current complete book; coalesce later updates without clock reset. Verified source reductions and protective risk exits attempt immediately. Keep event, local receive, durable commit, decision and order clocks distinct. Preserve existing immutable first-known proofs, source/financial journal versions and crash/restart semantics. Never rewrite past source or financial evidence. See [V4 canonical paper](docs/V4-CANONICAL-FRESH-PAPER-20261111.md).

**Sizing:** `FIXED_K_NATIVE_QUANTITY` by default. Follower target notional = signed `k * leader_native_quantity * source_mark`, converted with an independent follower quote. Source leader NAV is optional; source selected account/DEX scope, source exit receipts, frozen k, follower equity/headroom, broker reconciliation, PM03/PM04 pod losses, daily/trailing floors, gross/market limits, and Guardian permit remain mandatory at their boundaries. Legacy `ALLOCATION_OVER_LIVE_NAV` remains explicit historical opt-in. Never confuse a $200 modeled stop with guaranteed maximum fill loss. See [fixed-k policy](docs/RISK-BUDGETED-K-SIZING-20261106.md).

**Research:** historical HyperX/Vike fills and market bars are retrospective. They cannot claim prospective first-known times or executable follower PnL. Preserve frozen PM-01 membership, `pm01_fill_only_replay_v2`, selection source hashes, full-source positions and independently pinned OOS/holdout boundaries. Follow [data acquisition](docs/DATA-ACQUISITION.md) and [qualification](docs/QUALIFICATION.md); do not silently relax eligibility, cost, capacity or risk gates.

## Safe execution and verification

- **Before operations:** follow [RUNBOOK](docs/RUNBOOK.md) and the exact versioned release runbook; inspect service identity, restart/reconciliation semantics, source budgets, WAL size and deployment pins. Never run historical `--apply` examples just because a dated document contains them. For current canonical virtual paper read [its dedicated release runbook](docs/V4-CANONICAL-FRESH-PAPER-20261111.md). Guardian/broker changes require separate protected authority.
- **MANDATORY contract EV tool:** for portfolio/prop comparisons use native `research.contract_selector` via `copytrade-pm contracts rules` and `copytrade-pm contracts compare --portfolio NAMESPACE/ID --tape PRIVATE_TAPE`. Resolve portfolios from SQLite and require genuine matched net follower evidence; missing authentic tape means BLOCKED, synthetic EV means SCENARIO_ONLY; neither gives permission to trade. See [contract EV](docs/CONTRACT-PORTFOLIO-EV-TOOL-20261105.md).
- **For Prefect:** opt-in private Track B research orchestration only; never own source hot loops, live finance, k release or orders. See [Prefect runbook](docs/TRACK-B-PREFECT-ORCHESTRATION-20261110.md).
- **For dashboards:** Grafana is the protected operator surface; old Marimo docs are archived evidence. The public ops sidecar is read-only and nonauthoritative. See [dashboard retirement](docs/DASHBOARD-RETIREMENT-20261108.md) and [control center](docs/OPS-CONTROL-CENTER-20261111.md).
- **For blockers:** diagnose → repair → retest → resume, preserving adverse evidence and other agents' work. See [blocker recovery](docs/BLOCKER-RECOVERY.md). When inspecting a stash containing untracked files, verify its **third parent** (`<stash-sha>^3`) separately; see [follow-up audit](docs/RECONCILIATION-FOLLOWUP-20261107.md).

Verify exact-head tests, Ruff format/lint, build, capability catalog, relevant adversarial scenarios and cross-repository consumer pins when affected. `README.md` owns commands; `prop-production/src/prop_production/compatibility.json` owns compatibility pins. Independently captured signed agent traces, not test fixtures, are required for [agent trace evaluation](docs/AGENT-TRACE-EVAL-20261105.md). Git merge needs engineering evidence; runtime promotion requires action-specific gates. See [merge vs promotion ADR](docs/decisions/2026-11-10-merge-vs-runtime-promotion.md).

## Documentation maintenance is engineering work

For every source, contract, command, risk, release or architecture change: update **one canonical owner**, its ADR when a decision changed, `docs/INDEX.md` navigation and relevant OptMem record. Link instead of duplicating rules. Keep historical ADRs/experiments/incident proofs intact with supersession pointers. Record **APPROVED TARGET / IMPLEMENTED / TESTED / DEPLOYED / SCIENTIFICALLY_QUALIFIED / TRADING_AUTHORIZED** separately. Keep ephemeral balances, PIDs, disk sizes and portfolio PnL out of durable agent rules. Final report: exact changed paths, tests, installed evidence if checked, commit/PR, unresolved gaps.
