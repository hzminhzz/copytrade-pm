# Pydantic-native Round 8 — final-failure and specification-readiness decisions

**Date:** 2026-11-09
**Status:** Q35–Q39 **APPROVED FOR ARCHITECTURAL DESIGN**. Historical question/alternative record; the binding decision is [the Q35–Q39 ADR](decisions/2026-11-09-pydantic-native-failure-and-spec-readiness.md). No implementation or Git action.
**Prerequisites:** Q3–Q34 design approved; [domain interface ADR](decisions/2026-11-09-pydantic-native-domain-interfaces.md). [13-case combined-fault matrix](PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md) and [all-28 acceptance matrix](PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md) remain designed, not run.

## Architectural goal

Failure must not be silently demoted to a benign schema-validation exception or escalated into a false financial HALT. Source, paper, finance, durable publications, private registries, and protected Guardian have independent authority. The design must keep **maximum autonomous engineering speed** with a bounded set of non-negotiable safety assertions.

## Q35 — What does a malformed source record do to prospective continuity?

**A: reject only the individual frame and continue using the old baseline.** Fast, but dangerous: a malformed official complete replacement may conceal a real position change during the exact T+300 admission window.

**B (RECOMMENDED): risk-classify by whether the actual source continuity proof survives.**
- A malformed *required* selected-account official position, wrong identity/DEX, incomplete census, impossible/native-clock conflict, or untrusted replacement semantic invalidates that affected account's prospective continuity. Persist/reconstruct an explicit GAP/QUARANTINED source epoch through the owning journal. Fence its pending **new-risk** intents. Preserve last-known holdings, original raw evidence, committed first-known clocks and all financial latches; never invent flat.
- A noncritical diagnostic field known to be optional may be preserved as raw metadata and may yield a typed diagnostic without invalidating otherwise complete economic position proof. This exemption must be documented and tested, not assumed.
- A malformed **optional Vike fill, public-trade correction or research feed** quarantines *that feed* and must not automatically destroy an independently complete official position stream.
- If the affected account cannot be identified from the transport context, fence the ambiguous subscribed identities, not unrelated streams; a shared transport integrity failure may warrant wider fence. Publisher/replay journal divergence stops the affected writer/stream, not just skips one event.
- Recovery needs a new complete official baseline, then a genuine later transition; no retroactive T0. Financial HALT remains an independent owner and cannot be cleared by source repair.
- Include a bounded quarantine/error budget preventing a malformed-frame flood from cycling reconnects indefinitely; preserve diagnostic evidence safely.

**Counterexample:** T0=10:00 new leader position, malformed complete replacement frame at 10:04, valid same-size frame at 10:06. The system must **not** execute a delayed 10:05 entry from the old T0. A malformed ancillary fill event in a distinct feed cannot by itself cancel a healthy official source opportunity.

## Q36 — Where are the transaction and consumer-cursor ownership boundaries?

**A: one cross-database/global cursor advanced once any destination reads source.** Simpler nominally, but loses deliveries to slow/crashed portfolios and invents exactly-once atomicity.

**B (RECOMMENDED): commit locally per authority; use independent receipt/effect cursors.**
- Canonical source `PaperJournal` atomically commits original receipt + stream checkpoint with existing source stream ID/epoch/sequence/hash.
- Signed spool publishes fully durable file before its own cursor advances; packet at-least-once and deduplicated by the consumer.
- Each portfolio journal imports the verified source receipt as evidence only, maintaining its **own** source prefix/cursor. A partial fanout is acceptable if reported truthfully, recovered per target and never treated as all-consumer success.
- The owning follower paper finance transaction commits its per-run consumed source cursor **with** the simulated financial effect under existing account authority when that effect path requires source consumption; no new cross-DB transaction or shared wallet inventory. Audit the different existing `consume_source_effect()` v1 path vs V4 `ObservedPaper` `run.record()` path and establish equivalent idempotency guarantees rather than assuming they are the same.
- Stable effect IDs are derived from already committed source event + destination portfolio/run/pod + decision/rule revision. A duplicate source packet may be reread, but neither a second financial effect nor a second first-known timestamp may result. Conflicting same-ID content blocks recovery pending investigation.
- Guardian only consumes independently pinned signed versioned contracts and owns its own protected journal and financial permits; it cannot inherit portfolio SQLite cursors as trust.

**Counterexample:** Source packet P arrives, Portfolio A imports and models one effect, Portfolio B loses power before importing. Source producer continues to P+1. On restore B must catch up P, while A must **not** replay its financial mutation. Guardian sees no extra permit.

## Q37 — How aggressive should combined-failure acceptance be?

**A: test all theoretical Cartesian products of 28 state families before any engineering cutover.** Excessive and creates unclear coverage standards.

**B (RECOMMENDED): risk-weighted deterministic multi-fault coverage.**
- Design at least the **13 targeted combined-fault cases CF01–CF13** in the [matrix](PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md), covering at least one interaction involving every audit family.
- To accept the *first* source/finance SHADOW canary, require relevant critical combinations (malformed frame+due timer; HALT+stale quote+restart; cancelled/partial fill; signed publication crash; one source shared by two papers; signed release/Guardian HALT). Other cases become mandatory when the corresponding S3–S5 stage is implemented/closed.
- Use actual transaction/dispatch interfaces with deterministic clock/fault scheduling, not mocks that bypass each owning reducer. Simulated faults must not claim independent prospective provider truth.
- Fail the affected engineering gate for any causal T0 misclassification, HALT downgrade, double modeled financial effect, false flat, cursor skip, early/late unauthorized new entry or spoofed protected permit.
- Do not require broad scientifically irrelevant soak or exhaustive matrix permutations as a blocker for a focused read-only source fix.

