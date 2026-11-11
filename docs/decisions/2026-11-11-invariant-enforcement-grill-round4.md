# ADR: Invariant-enforcement grill Round 4 — compatibility, economics and recovery

**Date:** 2026-11-11
**Status:** OWNER-APPROVED FOR DESIGN: Q18=A, Q19=A, Q20=A, Q21=A, Q22=A, Q23=A, Q24=A, Q25=A. Documentation-only. No implementation, push, merge, migration, deployment or trading authorization.

## Context and existing authority

Extends [Round 1](2026-11-11-invariant-enforcement-grill-round1.md), [Round 2](2026-11-11-invariant-enforcement-grill-round2.md), and [Round 3](2026-11-11-invariant-enforcement-grill-round3.md).

Source and paper boundaries remain owned by copytrade-pm. PM03/PM04 independently account for simulated money; protected Guardian, its journal and its broker have separate authority in prop-production. The existing protected compatibility manifest is the **only** cross-repository pin authority. Prefect is optional read-only research orchestration, never a source hot path, financial journal or broker gate.

Evidence inspected: the source export derives an official mark from native positionValue / abs(szi) at original first-known, not automatically at T+300; the observed-paper execution passes follower midpoints to both marks; source events and paper results reside in separate databases. Historic frozen k reports and signed source artifacts must not be rewritten to correct future modeling.

## Q18 — Versioned, venue-specific source-mark freshness (APPROVED: A)

1. Every new-risk decision binds a named source-mark policy revision to the source identity, DEX-qualified native instrument, price semantics, authenticated provider/source evidence, original source/as-of and first-known times, decision cutoff, measured clock uncertainty, and max admissible age.
2. Prefer an official native position valuation **only** while its independently attested age remains within that policy. A still-valid position book may coexist with a stale valuation. If official valuation is stale or absent, separately authenticated source-venue valuation is permitted only when a specific **versioned fallback** policy already authorizes that trust root, contract and price semantics.
3. Define maximum age and permissible skew from measured provider update cadence, distribution of authentic leader-mark ages at T+300, provider timestamps and market-specific failure cases; never hard-code an unmeasured universal threshold or treat synthetic fixtures as empirical calibration.
4. Independently validate the destination follower quote, including appropriate price side and its **own** freshness policy; current source marks do not attest executable follower bid/ask. Missing, stale or cross-contract price fences only the dependent new-risk effect. Original T0 and established grace remain unchanged, while independently valid protective reductions remain a separate operation.
5. Treat the age parameters and source-provider priority as **explicit S0 measured inputs** to an implementation-ready spec, not as pre-approved numeric limits.

**Rejected:** one mandatory global mark-age threshold regardless of cadence; silently reusing follower midpoint, older mark, Vike candle or historic fill.

## Q19 — Provider-specific terminal normalization before Guardian (APPROVED: A)

1. Each provider adapter converts its raw broker order statuses and original identity/time/cutoff evidence into a **versioned canonical order observation**. Preserve the original provider status and raw evidence reference; never guess that provider-specific CLOSED/EXPIRED/CANCELLED means full economic completion.
2. Canonical reporting includes signed intended quantity, cumulative executed quantity, per-execution identities and ordering, actual terminal/disposition classification, cutoff/history completeness, and whether residual quantity is known. FILLED requires full quantity and reconciled executions. Partial fills during cancellation remain financial effects, even if the residual order is independently proven inactive.
3. Protected Guardian independently checks canonical inputs against its **own** durable intent/fill/inventory/reservation ledger. No second financial accounting authority is introduced in research or provider normalization.
4. Unknown provider codes, contradictory terminal combinations, uncertain histories and missing cutoffs stay UNKNOWN/RECONCILIATION_UNCERTAIN, preserve reservations, and block new risk for the affected protected financial account. Do not turn an ambiguous provider response into an explicit zero fill or verified flat.
5. Propr and Bybit current read-only financial evidence remains nonauthorizing until real coherent provider contracts are proven; synthetic gateway tests do not qualify them.

