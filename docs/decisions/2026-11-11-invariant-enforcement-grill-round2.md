# ADR: Invariant-enforcement grill, Round 2

Date: 2026-11-11
Status: OWNER-APPROVED DESIGN (Q5=A, Q6=A, Q7=A, Q8=A, Q9=A, Q10=A). Documentation-only; no source changes, migration, merge, deployment, scientific qualification or trading authorization.

## Context and dependencies

Follows [Round 1](2026-11-11-invariant-enforcement-grill-round1.md) Q1=B/Q2=A/Q3=B/Q4=B, the November 9 [domain interface partition](2026-11-09-pydantic-native-domain-interfaces.md) and [per-consumer effects ADR](2026-11-09-pydantic-native-failure-and-spec-readiness.md), and the [first-known T+300 contract](2026-11-08-position-first-t300.md).

This is a cross-repository design. The protected finance journal, broker order state and HALT recovery are owned by prop-production, not by this research codebase. Signed source producer and modeled paper finance remain separate from protected consumer and Guardian. No new global orchestration authority is created.

## Q5: Admissible independent source marks (APPROVED, A)

- Fixed-k new-risk target is signed selected-account native quantity times an authenticated, contract-matched leader mark times frozen k; only then convert USD notional at a separately authenticated follower quote.
- The leader mark must be known by the decision cutoff, fresh under an explicit contract-specific policy, attributed to the correct selected account/native DEX instrument, and linked to original verifiable source provenance. Preserve source observation time separately from the later T+300 decision time. A fresh quote on the follower venue is not evidence of a fresh source-venue mark.
- Official native source position valuation is an admissible candidate when its independent provenance, price semantics and freshness are proven. A separate, authenticated source-venue market mark can be admitted only under a versioned source-mark policy. Exact precedence, maximum age and evidence fields remain Round 3 decisions.
- Missing/stale/ambiguous required leader mark or follower quote blocks *new risk*. It does not fabricate source flatness, erase held paper inventory, clear HALT or excuse independently priced protective exits.
- Reject follower-midpoint reuse as the source mark, legacy historical-fill price and Vike OHLC as an unversioned live fallback. Retain signed legacy FIXED_K_NATIVE_QUANTITY policy meaning and frozen historical results.

Observed code: src/copytrade_pm/pm_exposure_sizing.py consumes separate marks, but src/copytrade_pm/pm_forward_observed_paper.py supplies the same follower midpoints in both calls. src/copytrade_pm/v4_source_export.py already derives prospective leader marks from native positionValue / abs(szi) where available; deriving a source mark is not proof it remains fresh at due.

## Q6: Terminal broker order conservation (APPROVED, A; Guardian owner)

- A broker status alone does not attest financial completion. Filled terminality requires complete signed cumulative quantity supported by coherent order/fill history and exact order/intent binding. Partial fills remain financially real.
- CANCELLED/EXPIRED/REJECTED may be terminal with nonzero filled quantity only when the original provider contract supports that case, all executions to the authoritative cutoff are accounted for, and residual uncertainty is resolved. UNKNOWN outcomes, inconsistent terminal labels, conflicting executions, or incomplete history must not release remaining reservations or authorize replacements.
- Validate recognized versioned status vocabulary and quantities at gateway trust boundaries; enforce reservation conservation again against the protected Guardian's own cumulative ledger. This is complementary ownership, not two competing ledgers.
- An inconsistent broker account snapshot fails protected admission and preserves the affected outstanding risk and HALT. Research source collection remains independent.

Protected code mismatch: BrokerSnapshot.ready checks finite order quantity and bounds but not FILLED implies filled == quantity, while Guardian's _reconcile_economics uses terminal statuses to release reservations after reconciliation.

## Q7: Versioned semantic journal replay (APPROVED, A; Guardian owner)

- Journal event SHA, sequence, account binding and snapshot equality are necessary, not sufficient, for legal financial state.
- New transactions must check domain-specific transition preconditions, allowed state progressions and postconditions **before commit**; replay checks the historical version's meaning, its invariants and protected authority boundaries.
- Preserve all existing journal event bytes, original hashes, old schema semantics and root trust floor. Do not retroactively reschema or overwrite legacy v1 transactions.
- A legacy record whose economics cannot be independently validated must be explicitly classified as unverifiable and block relevant protected admission until a legitimate, separately evidenced reconciliation/recovery boundary is established. Read-only forensic access may remain available. Detailed legacy migration policy is Round 3.
- Normal operations may use cached incremental proof; full bounded replay on restart/verification/upgrade must preserve fail-closed semantics. No broker I/O inside a journal SQL transaction.

