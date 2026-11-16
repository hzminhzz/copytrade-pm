# ADR — Source recovery, wallet-health monitoring, edge evidence and k release boundaries

**Date:** 2026-11-09  
**Status:** **Q4–Q9 OWNER APPROVED FOR ARCHITECTURAL DESIGN** (Grill With Docs Round 2). No application implementation, commit, merge, installation, service change, financial policy change, live/demo authorization or SHADOW rollout is authorized by this decision.  
**Prerequisites:** [approved Q1–Q3](2026-11-09-source-wallet-health-k-recalibration-round1.md), [Pydantic-native contracts](2026-11-09-pydantic-native-contract-ownership.md), [domain interfaces](2026-11-09-pydantic-native-domain-interfaces.md), [existing T+300 position-first policy](2026-11-08-position-first-t300.md) and [risk-budgeted fixed-k](../RISK-BUDGETED-K-SIZING-20261106.md).

## Context

The official selected-position producer for the 16-portfolio SHADOW study consumes 14 selected accounts through one native subscription session and writes first-known receipts to its existing SQLite PaperJournal. At the inspected checkpoint, its user systemd service had 24 cumulative restarts and a recorded `PAPER_JOURNAL_BUSY_OR_UNAVAILABLE` failure. The current writer maps both `flock` contention and SQLite operational failures to that code; the exact cause remains **UNKNOWN**. The independent 16-portfolio Pydantic SHADOW consumer has already gained a different BUSY retry. It cannot repair the producer. The previous ACT10 source opportunity was correctly canceled on a GAP before T+300. These are dated observations, not live guarantees.

Wallet-health Evals has only a synthetic corpus. Existing frozen `k_by_pod` values and private study selections cannot be rewritten retroactively. Guardian remains the sole protected financial authority.

## Q4 — Bounded, classified source-write recovery (APPROVED)

- Diagnose and expose the **specific source of contention** (filesystem writer lease, SQLite BUSY/LOCKED, transaction or WAL setup, verifier contention, or nonrecoverable storage error) through bounded private diagnostics before choosing an exact fix. Never treat the generic wrapper as root-cause proof.
- Retain exactly one bounded serialized journal writer and the **existing** source evidence/journal authority. Allow bounded retries **only for demonstrated transient BUSY/LOCKED conditions**, while preserving original first-local-known receive times, original raw SHA, source identity, ordering and account epochs.
- An in-memory queue is **not** durable. A frame may authorize a downstream source transition only **after the original ordered observation is committed**. If the process crashes with uncommitted frames or the queue overflows, continuity cannot be asserted. Mark a genuine GAP for affected accounts and require new baselines; never backdate first-known or convert a reconnect into a trade.
- No unbounded waits, optimistic cursor advances, deletion of committed receipts, fabricated terminal fills, journal rewrite or permissive restart. The numerical retry budget, queue capacity, commit-deadline and evidence of no omissions are **future specification**.

**Alternatives rejected:** restart for every temporary lock; unbounded backpressure; replace the existing SQLite source journal with another DB or broker for this fault.

## Q5 — Preserve one shared source socket initially, isolate account-local faults (APPROVED)

- Retain the single, budgeted Hyperliquid native subscription session for the 14 currently selected accounts **initially**.
- Separate account-local malformed frame / scope quarantine from transport-wide disconnect or ambiguous identity. A verifiably account-specific invalid frame must not discard healthy independent account state; a genuine shared disconnect fences the affected shared socket members' prospective continuity.
- Maintain account-local epochs, source-book integrity and portfolio dependency fanout. No backfilled source frames as actual continuous prospective knowledge.
- Split into multiple connection groups **only after** measurements show a shared-transport problem that outweighs socket/IP/resource budget and operational cost. The option remains open, not a deployed change.

**Alternatives rejected:** one socket per wallet without evidence; ignore shared transport GAPs.

## Q6 — Full-registry monitored universe, separate from official signal collection (APPROVED)

- Monitor the private SQLite **registered** wallet universe using read-only, deduplicated, rate-budgeted evidence checks. Begin with **daily** broader status evaluation and use more frequent read-only assessments for selected paper accounts *where original official receipts are already available*.
- Preserve exact account identity, provider coverage, PIT known-at, freshness, source scope and request/response integrity; unknown/missing evidence is not zero activity or a withdrawal.
- The initial 14-account official position-first source observer is **not** expanded to the entire wallet registry simply to perform health evaluation. Historical Vike/HyperX or other read-only vendor data do not become official complete live selected-account position books.
- Schedule/worker implementation, rate quotas and freshness thresholds remain future interface decisions.

**Alternatives rejected:** monitor 14 alone; create one continuous WS subscription per research wallet as a default.

## Q7 — Scoped capital evidence and explicit flow attribution (APPROVED)