**Rejected:** pass arbitrary provider status strings straight to generic reservation release, normalize as if ACK = final fill.

## Q20 — Nonrewinding forward semantic checkpoint for legacy journals (APPROVED: A)

1. Verify historical records under the invariant semantics **actually applicable** to their original event version. Preserve original bytes, SHA sequences, account binding, prior financial obligations and trust floor. A valid hash alone is not a proof of economics.
2. If original fields cannot establish a newly required invariant, classify **LEGACY_UNVERIFIABLE** for that particular financial capability, not blanket corruption, all-clear or authorization.
3. An independently evidenced, complete and coherent account/broker reconciliation may establish a **new forward semantic checkpoint** with explicit account, event schema version, signed evidence references, sequence/head/epoch and unresolved-effect disposition. Append it prospectively; never rewrite or reseal earlier entries or reset unknown execution outcomes by assertion.
4. Other research/source READ capabilities continue independently. Protected new-risk permission remains blocked until the forward checkpoint meets the Guardian-owned financial authority and existing release criteria. A checkpoint is not automatic ARMED/TRADE.
5. The exact historical event-kind table, semantic unknown classification and artifact schema are implementation-spec inputs, not new business permissions.

**Rejected:** destructive history rebuild; all-v1 grandfathering; indefinite demand for v2 fields absent from an original v1 record.

## Q21 — Separate role-scoped recovery signer lifecycle (APPROVED: A)

1. Use a dedicated protected, independently pinned **recovery signing authority**, distinct from source-observer, research reviewer, portfolio-release and broker credentials. Bound each operator/role to account/reason/action scope, current journal head/sequence, boot epoch, incident identity, nonce, issue/expiry and immutable remediation references.
2. Revocation, key rollover, role removal, stale-head/epoch conflicts and nonce replay invalidate unused recovery requests. A signed request proves an authorized request, **not** genuine remediation; a separate independent Guardian predicate verifies broker, finance or source repair.
3. Routine SHADOW incidents do **not** require blanket two-person signoff. Exceptional requests that would waive independently proven financial restrictions require stronger review and cannot be called routine recovery. A policy override does not manufacture missing broker evidence.
4. No new recovery key is generated or provisioned by this ADR. Protected secrets and signer pins remain external to research repository and Markdown files.

**Rejected:** reuse the existing portfolio-release signing authority to simplify trust boundaries, or regard operator strings and SHA-shaped evidence as sufficient.

## Q22 — Future-only pinned v2 signed-source cutover (APPROVED: A)

1. The prospective v2 producer and protected consumer use explicitly versioned signed wire semantics, including signed predecessor-chain proof and a cutover **head anchor**. Start a new source epoch/baseline from a reviewed cutoff. The v1 historical source journal and signed packets retain original bytes and trust meaning.
2. Gate compatibility through the **existing prop-production compatibility manifest**, reviewed producer/consumer commit pins, trust roots and negative tests. Do not create a second compatibility registry, dynamically infer wire semantics or silently switch protocol mid-stream.
3. The consumer may retain read-only historical v1 verification while processing v2 successors on the **new verified stream**. No mixed-version live events on one active stream, no implicit v1 fallback after a v2 anchor, and no double-delivery of the same economic transition as fresh signal across epochs.
4. The root/privileged deployment and signed source handoff are independently authorized operations; writing the ADR changes no live signer, release, projection, service or Guardian permission.

**Rejected:** mixed v1/v2 live stream interpretation, silent downgrade, full historical replay to generate new opportunity times.

## Q23 — Packet PARTIAL versus RESOLVED_WITH_QUARANTINE (APPROVED: A)

