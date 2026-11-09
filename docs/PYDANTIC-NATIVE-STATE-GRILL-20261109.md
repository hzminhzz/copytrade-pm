# Pydantic-native redesign — 28 implicit state-machine disposition ledger

**Date:** 2026-11-09
**Status:** Q3–Q39 ARCHITECTURE GRILL CLOSED; 28/28 ACCEPTANCE OBLIGATIONS DESIGNED; 0/28 ENGINEERING DISPOSITIONS VERIFIED. NO IMPLEMENTATION AUTHORIZED.
**Source baseline:** November 9 audit at `76e587b`; re-inspected high-value code on `175d54d`. These are **audit candidates, not 28 proved defects**. The owner approved the architectural resolution strategy, not any claim of completed fixes or tests.
**Binding guardrails:** [Q3/Q4 ADR](decisions/2026-11-09-pydantic-native-migration-guardrails.md), [Q5–Q8 domain contract/ownership ADR](decisions/2026-11-09-pydantic-native-contract-ownership.md), [Q9–Q13 state-semantics ADR](decisions/2026-11-09-pydantic-native-state-semantics.md), [Q14–Q18 recovery/compatibility ADR](decisions/2026-11-09-pydantic-native-recovery-and-compatibility.md), [Q19–Q24 validation/runtime ADR](decisions/2026-11-09-pydantic-native-validation-runtime.md), [Q25–Q29 sequencing/ecosystem ADR](decisions/2026-11-09-pydantic-native-sequencing-ecosystem.md), [Q30–Q34 domain interfaces ADR](decisions/2026-11-09-pydantic-native-domain-interfaces.md), [Q35–Q39 failure/readiness ADR](decisions/2026-11-09-pydantic-native-failure-and-spec-readiness.md), [V4 authority and T+300 ADR](decisions/2026-11-08-position-first-t300.md). Glossary: [CONTEXT.md](../CONTEXT.md).

## Approved foundation (Q3–Q8)

- Q3: Versioned internal redesign while preserving raw historical evidence, first-known T+300, financial limits and Guardian authority.
- Q4: Autonomous incremental replacement in isolated worktrees, focused tests and reversible deployment only within separately authorized scope.
- Q5: Pydantic-first public/domain contracts, **not** mandatory `BaseModel` for every internal object.
- Q6: Explicit typed events and deterministic transition owner per consequential lifecycle; Graph optional for justified orchestration, not a universal replacement for proven financial reducers.
- Q7: Domain-owned, versioned payload contracts across connector/copytrade/Guardian; no global shared package or duplicated finance authority.
- Q8: Retire redundant, proved-unreachable legacy paths rather than automatically port every old implementation.

**Approved Q9–Q13:** (Q9) source economic-state equality distinct from immutable raw SHA identity; (Q10) financial HALT latched separately from readiness; (Q11) desired source, pending intent, modeled attempt, actual holdings and unresolved exposure are separate; (Q12) atomic publish + durable cursor + idempotent at-least-once consumption, not unproven exactly-once; (Q13) wallet eligibility, source continuity, market validity, financial risk, worker health and scientific qualification are independent facts.

**Approved Q14–Q18:** (Q14) fail-closed restart and replay with proven continuity required to resume pending new-risk; (Q15) selected-account scope generations and targeted fencing; (Q16) validated risk-reducing actions under HALT with unresolved effects retained; (Q17) domain-owned versioned schemas with existing Guardian compatibility manifest; (Q18) risk-weighted proof and exact disposition for every family.

**Approved Q19–Q24:** (Q19) strict domain validation with explicit exact Decimal provider conversion; (Q20) typed VALID/INVALID/INCOMPLETE/STALE/UNSUPPORTED_VERSION/TEMPORARILY_UNAVAILABLE outcomes, never authority; (Q21) derived model serialization cannot replace immutable historic raw bytes/SHAs; (Q22) pure reducer + existing atomic journal authority + separate effect dispatch; (Q23) minimal Pydantic core with optional isolated ecosystem packages and measured performance; (Q24) evidence-based adoption of Settings/Graph/Evals/AI/Monty/Logfire only when useful.

**Approved Q25–Q29:** (Q25) start with full official-position to durable receipt vertical slice, independently expedite verified HALT risk defect; (Q26) old/new replay parity for unchanged semantics plus independent corrected-bug oracles and intentional-difference receipt; (Q27) bounded source/SHADOW canary before separately approved 16-portfolio cutover, no broker authorization; (Q28) offline wallet-monitoring Pydantic Evals as first optional experiment; (Q29) Grafana remains operator UI, optional strictly sanitized telemetry.