- Apply the existing `$1,000` wallet-capital eligibility floor only to an **explicitly defined, verified, time-aligned source-account equity measure** with known account/DEX scope. Do not silently add unrelated DEX margin sums, spot, vault or parent/child NAV; lack of leader whole-wallet NAV alone must not become a fixed-k mathematical sizing gate.
- Model deposits, withdrawals, realized and unrealized changes, trading losses, funding, fees, liquidation and unexplained residuals as distinct, PIT-observed financial-attribution facts. An equity drop does not prove trading loss.
- Missing or ambiguous coverage yields `EQUITY_UNVERIFIED` / `INSUFFICIENT_EVIDENCE`, **not** `BELOW_FLOOR`, `LIQUIDATED`, `EDGE_DECAY_CONFIRMED`, or an automatic exclusion.
- The future decision on which verified status temporarily suspends new shadow entries is **not** settled by adopting this evidence policy.

**Alternatives rejected:** require whole-wallet NAV for all fixed-k decisions; infer investment performance or liquidation from an equity-difference sign.

## Q8 — Multi-horizon, causally cost-adjusted follower edge monitoring (APPROVED)

- Use predeclared evidence windows with **7-day warning**, **30-day persistence check**, and **90-day historical context when available**. A favorable or unfavorable 7-day period alone is not a final edge verdict.
- Primary economic claim is the **modeled/observed follower's** T+300 net performance with fees, slippage, market capacity/uncertainty, cash/MTM and the existing PM03/PM04 risk model; never treat the source wallet's nominal PnL as follower performance.
- Preserve PIT known-at ordering, train/forward splits, independently observable episodes/active days and effective sample size. A retrospective fill reconstruction may provide a labeled screen, not counterfeit prospective first-known evidence.
- Require sufficient evidence for positive `EDGE_DECAY_CONFIRMED` and for k-increase proposals; if not, return `INSUFFICIENT_EVIDENCE` or a bounded warning rather than positive qualification. Specific sample thresholds, tests and confidence standards remain the Q12 frontier.

**Alternatives rejected:** raw source equity or PnL thresholds; single 7-day swing interpreted as durable alpha deterioration; impossible 90-day prospective requirements that suppress all descriptive monitoring.

## Q9 — Research proposals never auto-activate revised k (APPROVED)

- A deterministic sizing evaluator may propose `HOLD`, `DECREASE` or `INCREASE` for a **specific portfolio version + pod + evaluation-as-of**, with its immutable evidence/policy/algorithm refs.
- Pydantic validates versioned proposals and future release contracts, but **neither model validation nor orchestration authorizes financial changes**. Activation requires a separate explicit, versioned portfolio release under its owning governance contract.
- Do not rewrite historical k, original signed paper profiles, released portfolio membership, past modeled accounting, running journal identity or protected Guardian pins.
- Deterministic proposal generation can be automatic. **Automatic deployed k increases are not approved.** Whether a shadow-only risk reduction can become automatically effective, and what happens to held exposure and a pending T+300 opportunity at a release boundary, are explicitly **deferred to Q13**.
- `FIXED_K_NATIVE_QUANTITY`, NAV optionality, per-pod risk budgets, unresolved exposures, immediate protective exits, daily/trailing restrictions and Guardian isolation remain unchanged.

**Alternatives rejected:** a global per-wallet k mutable in place, silent cross-portfolio k propagation, immediate rewriting of live paper targets upon a fresh research estimate.

## Mandatory Pydantic-native implementation boundary (already binding)

- Reuse existing **strict/frozen/versioned Pydantic v2 domain contracts**, one deterministic reducer per consequential lifecycle, the existing PaperJournal/SQLite registry/release paths, and PM03/PM04 simulated finance. No duplicate `WalletState`, generalized event broker or second financial store.
- New wallet-health, money-flow and k-proposal facts/results must be typed and auditable, with explicit source IDs, known-at and raw-receipt provenance. An AI agent, an orchestration flow, and a successful validation **cannot grant financial authority**.
- Keep Polars/DuckDB/Parquet batch computations. Preserve exact Decimal/lot-based financial semantics at final sizing gates; do not create one Pydantic model per OHLCV or fill row.
- If an external scheduler is later adopted, it owns only retrying/scheduling **read-only research flows** and creating append-only **proposals**. It never owns official source continuity, T+300 timers, PM03 cash/inventory, immutable source SHA or Guardian financial admission.

## Consequences and next frontier

- Source reliability engineering can proceed independently of read-only health research, but an active wallet-health score cannot claim source continuity if its receipts do not support it.
- **Subsequent status:** Q10–Q15 were owner-approved in the [Round 3 ADR](2026-11-09-source-wallet-health-k-recalibration-round3.md), including conditional Prefect adoption for bounded research scheduling and no Temporal/source-loop rewrite. The **only current ready decision is Q16**: end-to-end acceptance and staged release boundaries.
- See the [design grill](../SOURCE-WALLET-HEALTH-K-GRILL-20261109.md). No implementation, commit, merge, deployment or financial policy mutation follows from these design approvals.
