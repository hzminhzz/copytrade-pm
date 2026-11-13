# Pydantic-native migration roadmap and ecosystem staging

**Document role:** HISTORICAL DESIGN RECORD. For completed engineering and remaining external-evidence gates, read [the acceptance results](PYDANTIC-NATIVE-ACCEPTANCE-RESULTS-20261109.md). The [agent system plan](AGENT-SYSTEM-DESIGN.md) reuses those owners; do not restart S0–S5 from this older status. The authenticated Site/Chapter 2 contract now owns operator presentation; Grafana-only wording below records the earlier design, not current UI policy. Current optional research scheduling is documented in [Prefect orchestration](TRACK-B-PREFECT-ORCHESTRATION-20261110.md).

**Original date:** 2026-11-09
**Original status at that design cutoff:** Q3–Q39 **APPROVED DESIGN ROADMAP**, S0–S5 accepted as a planning/dependency framework; target interfaces and measurements belong in a future implementation specification. **NOT APPROVED FOR EXECUTION, COMMIT, MERGE OR DEPLOYMENT**; stages are not implemented.
**Contracts:** [Q3–Q24 design decisions](decisions/2026-11-09-pydantic-native-validation-runtime.md), [Q25–Q29 sequencing/ecosystem](decisions/2026-11-09-pydantic-native-sequencing-ecosystem.md), [Q30–Q34 domain interfaces](decisions/2026-11-09-pydantic-native-domain-interfaces.md), [Q35–Q39 final failure/readiness semantics](decisions/2026-11-09-pydantic-native-failure-and-spec-readiness.md), [28-family acceptance matrix](PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md), [13-case combined fault matrix](PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md).
**Inspected code:** `copytrade-pm` `origin/main=175d54d` on November 9. Revalidate GitHub and actual running revisions before any engineering change; installed runtime is not proven by this document.

## Goal and rejection test

Build a **Pydantic-native domain contract plane** while *deleting* duplicated state interpretation. Pydantic validates normalized economic/financial contracts and versioned typed results; pure transition reducers own legal state changes; existing SQLite/source journals own durable commits; the same PM-03/04 owns simulated follower finance and Guardian in `prop-production` remains distinct. Vike historical fills never substitute for official complete selected-account position books. User does not code; ChatGPT directly executes only when separately authorized, without delegating coding.

Reject a proposed new abstraction if it creates another source of truth, masks an unknown as valid, changes T0 timing, bypasses Guardian, or requires all Polars rows to become Python models. Prefer deep modules with narrow public interfaces over blanket class conversion.

## Suggested internal layering (interface direction, not committed signatures)

```text
Original official native message (immutable bytes + independent first receipt)
      |
 Provider adapter: explicit Decimal and UTC normalization, source scope identity
      |
 Pydantic strict semantic contract (domain-owned, versioned, no authority minting)
      |
 Pure deterministic transition owner (typed legal events and rejected transitions)
      |
 Existing PaperJournal / registry / PM-03 or PM-04 transaction authority
      |
 Durable intent/outbox or read-only projection, independent from active inventory
      |
 Protected version-pinned consumer / Guardian (separate authority)
```

- Raw source SHA and legacy journal canonicalizer are **not** replaced by `model_dump`.
- `ValidationResult` must be distinct from `AdmissionDecision` or `ExecutionPermit`; even `VALID` does not imply financial admission.
- Effect dispatch is after commit; no broker/network call within SQLite transaction.
- Existing `copytrade-pm` capabilities/CLI and archive consumers are verified before removal.
- Delivery semantics: atomic local output, committed consumer cursor and idempotency, at-least-once transport.

## Dependency-aware proposed migration stages

