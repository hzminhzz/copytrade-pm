# Pydantic-native architecture grill — design closure and specification-readiness review

**Date:** 2026-11-09
**Status:** **ARCHITECTURE DECISIONS CLOSED; READY TO SYNTHESIZE IMPLEMENTATION SPECIFICATION.** The implementation specification itself is **NOT YET WRITTEN OR APPROVED**. **0/28 implicit-state engineering dispositions verified**. No code, dependencies, commits, merges, deployments, funded/demo/live authorizations or scientific qualifications are implied by this record.
**Inspected Git baseline:** `copytrade-pm` `175d54dec4fcda88ccf6bea885d172646aa63e4e` and its corresponding `origin/main` at the read-only check on 2026-11-09. The local review worktree is an isolated, detached, dirty **documentation-only** worktree; installed OS/Guardian revisions were not verified as part of this design closure.

## Result: Q3–Q39 is a complete accepted design tree

- **Q3–Q39 = 37 distinct approved decisions**, covered by eight linked ADRs. Every decision in this interval is accounted for once; no design choice remains pending in the stated frontier.
- The original unselected preliminary Q1/Q2 alternatives are substantively **superseded by explicit approvals Q5 (Pydantic-first domain contract scope) and Q8 (exhaustive 28-family disposition with verified legacy retirement)**. Do not treat the initial default radio buttons as separate owner approvals.
- Q3/Q4: versioned redesign, autonomous vertical migration, immutable finance/evidence/authorization invariants.
- Q5–Q8: Pydantic-first typed domain contracts; deterministic state transition owners; independent versioned cross-repo contracts; evidence-based legacy retirement.
- Q9–Q13: economic vs raw identity, durable HALT, intent/inventory separation, at-least-once/atomic publish and independent readiness dimensions.
- Q14–Q18: fail-closed restart and selected-scope generations, bounded protective reductions, Guardian compatibility authority and risk-weighted acceptance.
- Q19–Q24: strict provider Decimal normalization, typed evidence failure, historical wire SHA preservation, pure reducers and existing journal effects, minimal core and optional ecosystem.
- Q25–Q29: first source-to-durable-receipt vertical slice, corrected-bug vs parity replay oracle, limited event-driven SHADOW canary, offline Pydantic Evals, Grafana privacy.
- Q30–Q34: small immutable source/economic contracts, stable event/intent IDs, selected-perp vs whole-wallet completeness, independent aggregate ownership and independently labeled diagnosis Evals.
- Q35–Q39: continuity-impact quarantine, per-authority local transaction/cursor, multi-fault coverage, honest authentic forward canary, implementation-specification readiness requirements.

**Binding ADR series:**
1. [Q3–Q4 migration guardrails](decisions/2026-11-09-pydantic-native-migration-guardrails.md)
2. [Q5–Q8 domain contracts](decisions/2026-11-09-pydantic-native-contract-ownership.md)
3. [Q9–Q13 state semantics](decisions/2026-11-09-pydantic-native-state-semantics.md)
4. [Q14–Q18 recovery and compatibility](decisions/2026-11-09-pydantic-native-recovery-and-compatibility.md)
5. [Q19–Q24 validation and runtime boundaries](decisions/2026-11-09-pydantic-native-validation-runtime.md)
6. [Q25–Q29 sequencing and ecosystem](decisions/2026-11-09-pydantic-native-sequencing-ecosystem.md)
7. [Q30–Q34 source-domain interfaces](decisions/2026-11-09-pydantic-native-domain-interfaces.md)
8. [Q35–Q39 failure and spec readiness](decisions/2026-11-09-pydantic-native-failure-and-spec-readiness.md)

## Exhaustive matrix reconciliation

The read-only structural audit of locally written design records found:

| Dimension | Designed | Verified documentation structure | Engineering closed |
|---|---:|---|---:|
| Decision IDs Q3–Q39 | 37 | 37 unique; none missing/duplicated | Not an engineering claim |
| Individual lifecycle audit IDs 01–28 | 28 | 28 unique; none missing/duplicated | **0/28** |
| Combined-fault IDs CF01–CF13 | 13 | 13 unique; 01–28 collectively referenced | **0/13 executed under this review** |
| Stage assignments S1–S5 | 28 | 8 + 4 + 9 + 3 + 4 = 28, no duplicates | Not yet implemented |
| Documentation cross-links | all local design files | Local relative targets rechecked as part of final documentation QA | Not code tests |

**Stage reconciliation:**
- **S0 evidence/implementation preflight:** original wire/source SHA and native shape, current Git/runtime, installed companion pins, deterministic/real T0 and timing baseline; no family closed by preflight alone.
- **S1 source/durability:** 01,04,06,07,09,10,11,26 (8). Verify economic equality and scope transitions, cancellation, source/gap, spool publication and per-consumer provenance.
- **S2 finance:** 02,03,05,15 (4). HALT monotonicity, target cleanup, unknown cancel/fill and protected-standby separation.
- **S3 research/registry:** 12,14,17,18,21,22,23,24,25 (9). Genuine provenance, generation/caches, retrospective truth and signed maturity.
- **S4 operations:** 13,16,28 (3). Health vs liveness, incident/ACK vs activity, CDP session lifecycle.
- **S5 legacy:** 08,19,20,27 (4). Prove safe unreachability or repair before retirement; preserve necessary archival consumers.

**Binding individual test design:** [28-family acceptance matrix](PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md).
**Binding multi-fault design:** [13 combined-fault cases](PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md). Critical combinations CF01/02/03/04/05/13 are required for the initial affected source/paper SHADOW canary. Other cases become mandatory with their owning stage, never silently closed just because another stage passed.