## Q8: Authentication plus independent HALT remediation evidence (APPROVED, A; Guardian owner)

- A signed, incident-scoped recovery request authenticates who requested a specific clearance and the approved authority scope. The signature does **not** assert that the account, source or broker problem has actually been fixed.
- Require independently verified reason-specific remediation predicates, current account/release/journal/epoch binding, bounded validity, anti-replay and explicit linkage to the currently latched HALT(s). Wrong-account/reason, expired, conflicting, or merely SHA-shaped evidence cannot clear a HALT.
- Keep recovery-request and recovery-verified outcomes auditable. Preserve unrelated latches, unknown orders, and the existing narrow midnight-baseline semantics.
- After verified clearance, revoke outstanding permits, increment the boot epoch, and transition to DISARMED when no other HALT remains; never auto-arm, order or promote a research/SHADOW observation.
- Do not require a blanket second-person approval for every routine incident. Exact operator trust anchors, exceptional escalation and evidence types are Round 3 decisions.

## Q9: Versioned signed predecessor-chain proof (APPROVED, A)

- The next prospective signed source wire version must bind the authenticated *previous* stream chain identity, current committed event, epoch, cursor, source/account/DEX scope, first-known and producer signer identity such that the consumer can recompute or independently verify predecessor linkage.
- The protected consumer checks current event authenticity and continuity against its own durable stream checkpoint in the same owning transaction; no trust upgrade from a producer-supplied current chain digest alone.
- Historical signed v1 packets, their bytes and original SHA remain immutable. Legacy proofs retain their **original** assurance level and are not silently treated as v2 predecessor-verified proof. A clearly versioned new release/receiver compatibility and initial anchored baseline are required before any v2 cutover.
- A discontinuity, reused cursor with different event bytes, unexpected signer/epoch or invalid predecessor fails closed for affected prospective new risk. Original baselines cannot become retroactive entries.
- Do not claim the current v1 receiver already offers independent predecessor-chain verification; it currently validates the signature and monotonic cursor and retains the signer-provided stream_chain_sha.

## Q10: Deterministic per-consumer crash/replay reconciliation (APPROVED, A)

- Source commit, paper modeled effect and protected finance remain distinct local authorities, never a globally atomic action. Each consumer derives one stable effect identity from the immutable source occurrence, selected portfolio/run/pod, original first-known and frozen policy/release version.
- After crash/restart, compare independently durable source and destination prefixes, replay verified missing **consumer processing** with original event identity, and commit local effect plus consumption progress in the destination's own atomic transaction where possible.
- Identical repeated input is a no-op; conflicting payload or ambiguous financial/broker outcome is quarantined/reconciled, never treated as an invitation to generate a new intent or execute another order. Preserve all existing modeled inventory and account exposure.
- Replayed source evidence does **not** generate a new first-known T0. Whether a timed new-risk attempt may occur after its original deadline, and how a late protective reduction behaves, is a Round 3 owner decision; do not infer that replay authorizes catch-up.
- The V4 observed-paper run.record path must be independently verified/adapted; prior guarantees for a distinct PaperJournal.consume_source_effect path do not establish equivalence. No cross-DB two-phase commit.

## Rejected alternatives

1. Follower midpoint or estimated bars substituted as a source mark for live fixed-k.
2. Trust broker terminal status alone and free reservations on acknowledgement.
3. Hash-only journal replay as sufficient financial semantic proof.
4. Recovery from operator/digest-shaped metadata without remediation verification.
5. Historical v1 signatures silently reinterpreted to satisfy stronger future cryptographic chain semantics.
6. A second shared transaction coordinator, global consumed bit or reconstructed fresh intent after crash.

## Consequences and next frontier

The first two rounds settle **policy and authority**, not exact interfaces or runtime evidence. Ready Round 3 decisions include leader-mark source priority/freshness, treatment of contradictory broker snapshots, legacy journal semantic uncertainty, recovery trust and remediation witness, initial signed chain anchor, and expired T+300 replay semantics. Their concrete fixtures, compatibility gates, migration sequencing and runbooks follow from those decisions.

The current protected V4 receiver remains source-only SHADOW; the absence of a broker route, independently qualified quote/finance proof and trading permission is not a defect to bypass.
