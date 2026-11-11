# ADR: Invariant grill Round 5 — evidence-weighted acceptance and reversible release

**Date:** 2026-11-11
**Status:** OWNER APPROVED FOR DESIGN — Q26=A, Q27=A, Q28=A, Q29=A, Q30=A, Q31=A, Q32=A, Q33=A.
**Scope:** documentation and implementation acceptance policy only. No code, data migration, publication, installation, signer provisioning, runtime promotion, scientific qualification or trading authorization.

## Context

This completes the architecture and failure-policy frontier established in the [Round 1](2026-11-11-invariant-enforcement-grill-round1.md), [Round 2](2026-11-11-invariant-enforcement-grill-round2.md), [Round 3](2026-11-11-invariant-enforcement-grill-round3.md), and [Round 4](2026-11-11-invariant-enforcement-grill-round4.md) ADRs. Existing 28-family Pydantic-native engineering acceptance and companion cross-repository tests provide useful regression evidence, but do not establish that these distinct residual trust-boundary findings are fixed.

The architectural abstraction is a **proof-carrying, domain-owned transition**: an authenticated observation yields a versioned, causal decision; the authority that owns the resulting state independently validates the proof and commits exactly its own local effect or explicit terminal disposition. This is a **semantic protocol**, not a new global shared Python state machine, second ledger, generic event platform or distributed transaction manager.

## Q26 — Risk-weighted adversarial acceptance (APPROVED: A)

Acceptance is organized by **four trust seams**, not a growing checklist for every incidental field:

1. **Causal source and pricing:** genuine selected-account scope, authentic original source and mark proof, cutoff versus first-known timestamps, stale/missing marks, versioned predecessor chain, independent wallet failures and no invented entry after restart.
2. **Financial conservation and safety:** impossible broker terminality, duplicate/partial/late fills, reservations, real account binding, durable HALT, independent remediation proof, rejected/expired signer, and protective reductions that never increase unresolved risk.
3. **Durable per-owner effects:** real local SQLite transaction/crash boundaries, two-writer stale read, before/after-commit faults, lost acknowledgments, replay, monotonic cursors, partial packet progress and no second paper effect.
4. **Cross-repository continuity:** known pinned producer/consumer/connector versions, negative incompatible-wire/signature cases, source-only NO_TRADE and compatible rollback that never rewrites original journals.

Reuse prior tests when the **exact scenario and authority boundary** match; add only focused new regression/combined-fault cases for uncovered behavior. Every residual finding receives concrete code/test/negative control evidence at its owner. Synthetic tests prove engineering, not authentic protected economics or execution. Do not demand unrelated full production/science gates for a documentation-only or research-only merge.

## Q27 — Measure, do not guess, mark freshness (APPROVED: A)

Use immutable authenticated source and market observations to measure leader mark age at the original T+300 decision, provider clock skew, real update cadence, missing-mark frequency and affected native markets. Record denominators, excluded observations and provenance; freeze empirically supported venue/instrument age and fallback limits in an explicit policy revision. Synthetic timings and arbitrary conservative-looking numbers do not qualify. Until actual admissible mark proof and a reviewed versioned limit exist, block that **new-risk** effect, not source collection or historical research merges.

## Q28 — Exact-commit, scope-aware compatibility evidence (APPROVED: A)

Keep the existing prop-production compatibility manifest as the **only** companion-commit/schema pin authority. For an integrated candidate, use the clean reviewed exact producer, protected consumer and connector revisions; run relevant signed source, broker, journal, cross-version and negative contract oracles plus owning regression/build/lint gates. Do not describe unrun cases or mandatory skips as passes; record exact SHAs, versions, tests, skipped reasons and artifact hashes. Documentation-only decisions do not require invented deployment ceremony. A clean green local suite does not prove root-installed services or financial readiness.

## Q29 — Authentic, bounded source-only SHADOW canary (APPROVED: A)

Evaluate the separately approved signed cutoff/head anchor, authentic post-baseline selected-position transitions, original first-known and T+300 eligibility/expiry, valid and invalid source marks, protected consumer restart and duplicate delivery, wallet-scoped continuity fault and no duplicate action. Verify there is **no real order route** and no promotion from source eligibility to Guardian finance. A source-only canary need not show positive follower alpha, a blanket calendar soak or broker mutations. Source collection success is a separate capability from paper admission.

