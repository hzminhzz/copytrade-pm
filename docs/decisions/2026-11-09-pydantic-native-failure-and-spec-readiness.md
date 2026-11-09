# ADR — Continuity quarantine, per-consumer effects, combined-fault proof and specification readiness

**Date:** 2026-11-09
**Status:** Q35–Q39 **APPROVED FOR ARCHITECTURAL DESIGN**. This decision does **not** authorize implementation, dependency changes, journal migration, commit, merge, release installation, SHADOW cutover, or actual broker trading.

## Context

The Q3–Q34 Pydantic-native decisions established immutable evidence references, exact Decimal canonical positions, strict typed contracts, deterministic source and paper reducers, existing PM-03/04 paper finance, protected Guardian authority, event identity, independent selected-perp completeness and a source-first reversible migration. The November 9 implicit-state audit contains 28 lifecycle families. The repository already atomically commits source receipts with their stream checkpoint and can commit supported per-run source-cursor+simulated effects, but the V4 ObservedPaper route and separate portfolio fanout have distinct semantics. A Pydantic parser exception alone cannot prove continuity was preserved.

Relevant inspected code at `175d54d`: `pm_forward_source_stream.PersistentAccount.observe()`; `pm_forward_continuous_transport.SerialWriter`; `pm_forward_journal.PaperJournal.append_source_receipt()/consume_source_effect()`; `pm_forward_source_fanout`; `pm_forward_observed_paper`; `v4_source_spool`; `v4_source_export._atomic_private_output()`. See the [original frontier and alternatives](../PYDANTIC-NATIVE-FAILURE-GRILL-20261109.md), [all-28 matrix](../PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md), [combined-fault matrix](../PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md), and [Q30–Q34 domain partition](2026-11-09-pydantic-native-domain-interfaces.md).

## Q35 — Continuity-sensitive quarantine, not blanket discard (APPROVED)

1. A required malformed official selected-position replacement, identity or native DEX mismatch, incomplete census, invalid timestamp, provider semantic ambiguity, or journal/source conflict invalidates the **affected selected account's prospective continuity proof**. Record a durable GAP/QUARANTINED transition in its existing stream authority where the journal can safely commit. Fence its pending **new-risk** intents and downstream dependents.
2. Raw evidence, first-known clocks, last-known economically valid positions, follower holdings, unresolved exits and durable HALT remain preserved. A missing or rejected frame never means flat and cannot create a retroactive T0 or a new-entry due clock.
3. Known-optional diagnostics may be retained as raw metadata or a typed diagnostic **only after** independent proof that core economic replacement completeness remains valid. Invalid Vike fills or historical/public trade corrections are quarantined in their own feeds; those cannot override an independently valid official source.
4. A shared transport integrity failure fences all identities whose complete observation cannot be established; a single attributed account error must not stop unrelated healthy accounts. Critical journal divergence stops affected writer/stream until safely reconciled.
5. Recovery requires a complete verified official baseline and a later genuine position transition, with bounded error/reconnect budgets and idempotent journaled remediation. Source recovery does not clear a financial HALT.

**Rejected:** Treat every schema error as a harmless skipped frame; treat every optional fill failure as a global source GAP; automatically infer a close or an eligible entry after reconnect.

## Q36 — Each authority owns its cursor and local effect transaction (APPROVED)

1. Preserve existing per-stream epoch, SHA-linked receipt sequence and atomic source receipt/checkpoint commit in `PaperJournal`.
2. Signed export packet publication is atomic/durable before producer cursor advance; replay is **at least once**. Consumers validate signature/chain/cursor and deduplicate.
3. Each independent portfolio journal maintains its own verified source-import prefix and effects. Partial fanout is explicitly recorded, caught up per consumer and **never** advertised as a globally committed multi-portfolio transaction.
4. Where a local account effect consumes one source event, the same owning transaction must commit both the effect's idempotency identity and the account's source-consumption progress; unknown external outcomes remain unresolved until reconciled. The existing `consume_source_effect()` path establishes this for supported v1 effects; the distinct V4 `ObservedPaper.run.record()` route must be verified or explicitly adapted to equivalent guarantees before cutover. Do not infer cross-path equivalence from similar names.
5. The immutable source event plus destination portfolio/run/pod and policy revision forms a deterministic per-consumer identity; conflict on repeated identity blocks, replay with same identity remains a no-op. Guardian's signed protected permits and broker/order effects remain an independent financial authority, not a cloned portfolio cursor.

**Rejected:** One global consumed bit; cross-DB two-phase commit merely to synchronize independent paper ledgers; fresh intent IDs after replay; claims of global exactly-once effects.

## Q37 — Risk-weighted combined failure acceptance (APPROVED)