**Counterexample:** a green set of 28 independent unit tests does not prove source+finance recovery safe when 10:05 is both entry due and a reconnect gap; this requires an orchestrated multi-fault case.

## Q38 — What is the minimum honest SHADOW canary pass?

**A: instant 16-portfolio replacement after local tests** vs **C: fixed multiweek soak for all streams and exits**.

**B (RECOMMENDED): event-driven canary with distinct coverage classes.**
- **Engineering preflight**: current deployed/source SHA, selected-account/DEX scope and trust pins verified, all critical local red/green and combined-fault tests passing, isolated source+journal, rollback without journal rewind, no broker transport.
- **Authentic forward proof**: record at least one complete official **post-baseline selected position transition**, its genuine first-local T0, one non-resetting due decision precisely at T0+300 according to the defined scheduling/admission policy (FILLED *or* explicitly BLOCKED, never invented), an authenticated quote/economic evidence receipt, and durable restart/replay verification. Synthetic tests alone cannot be labeled forward proof.
- **Protective reduction proof**: deterministic adversarial test for both valid reduction and blocked/unresolved safety behavior is mandatory before cutover; capture genuine source reduction/exit when naturally observed, and declare real-exit coverage **UNKNOWN** until it occurs. A true source reduction is not required on an arbitrary calendar deadline, but must be collected to claim fully observed end-to-end real exits.
- **Promotion semantics**: do not declare **fully accepted forward-risk lifecycle** without genuine exit coverage. Additional **read-only collection** may expand while exit coverage is unknown; promoting to all paper follower finance requires owner-approved exact scope and an explicit evidence receipt of remaining uncertainty. There is no automatic funded/demo/live admission.
- Use bounded evidence per selected portfolio and independent held inventory; a single account's proof does not certify every portfolio's unique economic risk limits.
- Do not equate a T+300 **due decision** with a guaranteed simulated execution at the wrong time. Market inadequacy must yield a transparent BLOCKED/EXPIRED outcome consistent with exact policy.

**Counterexample:** no leader closes during the canary window. The canary may verify first-known entry and restart, but must report **FORWARD_EXIT_NOT_YET_OBSERVED** rather than backfilling a synthetic close or running indefinitely.

## Q39 — What constitutes 'implementation-ready specification'?

**A: write a single ambitious ticket after Q35–Q38 approval** vs **C: insist all 28 defects are already fixed before specification**.

**B (RECOMMENDED): design closed, proof obligations explicit, execution still separately authorized.**
- All Q3–Q38 approved design decisions, plus documented source envelope and provider schema truth-vs-actual-frame unknown as an explicit read-only S0 acceptance task (not a reason to invent compatibility).
- Versioned typed public contracts and transition-owner/transaction-ID algebra with reference to existing journal/SHA/PM03/04 and Guardian. No global Pydantic wrapper or second authority.
- 28/28 proposed route, owning module, evidence test, user-visible semantic difference and migration stage; 13 combined-fault cases with stage placement; explicit rollback and review boundaries.
- Fast S0–S5 dependency graph and small vertical slices with autonomous ordinary blocker recovery, test/baseline/fault acceptance; check current GitHub/installed runtime when **execution** starts, rather than assuming historic state is current.
- Mark whether a stage is IMPLEMENTED, ENGINEERING VERIFIED, MERGED, DEPLOYED, FORWARD OBSERVED, SCIENTIFICALLY QUALIFIED, TRADING AUTHORIZED; none inferred.
- State supported historical reader/backward evidence preservation, cross-repository pinned compatibility, Grafana/privacy, Pydantic package dependency and optional Evals experiment isolation.
- Deliver spec as local **proposal only** after all decisions settled; user must explicitly authorize implementation/merge/deploy outside of this grill. Do not start actual coding merely because specification is ready.

**Counterexample:** a detailed Pydantic schema with no plan for the original hash canonicalizer, V4 paper finance path, or unknown order result is **not implementation-ready**, even if all classes are named.

## Frontier dependencies

- Q35 and Q36 each depend on accepted Q30–Q33; they can be decided independently.
- Q37 is a **test scope and method** decision independent of the exact Q35/Q36 implementation. *Precise case verdicts* must be finalized after those decisions.
- Q38 is an **evidence class/promotion standard**, based on accepted Q27/Q18; exact adverse-case witnesses are finalized after Q35/Q36/Q37.
- Q39 is a **specification readiness checklist**, not a claim that the specification is already ready. It can be approved as a rule now; actual readiness is assessed only after Q35–Q38 and the remaining factual S0 unknowns are incorporated.

Q35–Q39 were subsequently approved exactly as recommended. [The binding ADR](decisions/2026-11-09-pydantic-native-failure-and-spec-readiness.md) and [the final design closure/readiness review](PYDANTIC-NATIVE-DESIGN-CLOSURE-20261109.md) supersede the original open-frontier status. No implementation, commit, merge or deployment is authorized.
