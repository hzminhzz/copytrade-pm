# ADR — Pydantic-native source acceptance, wallet actions, k lifecycle and Prefect boundary

**Date:** 2026-11-09  
**Status:** **Q10–Q15 APPROVED FOR ARCHITECTURAL DESIGN** by the owner in Grill With Docs Round 3. **No application implementation, commit, merge, service installation, restart, deployment, registry mutation, paper-finance policy promotion or broker authorization.**  
**Prerequisites:** [Q1–Q3](2026-11-09-source-wallet-health-k-recalibration-round1.md), [Q4–Q9](2026-11-09-source-wallet-health-k-recalibration-round2.md), [Pydantic-native domain ownership](2026-11-09-pydantic-native-contract-ownership.md), [fixed-k policy](../RISK-BUDGETED-K-SIZING-20261106.md) and [official T+300 source semantics](2026-11-08-position-first-t300.md).  
**Working baseline:** `copytrade-pm` isolated worktree derived from `origin/main=6c07cc6d36099135881be27a072c426a52a24f24`; any later implementation must revalidate the actual code, installed release and user-service state.

## Context and invariants

The existing 16-portfolio SHADOW study has 14 source accounts, a shared official native Hyperliquid source stream, a SQLite PaperJournal for original source/continuity evidence, and independent PM03/PM04 paper ledgers. The latest inspected source-unit evidence included 24 historical restarts and `PAPER_JOURNAL_BUSY_OR_UNAVAILABLE`, but that error wraps multiple lock/SQLite causes and is **not itself a root-cause diagnosis**. A previous authentic source change was correctly canceled on a GAP before T+300. The present Pydantic wallet-health Evals baseline is synthetic and cannot establish real-wallet edge detection.

All new domain boundaries **must reuse the implemented strict/frozen/versioned Pydantic v2 contract plane** (with explicit Decimal/UTC conversion at provider adapters), deterministic reducers, original evidence/provenance SHA and existing journals. Retain the exact first-known T+300 admission rule, immutable past releases, and independent Guardian authority. Do not confuse valid contracts, research eligibility, modeled fills, scientific qualification or production permits.

## Q10 — Separate source-writer reliability from the full forward economic lifecycle (APPROVED)

- Establish an adversarial *engineering* test gate for filesystem lease collision; SQLite BUSY/LOCKED in WAL setup, open and transaction; bounded retries; receiver queue saturation; cancellation; process interruption; corrupt/divergent source; journal replay; multiple consumer cursors and account-local vs shared faults.
- Required invariants: no accepted uncommitted frames, no duplicate committed effects/T0, no backdated local receipt time, no hidden dropped observations, original wire/receipt SHA preserved, immutable stream chain intact, appropriate GAP/quarantine and rebaseline after continuity loss, and no broker route. Test the real cross-process owner boundary where relevant, not just mocks.
- Follow with an independently evidenced **bounded SHADOW canary** using existing 14 selected accounts, original service revisions, verified source/consumer chains, and rollback to a known-good pinned release. Observe restart count, attributable contention, queue high-water, committed-receipt age and actual GAP recovery.
- A successful authentic T+300 entry AND later genuine reduction/exit are required to claim a *complete prospective financial lifecycle*, **not** prerequisites for demonstrating the source writer's bounded fault recovery. No invented arbitrary multi-day soak or SLA thresholds; select numeric budgets from measured baseline in implementation specification.
- **Reject:** declaring a fix from an active systemd process; permitting source frames that only resided in memory to cause new risk; coupling an unrelated absent wallet exit to the source-writer acceptance gate.

## Q11 — Graded wallet-health consequences; no silent exclusion or liquidation (APPROVED)

- Separate a *monitoring assessment* from a *participation decision* and from *financial inventory/Guardian permissions*. For verified severe capital/identity breaches, disallow new research selection; suspending new SHADOW admissions is possible **only** under an explicit versioned active participation policy.
- Stale or missing evidence produces `UNKNOWN`/alert, **not** fabricated capital, loss or liquidation. A seven-day follower deterioration warning prompts review or a bounded risk-off k proposal; it cannot itself force liquidation, mint a financial HALT or purge an existing registry record.
- Genuine official source GAPs retain their own first-known T+300 new-risk fences. Held follower inventory, pending/unknown executions, risk-reducing actions and HALT stay under PM03/PM04 and protected Guardian respectively.
- Recovery from a participation restriction requires fresh attributable evidence and a documented probation/re-admission decision. Existing registry exclusion requires separately governed explicit action; no research job may silently exclude or replace a selected wallet.
- Exact evidence age/activity thresholds and per-reason allowed actions remain **to be specified**, not guessed from a generic score.

## Q12 — Deterministic risk-constrained k estimator with scientific evidence separation (APPROVED)

- For each **portfolio-version + pod + as-of** assess candidate k using PIT-correct follower net outcomes under the **existing** T+300 and PM03/PM04 financial economics. Account for trading costs, adverse entry, observed capacity uncertainty, lot rounding, funding, pod budgets, exposure/concentration, portfolio correlation and daily/trailing restrictions. Source gross profit or equity change is not a substitute.
- The standard `$200` pod loss is an example *nominal loss-trigger budget*, not a guaranteed adverse loss ceiling. Compare modeled realized/mark-to-market follower results under plausible adverse conditions, rather than divide $200 by one recent source-wallet drawdown.
- Use Polars/DuckDB for large causal evaluation and explicit Decimal application at the final signed quantity/risk boundary. Do not build a competing financial simulator or wrap individual bars/fills as Pydantic rows.
- Use OOS/forward evidence and meaningful independent sample size before a positive `INCREASE` recommendation. Sparse evidence means `HOLD`, `DECREASE_REVIEW` or `INSUFFICIENT_EVIDENCE`, never automatic k amplification. Fix numerical minima, k change bounds, drawdown stress cases and objective in the eventual specification using recorded baseline evidence.
- Every result must have a strict Pydantic evidence-bound proposal, separate reason/uncertainty fields, data/algorithm/policy hashes, and clearly non-authorizing outcome classification.