**Approved Q30–Q34:** (Q30) immutable source evidence references versus canonical position projection; (Q31) retain versioned stream/intent/effect ID lineage and replay idempotence; (Q32) selected perp book completeness separate from whole-wallet finance and observer vs account generation; (Q33) independent observer/opportunity/PM03-04/Guardian/eligibility-science-readiness aggregate owners; (Q34) independently labeled PIT-correct read-only agent Evals with justified abstention and deterministic baseline.

**Approved Q35–Q39:** (Q35) quarantine continuity-critical malformed source frames and fence only affected prospective new risk; (Q36) independent producer, portfolio and protected consumer cursors with locally atomic effect identities; (Q37) 13 risk-weighted combined-fault acceptance cases; (Q38) event-driven forward SHADOW canary with honest exit-coverage status; (Q39) design-to-spec readiness rules, with read-only S0 factual checks. **Q3–Q39 frontier closed; no unresolved owner policy decision.** See [binding final ADR](decisions/2026-11-09-pydantic-native-failure-and-spec-readiness.md), [13-case matrix](PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md), [28-case matrix](PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md), [roadmap](PYDANTIC-NATIVE-MIGRATION-ROADMAP-20261109.md) and [closure review](PYDANTIC-NATIVE-DESIGN-CLOSURE-20261109.md). All engineering dispositions remain pending actual code/test evidence.

## End-state closure rule for every family

Document (1) the one responsible authority and source of truth; (2) typed valid state, legal events/transitions, and deliberately retained combinations; (3) invalid transitions and fail-closed response; (4) restart/cursor/transaction behavior and evidence clocks, where applicable; (5) tests through the actual interface for risky paths; (6) an explicit final disposition: **FIXED / EXPLICIT-AND-VERIFIED / RETIRED-NOT-REACHABLE / DOCUMENTED-INTENTIONAL**. An unresolved risky finding is not closed by adding an enum or Pydantic model. Retiring an implementation requires proving no active callers/OS release dependence. Scientific qualification and actual deployment remain separate.

## Candidate inventory (provisional, not owner-approved resolution)