| Stage | Audit families and dependencies | Engineering output / acceptance | Cutover status |
|---|---|---|---|
| **S0 Evidence and interface baseline** | Prerequisite to S1–S5; no family claimed resolved | Freeze real immutable source/journal golden corpus and hashes; verify cross-repo pins, live installed releases, existing tests, source T0; characterize baseline perf; mark known wrong behavior as negative oracle | Design/test preparation; no deployment |
| **S1 Source, scope, continuity and publication** | **01,04,06,07,09,10,11,26**; S0 | Canonical official positions and independent evidence identity, scope epoch, typed stream events, one transition owner, crash-atomic spool and idempotent consumer progress; exact T+300 after verified post-baseline change; falsifying tests | Independent read-only/paper SHADOW canary after separate authorization |
| **S2 Financial risk, execution and reconciliation** | **02,03,05,15**; depends on S1 proof and existing PM-03/04 finance | Durable HALT reducer, no phantom routed target after flat, broker cancel/fill-reservation reconciliation, independent entry vs protective reduction semantics, restart-safe financial events | Paper-only; protected Guardian compatibility verified without mutating services |
| **S3 Research metadata and retention** | **12,14,17,18,21,22,23,24,25**; S0 + affected S1 contracts | Release pointer/crash safety, generation/hash-bound cache and acquisition, historical uncertainty, signed outcome maturity, challenge stage semantics and archive compatibility | No prospective/economic promotion |
| **S4 Operations and diagnostic projections** | **13,16,28**; usable S1/2 statuses | Grafana health vs liveness, notification activity/ACK/delivery separation, browser session fault recovery; fixture evidence labeled synthetic | Grafana remains existing operator presentation |
| **S5 Legacy reachability and removal** | **08,19,20,27**; verified current/new consumers and exact installed units | Prove and retire redundant CCXT/Combo2/ForwardBatch/PM02 paths, or preserve with explicit deterministic lifecycle tests; archived studies still reproducible | Removing live units still requires separately approved release/rollback |

Families sum to **8+4+9+3+4=28**. This is a planning assignment only; a found caller or a critical failure can reclassify scope/stage. Cross-repository consumer contract checks accompany each stage involving exchange data, source events or protected financial status, not one final big-bang re-pin.

### Delivery style

Use one autonomous top-level objective and small coherent vertical integration slices in isolated worktrees; the user is not a ticket dispatcher. Each slice should delete bypass paths and add adversarial replay tests. A single large perpetual compatibility shim is undesirable. Maintain a short manifest of expected semantic changes so intentional bug fixes need not exactly match old defective output.

**Potential S1 order:** 01 source equality and scope -> 07/06 continuity -> 04/11 durability -> 26 fanout -> 09/10 optional market/fill evidence, with independent S2 HALT regression prepared early. This ordering is advisory; live runtime evidence may prioritize independent safety fixes.

### Distinguish these gates

- **IMPLEMENTED:** typed classes/events/reducers and necessary callers migrated.
- **ENGINEERING VERIFIED:** relevant risk-weighted tests and negative cases passed at exact commit, with receipt/hash evidence, clock/restart recovery and backward-wire reading as applicable.
- **MERGED:** reviewed source on configured branch, with all unowned dirty code preserved and cross-repository compatibility pinned as needed.
- **DEPLOYED:** owner-approved exact installed release and verified running service with rollback available.
- **FORWARD OBSERVED:** genuine prospective after-baseline source transition and modeled T+300/exit outcome from actual feeds; not a synthetic test.
- **SCIENTIFICALLY QUALIFIED:** independent prospective executable follower economics; separate from all above.
- **TRADING AUTHORIZED:** separate Guardian and venue credentials/account permits with explicit owner permission.

No stage may silently promote one status into another.

## Approved sequencing/ecosystem decisions (Q25–Q29)

The owner approved the source-first *vertical slice*, expedited independent confirmed HALT repairs, the two differential/invariant replay oracles with explicit semantic-diff receipts, a limited authentic source/SHADOW canary before all sixteen paper portfolios, offline wallet-monitoring Pydantic Evals as the first optional experiment, and continued Grafana-only operator display with sanitized optional telemetry. Details are binding for future specification under the [Q25–Q29 ADR](decisions/2026-11-09-pydantic-native-sequencing-ecosystem.md). No deployment, package installation or full stage execution is approved by this choice.