**Important distinction:** A design disposition is a planned engineering resolution, not evidence that a listed family is currently defective or fixed. The original 28 are audited *implicit lifecycle families*, not 28 confirmed production bugs.

## Actual source/contract findings and explicit S0 fact checks

| S0 fact needed | Current inspected evidence | Spec handling and risk boundary |
|---|---|---|
| **Native official all-DEX wire encoding** | Published Hyperliquid `WsAllDexsClearinghouseState.clearinghouseStates` is a TypeScript `Record<string, ClearinghouseState>`; local `pm_e4_prospective._account_state()` expects a list of `[dex,state]` pairs. Actual immutable captured wire was **not** compared in this closure. | Make a read-only real-frame shape test the **first S0 task**. Preserve the raw bytes, verify official documentation against observed wire and fail closed on unsupported format. Do not silently reinterpret provider evidence. Source: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions |
| **Margin envelope vs NAV requirement** | Official `ClearinghouseState` includes `marginSummary`, but full-wallet NAV was intentionally removed as a prerequisite for fixed-k selected-account mirroring. | Retain documented provider envelope/completeness fields unless authentic wire proves otherwise; never reintroduce leader whole-wallet NAV as a general fixed-k gate. |
| **Source event vs paper effect atomicity** | `PaperJournal.append_source_receipt()` commits stream+receipt atomically; `consume_source_effect()` commits supported source cursor+simulated effect; V4 `ObservedPaper.run.record()` is **another path**. | Demonstrate equivalent V4 idempotent effect+consumption semantics or adapt it in its authorized stage. No global cross-DB transaction. |
| **Signed spool publication** | Newly created output packet can appear under final name before complete fsync and directory sync; cursor state is another file. | Case 04/CF04 must fail on old behavior and pass after stage S1 repair, without rewriting old SHA evidence. |
| **Risk HALT overwrite** | PM03 execution and journal funding-error branches can set `risk = RED` even after an earlier HALT. | Independently expedite an actually reachable safety repair in S2 if confirmed at release; preserve HALT, protective exit and independent Guardian financial authority. |
| **Exact T+300 scheduling** | Source intent stores original T0/due time; current `_execute_pending` evaluates on callbacks/ticks and retains a grace period. Exact **attempt time** must not be assumed from the existence of `due_at`. | Record due/decision/attempt clocks and jitter in tests and genuine canary; do not claim exact-T+300 execution from a late tick or fabricated fill. |
| **Current production release/pins** | Git HEAD and source docs inspected; actual installed user/root service releases, signed trust floors and compatibility manifest were not independently established in this design session. | Read-only preflight S0, then stage-specific pinned compatibility/rollback acceptance before separately authorized deployment. |

These are **factual discovery/testing obligations**, not missing owner policy approvals. The implementation specification can require the autonomous executor to discover them before making dependent changes and use the already approved fail-closed defaults.

## Architecture outcome

**Source evidence** remains immutable/raw. **Pydantic** is the strict, versioned normalized domain contract and typed-validation error layer. **Pure reducers** own observed-account continuity and paper-opportunity transitions. **Existing SQLite journals/PM03/04** own local effect commits, follower accounting, durable HALT and unresolved inventory. **Guardian** remains protected and independently signed/version-pinned. **Grafana** remains operator display; **Pydantic Evals** is an isolated, read-only wallet-diagnosis pilot, not economic proof.

No mandate to port every internal dataclass, convert Polars bars to models, install Graph/AI/Monty/Logfire, invent another ledger, create a global WalletState or replace existing state/event ID algorithms.

## Readiness verdict

| Gate | Verdict | Exact meaning |
|---|---|---|
| **Architecture decision tree complete** | **PASS** | Q3–Q39 settled; no further conceptual grill required absent contradictory S0 evidence |
| **28 individual acceptance design complete** | **PASS** | All 28 test scenarios and planned dispositions mapped |
| **13 cross-family acceptance design complete** | **PASS** | All CF01–CF13 cases mapped to every one of the 28 IDs |
| **Staged engineering plan designed** | **PASS** | S0–S5 planned with dependency and evidence gates |
| **Ready to AUTHOR a consolidated implementation spec** | **PASS** | Can synthesize without another approval interview; factual S0 tasks are explicit |
| **Consolidated implementation-ready spec EXISTS** | **NO** | Exact module/Pydantic model versions, signatures, executable test commands/targets, thresholds, compatibility/rollback runbooks still need synthesis |
| **Engineering tests / 28 fixes complete** | **NO** | 0/28 actual closure proofs; 0/13 combined-fault tests executed in this design review |
| **Merged/deployed/forward/scientific/trading authorization** | **NO CHANGE / NOT CLAIMED** | No code, Git state or installed service changed |

## Required next deliverable — not executed here

**One consolidated implementation-ready specification** should be authored from the eight approved ADRs and both accepted acceptance matrices. Include exact V4 module interfaces, versioned Pydantic contract drafts, consumer transaction/cursor proof, source-shape S0 acquisition and fail-closed handling, semantic-difference oracle receipts, stage S0–S5 tracer slices with deterministic tests and measurements, reversibility and explicit independent deployment/Guardian authorization. Use current repo and OS facts only when the execution phase actually begins; do not force the owner to manage individual coding tickets.

No further architecture design questions remain in scope now. The current user request explicitly forbids implementing, committing, merging or deploying; those boundaries were respected.