| Audit ID | Domain lifecycle / source examples | Initial direction to pressure-test | Evidence / risk to close |
|---|---|---|---|
| 01 | Complete selected-position observation: `pm_forward_source_stream`, `pm_e4_prospective` | **FIX + DEEPEN** | Numeric equality (`20` vs `20.0`), DEX scope/census changes, baseline vs transition, replay clocks |
| 02 | PM-03 risk tier and durable HALT: `pm03_account`, `pm03_risk`, `pm03_execution`, `pm_forward_journal` | **FIX + CENTRALIZE** | Never downgrade HALT due to missing quotes/funding; preserve real risk-reducing permission |
| 03 | V4 routed targets and terminal position reconciliation: `pm_forward_observed_paper`, `pm_forward_single_shot` | **FIX** | Retire stale routed targets and avoid requiring dead instrument marks after verified flat |
| 04 | Signed source spool and cursor: `v4_source_spool`, `v4_source_export` | **FIX PUBLICATION** | Partial packet visibility, abandoned staging, file + directory fsync, recovery/retry safety |
| 05 | Broker cancel/fill/reconcile: `pm04_broker`, `pm04_shadow` | **EXPLICIT-AND-VERIFY** | Keep canceled pending reservations until post-cancel broker snapshots |
| 06 | Observer scope, worker generation and census: `pm_forward_continuous`, `pm_forward_source_stream` | **DEEPEN** | Installed scope generation vs unchanged membership; held-market retention |
| 07 | Transport connect/subscription/reconnect/shutdown: `pm_forward_continuous_transport`, `pm_forward_observer`, `pm_e4_stream` | **EXPLICIT-AND-VERIFY** | Disconnected epochs cannot admit post-gap entries |
| 08 | CCXT market stream continuity/quarantine: `pm_forward_ccxt_market`, `pm_forward_ccxt_trades` | **RETAIN-OR-RETIRE** | Confirm current consumers before replacement; no silent fallback in V4 |
| 09 | Native public-trade continuity: `pm_forward_public_trades`, `pm_forward_stream_journal` | **DEEPEN/VERIFY** | Gap/retrospective receipts never become prospective signal proof |
| 10 | Vike selected-fill gap/cursor: `pm_vike_selected_fills`, `pm_vike_stream_canary` | **FIX** | Older gap marker remains sticky even with monotonic later cursor |
| 11 | Serialized writer and cancellation: `pm_forward_continuous_transport` | **VERIFY** | Commit-before-publish, cancellation and shutdown without orphaned task |
| 12 | UTC bucket seal/correction: `pm_forward_public_trades`, `pm_forward_batch` | **EXPLICIT-AND-VERIFY** | Partial, late corrections and immutable sealed bucket semantics |
| 13 | Grafana publication/recovery: `ops/grafana-phase1/production.sh`, `compose.yaml` | **FIX HEALTH CONTRACT** | Start reports health when projection/publisher not progressing |
| 14 | SQLite metadata registry release/cutover: `scripts/registry_release.py`, `pm_runtime_readonly` | **EXPLICIT-AND-VERIFY** | Pointer/metadata crash intermediate remains recoverable and fail-closed |
| 15 | Protected standby HALT and process epoch: `pm_forward_protected_ops` | **EXPLICIT-AND-VERIFY** | Watchdog restart must not clear HALT or promote standby to finance |
| 16 | Notification incident/delivery/ACK: `dashboard/notifications.py` | **DEEPEN** | Acknowledgement vs active incident vs delivery result are distinct states |
| 17 | Prospective receipt/audit/matured outcome: `pm_prospective_ledger`, `pm02_campaign` | **EXPLICIT-AND-VERIFY** | Preserve independent signature and maturation requirements |
| 18 | SQLite metadata + native file mutation: `wallet_registry_native` | **DURABILITY REVIEW** | Hard-link/fsync/transaction power-loss implications |
| 19 | Combo2 freeze vs admission: `pm_combo2` | **FIX-OR-RETIRE** | FROZEN display must agree with new-risk admission/latches |
| 20 | Legacy ForwardBatch due/reason lifecycle: `pm_forward_batch`, `pm_forward_admission` | **FIX-OR-RETIRE** | Source gap cannot leave prior DUE eligibility active; stale reasons reset |
| 21 | Historical book anchoring/trust: `pm_fill_replay`, `pm_fill_tape` | **EXPLICIT-AND-VERIFY** | No retrospective source state mistaken for prospective atomic book |
| 22 | Historical flat-to-flat episode reconstruction: `pm_historical_combos` | **EXPLICIT-AND-VERIFY** | Retrospective episodes always labeled estimates |
| 23 | Challenge stage/funded/payout: `contract_actuary` | **DOCUMENT-INTENTIONAL / VERIFY** | Ever-funded + inactive is valid; not current funding |
| 24 | Acquisition generation/file pairing: `pm_hyperx_gap_recovery`, `pm_e4_backfill` | **VERIFY** | Correct generation/hash and orphan-recovery semantics |
| 25 | Immutable cache state: `pm_offline_cache`, `pm_offline_oracle` | **EXPLICIT-AND-VERIFY** | Cache corruption never silently accepted as scientific evidence |
| 26 | Source fanout cursor/progress: `pm_forward_source_fanout` | **EXPLICIT-AND-VERIFY** | Durable receipt and per-consumer position under crash/restart |
| 27 | Old PM-02 fallback lifecycle: `pm_manager`, `pm02_audit`, `pm02_risk` | **RETAIN-OR-RETIRE** | Historical compatibility vs current campaign reducer reachability |
| 28 | CDP browser session lifecycle: `ops/lib/obscura_cdp.py` | **DOCUMENT/VERIFY** | Isolate browser session/target/connection without trading authority |

## Proposed disposition of ALL 28 families (DESIGN ONLY)

**No family is marked resolved.** These are explicit planned routes, not claims that required runtime or regression evidence exists. A discovered active dependency or real defect overrides an initial route. Each audit ID remains individually tracked in the inventory above.

| Proposed route | Audit IDs | Number | Required finish |
|---|---|---:|---|
| **FIX** already reproduced or high-confidence defect | 01, 02, 03, 04, 10, 13 | 6 | Reproduce on the target revision; change behavior; add boundary regression and restart/causal checks as applicable |
| **DEEPEN** distributed lifecycle ownership | 06, 09, 16 | 3 | Concentrate transition authority; prove legal and invalid transitions through interfaces |
| **EXPLICIT-AND-VERIFY** or fix if tests expose a defect | 05, 07, 11, 12, 14, 15, 17, 18, 21, 22, 24, 25, 26, 28 | 14 | Formalize semantics, model concurrency/failure evidence, verify actual consumers and invariants |
| **CONDITIONAL RETIRE** or fix if still required | 08, 19, 20, 27 | 4 | Prove absence of installed/research consumers and preserve necessary historical interfaces, otherwise fix and verify |
| **DOCUMENTED-INTENTIONAL**, subject to behavioral verification | 23 | 1 | Prove `ever_funded` and `currently_active` are distinct, documented predicates |