## Q30 — Staged nonrewinding cutover and rollback (APPROVED: A)

Plan separate proof/release stages for producer, protected source-only receiver, modeled paper consumer and **independently authorized** Guardian finance. Reuse existing immutable bundle and named schema-compatible rollback mechanisms, the single manifest and role-bound deployment evidence. A rollback restores compatible **code and units** only, never winds back source events, cursor truth, financial journal, outstanding broker effects, trust floor or recovered HALT. If old code cannot safely read new protected state, fence the affected operation and preserve evidence instead of downgrading it. No deployment is authorized by this ADR.

## Q31 — Bounded operational state, immutable unresolved evidence (APPROVED: A)

Retain originals and content hashes under the existing private evidence authority with an approved, auditable preservation policy. Keep operational SQLite material compact: verified cursors, per-stream quarantine disposition, deterministic consumer effect identity, current state and bounded recent diagnostics rather than indefinitely replaying/duplicating full payloads. Compaction/archive must not delete unresolved evidence, silently complete PARTIAL packets, erase financial obligations or advance invalid cursors. Derive capacity/retention limits from measured workloads and recovery needs. This design neither claims nor performs an SQLite bloat repair.

## Q32 — Separate historical verification from future signer authority (APPROVED: A)

Retain original signed v1 and retired public key material as read-only historical verification inputs with their original assurance; they are **not** keys trusted for new prospective successors. A new approved active signer/release and anchored stream epoch govern v2. Test revoked/rotated/wrong-scope keys, old/new epoch replay and downgrade refusal. Protected signer provisioning and trust pin changes remain outside Git and require separate authorized operations.

## Q33 — Measure resource and recovery behavior (APPROVED: A)

Under representative observed stream rates and injected failures measure event lag, recovery time, concurrent writer contention, CPU/memory, SQLite WAL and disk growth, backlog/quarantine accumulation and source/replay throughput. Set bounded budgets and backpressure policy from measured VPS resources. A capacity failure blocks the **affected operational rollout**, not documentation integration or safe offline research. No invented throughput number becomes an acceptance fact.

## Abstract contract: Evidence → Decision → Owned effect

Across all four seams the minimum logical proof consists of:

- **Evidence identity:** original authenticated source/account/stream or provider-order record, hash and signer/trust scope.
- **Causal scope:** selected native contract, original first-known time, decision cutoff, predecessor/epoch and validity of prices.
- **Decision authority:** frozen k, risk and schema policy; eligibility is not a finance permit.
- **Owned result:** one local journal/effect/disposition with deterministic identity, invariants and replay/failure state.
- **Independent status:** ENGINEERING VERIFIED is not SHADOW RUNNING, SCIENTIFICALLY QUALIFIED or TRADING AUTHORIZED.

These are logical facets of existing versioned domain records, **not** a mandate for one shared Pydantic class, new global database or broad runtime framework. PM03/PM04 preserve research-finance ownership; Guardian independently owns protected-finance effects. Prefect may orchestrate bounded **offline research**, not the event hot path or broker.

## Rejected alternatives and closure

Rejected: unit-green only; synthetic freshness guessed as live policy; unpinned cross-repo compatibility; a running process or baseline as canary success; rollback by rewinding financial history; indefinite operational SQLite payload accumulation or timed deletion of unresolved proof; any retired key signing future events; unmeasured performance acceptance.

The **architectural question frontier is closed for this audit**. Remaining inputs are factual/engineering evidence to be measured during a separately authorized implementation, not reasons to open another round of speculative architectural choices: actual mark-age distributions and cost/quote provenance; actual protected broker coherent history; signed production key/trust provisioning; precise migration-compatible release bundles; fault-injection results and VPS resource envelope. A consolidated closure record indexes owners and proof obligations. Existing separate merge, source-only SHADOW, protected finance and trading approvals remain intact.

No engineering implementation, push, merge, deployment, or protected recovery has occurred as a result of this ADR.