- The [13-case combined-fault matrix](../PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md) is a **minimum accepted design** alongside the [28 individual cases](../PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md). The scenarios collectively reference IDs 01–28. Each still requires **actual tests or reachability proof** before engineering closure.
- Relevant critical interactions must pass before the affected source/paper SHADOW canary: malformed source + due timer (CF01); HALT + stale quote + restart (CF02); cancel/fill + writer cancellation (CF03); crash-atomic signed spool/cursor (CF04); partially failed two-portfolio fanout (CF05); and pinned release/Guardian HALT (CF13). Other combined cases become mandatory as their S3–S5 families are migrated or retired.
- Use existing reducer/journal/dispatch interfaces under controlled time and fault schedules rather than mocks that bypass the authority at risk. A causal T0 fabrication, silent HALT downgrade, unknown order double-dispatch, forced flat, cursor skip or spoofed permission fails its stage.
- No all-combinations exhaustive Cartesian product, multi-month soak, or AI-grader score is a substitute for these targeted invariants.

**Rejected:** 28 isolated passing unit tests automatically prove the cross-aggregate system; conversely, exhaustive all-pairwise permutations are mandatory before any safe read-only change.

## Q38 — Evidence-classed SHADOW canary (APPROVED)

- Preflight requires verified source/release identities, selected perp scope and trust pins, critical negative/positive tests, actual independent paper-ledger identity and a reversible journal-preserving installation plan **under separately authorized deployment scope**.
- Authentic forward evidence includes one genuine complete post-baseline official economic position transition, its original first-local-known T0, its **T0+300s due contract**, actual scheduler/deadline and admission outcome (simulated filled, explicitly BLOCKED or EXPIRED), correct quote/source identity and a durable restart/replay witness. A late tick inside a grace window is **not automatically evidence of an exact T+300 market attempt**; record scheduling delay and apply the previously approved one-shot policy, never silently reset T0.
- Before financial cutover, test both a justified protective reduction and blocked/unresolved protective outcome under adversarial evidence. Capture authentic later source reduction/exit when it occurs. Until then declare `FORWARD_EXIT_NOT_YET_OBSERVED`, not a synthetic positive or an infinite waiting requirement.
- Read-only/paper-source observation can be expanded while genuine exits remain unobserved if separately authorized; promoting **all 16 modeled portfolios** must state per-portfolio financial isolation and evidence gaps explicitly, with owner-approved exact scope and reversible release. A single source canary does not certify every independent portfolio.
- A SHADOW run never authorizes demo, funded, broker, real orders, or scientific alpha.

**Rejected:** Instant unverified 16-portfolio cutover; mandatory calendar soak unrelated to observed events; fabricated forward exit or a claim that any due event guarantees a filled market order.

## Q39 — Implementation specification readiness gate (APPROVED)

A design is **ready to synthesize into an implementation specification** when: (1) the Q3–Q39 decision frontier is closed; (2) every one of 28 lifecycle families has a proposed terminal disposition, owner, specific negative/positive acceptance witness and S0–S5 stage; (3) the combined-fault cases and stage-specific prerequisites are explicit; (4) source/finance/Guardian transaction and identity boundaries are independently traced; (5) historical wire SHA and T+300 invariants are binding; and (6) remaining unknowns are read-only S0 verification tasks or measured implementation thresholds rather than unresolved owner policy decisions.

An **implementation-ready engineering specification** additionally needs executable target-module boundaries, concrete versioned interface/contract signatures, implementation slices and dependency gates, test invocations/fixtures, a fail-closed default where wire fields remain unresolved, measurable baseline/performance criteria, compatible source/Guardian consumer schema pins, and separately authorized release/runbook paths. The spec may require the autonomous engineer to discover current facts during S0; it must not pretend the deployed revision or authentic native raw wire has already been proven.

Decisions/roadmap acceptance do not constitute a final implementation spec or authority to change code. The owner must explicitly authorize implementation and separately authorize any deployment outside an already granted scope.

## Open factual S0 verification, not new owner policy questions

- **Provider wire shape:** The Hyperliquid published `WsAllDexsClearinghouseState.clearinghouseStates` type is a `Record<string, ClearinghouseState>`, while the inspected parser expects a list of pairs. Compare original captured immutable wire to current official type; do not modify the observer on documentation alone or weaken native completeness. Official source: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions.
- **Real V4 financial effect idempotence:** Reconcile `pm_forward_observed_paper` event replay against the proven `PaperJournal.consume_source_effect` v1 path without replacing their historical hashes.
- **Installed runtime and compatibility pins:** Verify actual user services, root-protected Guardian and companion revisions in a read-only S0 preflight. Git HEAD is not deployed state.
- **Source/observer timing:** Benchmark genuine first-known provider receive time, observer processing, due scheduling and one-shot attempts under the exact T+300 contract; do not call a delayed attempt exactly-on-time.

## Consequence

**Q3–Q39 design is complete**, subject to the bounded factual S0 work above. The next output should be a single consolidated implementation specification, not another conceptual framework debate, unless S0 evidence refutes a binding premise. The [design closure/readiness review](../PYDANTIC-NATIVE-DESIGN-CLOSURE-20261109.md) records completeness and proof limitations. No engineering fix has been executed and **0 of 28 state-machine families are closed**.