**28/28 assigned; 0/28 closed.** The old 5 HIGH / 18 MEDIUM / 5 LOW risk ranking is not an assertion that 5 currently deployed incidents are unresolved; independently inspect current releases before runtime claims.

**Approved Q18 evidence policy:** Risk-sensitive families require adversarial replay/crash/restart/fault tests; persistence and inter-repository families require atomicity and compatibility tests; nonfinancial/legacy families receive proportionate behavior or reachability evidence. Do not require a new Pydantic class where a verified reducer or safe retirement resolves a family.

## Pressure-test dependencies

- **F0 (SETTLED Q5–Q8):** Pydantic-first contract coverage, typed event/reducer default, domain-owned versioned exchange schemas, and legacy retirement backed by reachability evidence.
- **F1 (Q9–Q18 SETTLED):** Source observation and publication (01,04,06–12,24,26); financial authority and stops (02,03,05,15,19,20); independent registry governance (14,17,18,21–23,27); operator workflows (13,16,28).
- **F2 (Q14–Q24 SETTLED):** Crash/restart, account scope, protective exits, pinned schema evolution, strict typed validation, immutable serialization, pure reducers, committed effects, and optional ecosystem ownership are approved as semantic constraints.

## Approved Round 4 — Q14–Q18

Authoritative [Q14–Q18 recovery/compatibility ADR](decisions/2026-11-09-pydantic-native-recovery-and-compatibility.md). The accepted policies are fail-closed restart, targeted scope fencing, independently constrained protective reduction, existing Guardian schema-pin authority, and risk-weighted closure evidence. This approval does **not** close or fix any of the 28 audited families.

## Approved Round 5 — Q19–Q24

Authoritative [validation and runtime ADR](decisions/2026-11-09-pydantic-native-validation-runtime.md). Pydantic is the domain-contract layer, not a new source journal, financial authority, or forced representation for all research records.

## Approved Round 6 — Q25–Q29

Authoritative [sequencing and ecosystem ADR](decisions/2026-11-09-pydantic-native-sequencing-ecosystem.md). Full source state vertical slices, independent safety fixes, intentionally corrected replay oracles, limited SHADOW canary, offline Pydantic Evals and Grafana privacy are approved design choices only.

## Approved Round 7 — Q30–Q34

Binding [Q30–Q34 domain interfaces ADR](decisions/2026-11-09-pydantic-native-domain-interfaces.md), original [interface grill with alternatives](PYDANTIC-NATIVE-INTERFACE-GRILL-20261109.md). Preserve source raw evidence independently of canonical economic state; keep existing cursor/effect lineage; distinguish selected perp completeness from whole-wallet finance; and do not replace PM03/04 or Guardian authority.

**Code-backed prerequisite:** Hyperliquid documents `marginSummary` in each `ClearinghouseState` schema, but actual native frame encoding and completeness assumptions must be verified against authentic original bytes in S0. See the ADR for provider source. Do not infer mandatory leader NAV for fixed-k.

## Approved Round 8 — Q35–Q39; architecture decision frontier closed

[Binding final ADR](decisions/2026-11-09-pydantic-native-failure-and-spec-readiness.md) approves selective source quarantine, per-authority cursor/effect transactions, the [13 combined-fault tests](PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md), bounded event-driven SHADOW evidence, and a concrete engineering-specification readiness rule. [Historical alternatives](PYDANTIC-NATIVE-FAILURE-GRILL-20261109.md) remain for rationale, not unresolved decisions.

**F3 — next activity is specification synthesis, not another design grill.** All 28 families have accepted **test-design obligations** and assigned prospective work stages; **0/28 engineering closures**. The spec must include the actual S0 source-format check, V4 versus legacy paper effect transaction proof, real installed compatibility pins, performance baselines and release/rollback details. No code, merge, deployment or broker action is authorized by these documents.

No blanket adoption of Pydantic Graph is authorized. Do not introduce a second registry, financial ledger or protected broker authority.