**Approved Q30–Q34** settle source evidence vs canonical contract, provenance-bound event and effect identity, separate selected-perp vs whole-wallet completeness, independent observer/paper/finance/Guardian reducers, and offline Evals evidence quality. See [domain interfaces ADR](decisions/2026-11-09-pydantic-native-domain-interfaces.md).

**Approved Q35–Q39** settle continuity-sensitive source quarantine, per-consumer cursor/financial effect transactions, risk-weighted combined-fault testing, evidence-classed SHADOW canary and implementation-specification readiness. See [binding Q35–Q39 ADR](decisions/2026-11-09-pydantic-native-failure-and-spec-readiness.md), [historical alternatives](PYDANTIC-NATIVE-FAILURE-GRILL-20261109.md), and [combined-fault matrix](PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md). No owner policy question remains open in this Q3–Q39 decision tree.

## Approved ecosystem staging guidance (no package installation)

| Component | Potential workload | Gate to ADOPT vs EXPERIMENT vs DEFER |
|---|---|---|
| **Pydantic Validation** | Versioned source, paper, risk and schema-edge contracts | **ADOPT in approved implementation** after S0 baseline and S1 test proof. Core pinned version. |
| **Pydantic Settings** | Consolidate fragmented configuration and env loading | **EXPERIMENT** only if actual duplication/secret-handling friction demonstrated; no secret serialization/logging. |
| **Pydantic Evals** | Score wallet-monitoring agent explanations, eligibility/edge-decay diagnostics, abstentions and tool trajectories | **EXPERIMENT** with an offline human-labeled corpus. Not follower PnL qualification or Guardian permit. |
| **Pydantic Graph** | Multi-step research/agent orchestration | **DEFER** unless it outperforms small reducers and existing scheduling; durable progress still journal-owned. |
| **Pydantic AI** | Read-only investigation of why wallets lose equity or edge | **EXPERIMENT LATER** with bounded tools and explicit non-authoritative recommendations. |
| **Monty** | Execute *untrusted model-authored snippets* with explicit host capabilities | **DEFER**. Restricted Python subset, third-party import limitations, and mounted filesystem/host functions require an independent security evaluation. Not equivalent to full Polars/DuckDB worker. |
| **Logfire** | Optional trace instrumentation via OpenTelemetry | **DEFER/EXPERIMENT** if current Grafana diagnostics show an attributable gap; keep owner Grafana and privacy controls. |
| **Prefect (not Pydantic stack)** | Scheduled daily equity/activity/edge-decay collection and retries | Evaluate separately as orchestration only; never as registry, state machine, finance, authority or source of truth. |

## First fast-fail experiments (after separately authorized implementation)

- **Semantic equality:** `"20"` / `"20.0"`, unchanged raw SHA semantics vs economic equality, market scope changes.
- **Durability crash points:** final file visibility, fsync, cursor advance, consumer commit and restart replay.
- **Safety:** HALT then stale quote/funding; unknown cancel then partial fill; unresolved exits.
- **Causality:** real first-known T0 plus 300 seconds, mid-delay updates, reconnect across due, no second entry.
- **Performance:** baseline end-to-end source observer latency/CPU/RSS and journal throughput before/after, with no loss of deadline or shared-IP budget.

Only real measured regressions warrant optimization or changed dependency strategy. This document does not assert any tests already passed.

## Original design completeness at the November 9 cutoff

The companion [individual matrix](PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md) lists one concrete acceptance scenario for each **01–28** and the [combined matrix](PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md) lists **13** multi-fault scenarios referencing every audit ID; both are approved **test designs**, not execution evidence. **At this original design cutoff: 0/28 engineering dispositions closed**; subsequent implementation evidence is in the acceptance results linked above. The Q3–Q39 design frontier is complete. [Design closure/readiness assessment](PYDANTIC-NATIVE-DESIGN-CLOSURE-20261109.md) identifies what must be specified and verified at S0 before engineering promotion.