1. Packet **COMPLETE** means every original contained event passed the applicable verification and acceptance path; no event was discarded or fabricated.
2. With an authentic envelope and an attributed invalid wallet B, accepted independent streams A/C may commit. Keep B's verified cursor and pending fault; report packet **PARTIAL** until B's failure has an explicit, durable, audited per-stream quarantine disposition and a genuinely fresh verified official baseline under the applicable recovery policy.
3. After that resolution, mark the original packet **RESOLVED_WITH_QUARANTINE**, explicitly different from COMPLETE. The rejected B event never counts as accepted history and cannot mint a signal on recovery baseline. A later real change after the baseline can have its own new opportunity.
4. Preserve original packet SHA, accepted per-wallet prefixes, rejection evidence and reason, and the audit link to resolution. Restart/replay is idempotent. Shared packet-envelope/signature failure rejects the whole packet before any event; unscopable shared trust loss fences its dependents.
5. Retention/compaction thresholds and how permanently unresolved packets are reported remain acceptance/runbook policy to decide on the next frontier. No arbitrary timeout converts PARTIAL to COMPLETE.

**Rejected:** success status after silently skipping B; global abort of A/C on a verifiably local fault.

## Q24 — Causal consumer-owned modeled effect receipts (APPROVED: A)

1. A paper effect carries a stable destination owner (run/portfolio/pod), original committed source event/stream-head identity, decision cutoff and clocks, frozen sizing/policy/release identity, follower valuation evidence and its **own** deterministic idempotency identity.
2. A destination local transaction atomically persists consumed source progress and the resulting paper effect or an explicit terminal disposition. After a crash, compare original source and destination receipts; identical replay is a no-op and a conflicting identity or UNKNOWN external outcome remains quarantined/accounted.
3. Immediately before local commit, revalidate whatever original source-head fence can be proven without holding independent databases in an imaginary global transaction. A source update racing between distinct SQLite commits is recorded as a causal ordering/reconciliation limitation, not falsely labeled impossible. A later source update triggers its own deterministic reduction/exit policy and never retroactively changes the earlier first-known time.
4. If source continuity at the required decision time cannot be established, block new risk, persist the reason, retain held inventory and independently valid protective paths.
5. The currently separate ObservedPaper.run.record pathway must prove these local consumption/idempotency semantics itself. Guarantees of another PaperJournal.consume_source_effect path cannot be copied by analogy.

**Rejected:** cross-database two-phase commit or long locks on the live source writer, unbound effect IDs regenerated after restart, claiming global exactly once.

## Q25 — Versioned economic correction and re-evaluation (APPROVED: A)

1. Fixing source-versus-follower mark usage is an **intentional prospective economic semantics revision**. Preserve historic signed fixed-k, frozen k releases, original receipts, backtest/economic reports and their original claims exactly; do not overwrite source data or silently restate old follower PnL.
2. Record distinct old-versus-new versioned sizing/price policies and comparable replay artifacts with verified original as-of constraints, same eligible opportunities, independent source marks and follower quotes, native rounding, gross/market/pod/day/trailing controls, realistic costs and missing-price opportunity exclusions.
3. Report quantity/notional deltas, rejected opportunities, risk-limit changes and post-cost follower economics separately. An engineering correction or favorable historical difference is **not** independent prospective qualification or proof of profitable executable orders.
4. An additive read-only engineering change may merge when reviewed and tested even if new science or activation remains blocked. A different active signed k/risk policy needs its **own** independently authorized future-effective release, original release identity and rollback rule. No retroactive risk promotion.
5. Use the existing Track C frozen-k and T+300 safeguards rather than a parallel calibrator or redundant gate.

**Rejected:** altering sizing semantics while treating all prior k calibrations and performance as directly comparable without an explicit economic revision record.

## Consequences and ready next design frontier

The next independent frontier concerns **acceptance and reversible release contracts**: minimum adversarial failure matrix and real authority seams; cross-repo exact-commit verification and skipped-test handling; source-mark empirical thresholds as evidence rather than guessed policy; authenticated SHADOW canary scope; account/projection rollout order; schema-compatible rollback without journal rewind; evidence-bound signoff versus merge gates; and operational retention/metrics.

These are not requests to create new runtime state, keys, SQLite artifacts or real orders. Do not implement, push, merge or deploy by virtue of this ADR.