## Q13 — Future-opportunity k activation with immutable existing effects (APPROVED)

- A reviewed k release has explicit **portfolio version and effective time**. Its default effect is on **future eligible entry opportunities**, not retroactive revaluation of historical trades, active paper state or past source timestamps.
- A T+300 pending intent created under an earlier version preserves its original first-known T0, k/decision provenance and one terminal attempt until resolved or canceled; no replay after policy cutover.
- Existing modeled follower inventory and unresolved effects remain accounted for under original financial-event evidence. A separately permitted protective reduction may reduce carried risk under existing PM03/PM04 gates; never apply an automatic *new-risk catch-up* to make current holdings equal a freshly recalibrated k.
- Restart must derive one deterministic active configuration/version from durable signed release state. Whether activation should start a distinct run or a versioned policy record inside a compatible existing run is an **implementation seam requiring actual journal contract inspection**, not permission to overwrite `k_by_pod` in place.
- Research proposals may be scheduled automatically; **automatic deployed k increases are not approved**, and SHADOW decreases still need explicit release-policy authorization.

## Q14 — Use existing Grafana/registry and read-only projections (APPROVED)

- Show **separate**, as-of Pydantic-validated read models for source continuity, capital-flow attribution, eligibility, follower edge warning, proposed k, released effective k, and independent Guardian authority. Avoid one opaque green/red wallet score.
- Keep SQLite wallet registry authoritative for identities/cohorts/exclusions/versioned portfolio metadata, existing source/PM03/04 journals for their evidence, Grafana as the operator interface. No second mutable wallet database, dashboard-owned risk state or broker command path.
- Alerts and operator acknowledgements must preserve their own observed delivery/ACK evidence. Redact wallet addresses where not authorized. An alert cannot automatically clear HALT, exclude a wallet or activate a k release.

## Q15 — Adopt Prefect 3 for justified periodic research; defer Temporal (APPROVED)

**Decision:** Prefer **Prefect 3** for bounded periodic read-only monitoring, attribution, 7/30/90-day PIT follower economics and versioned research k proposals **where orchestration/retries/observability materially improve on simple systemd timers**. This is an approved technology direction, **not authorization to install or operate Prefect yet**.

- First verify workload and operational benefit; simple one- or two-job deterministic schedules may stay on systemd timers. When Prefect is justified, use an **isolated, pinned environment and deployments** on the existing VPS. Its workflow metadata/storage must remain distinct from the official source PaperJournal, registry mutation authority and PM03/04/Guardian financial state. Plan backups, worker identity, secured UI/API, telemetry and rollback before cutover.
- Prefect retries **read-only data collection and append-only evidence-bound research results/proposals** with explicit idempotency keys, e.g. (wallet account identity, as-of cutoff, original evidence SHA, policy/algorithm version). A Prefect task's `Completed` status, cache hit or retry is **not** proof of a committed original receipt, exactly-once financial effect or release approval.
- Keep the **official continuous position observer under systemd** with its own journal/clock owner. Never orchestrate individual T+300 entries, protective exits, PM03 cash or broker permits in Prefect.
- **Defer Temporal**: more sophisticated durable, replayable cross-service workflows could be warranted for later long-running approval/recovery programs, but they introduce server/worker/task-queue and deterministic-workflow complexity not justified by these three features.
- **Pydantic boundary:** Pydantic v2 Validation is the mandatory existing domain-contract system. `Prefect @flow/@task` works for deterministic Python without a Pydantic AI agent. If a future independently evaluated research AI agent is introduced, Pydantic AI's documented Prefect durable-execution integration may make its model/tool calls resumable, but the agent cannot authorize k changes, source admission or broker actions. No AI/Graph/Monty runtime dependency in critical source ingestion.
- Source documents: [Pydantic AI durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/), [Prefect integration](https://pydantic.dev/docs/ai/capabilities/durable_execution/prefect/), [Temporal integration](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/), [Prefect 3 docs](https://docs.prefect.io/v3/), [Temporal docs](https://docs.temporal.io/).

**Rejected alternatives:** replacing continuous source/finance with Prefect or Temporal, mandatory AI agents for deterministic rules, a globally mutable wallet health/risk state, workflow task-cache authority, or installing a new orchestrator without a measured operational benefit.

## Consequences and next frontier

The approved build has three *separate* workstreams: (1) fix and independently verify original source continuity, (2) read-only wallet monitoring with explicit attribution/unknowns, and (3) causal portfolio/pod-specific k research proposals with later immutable governance. They share the existing Pydantic contract plane but not a new shared financial owner.

**Next dependency-ready frontier: Q16 — final end-to-end release, acceptance, sequencing and rollback contract.** Q17 about a real agent diagnostic runtime remains conditional and is **not triggered** by adopting Prefect for deterministic research. See [design tree](../SOURCE-WALLET-HEALTH-K-GRILL-20261109.md). After Q16 is approved, produce an implementation-ready specification only if separately requested. No implementation, commit, merge, deployment or trading activation is authorized by this ADR.
