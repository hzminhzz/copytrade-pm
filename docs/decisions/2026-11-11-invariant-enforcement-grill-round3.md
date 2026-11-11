# ADR: Invariant-enforcement grill, Round 3 — failure semantics and trust boundaries

**Date:** 2026-11-11
**Status:** **OWNER-APPROVED FOR DESIGN**, Q11=A, Q12=A, Q13=A, Q14=A, Q15=A, Q16=A, Q17=A. Documentation-only; no runtime fix, source-wire migration, broker approval, deployment or trading authority.

## Context and dependencies

Continue [Round 1](2026-11-11-invariant-enforcement-grill-round1.md) and [Round 2](2026-11-11-invariant-enforcement-grill-round2.md). Original first-known T+300, source provenance, independent consumer cursors, PM03/PM04 simulated finance and the separate Guardian financial authority remain binding.

Cross-check: the signed V4 producer derives leader marks from native positionValue / abs(szi) when supplied, with mark_known_at_ms equal to source first-known time (src/copytrade_pm/v4_source_export.py). This does not prove age at T0+300. The observed-paper route still supplies follower midpoints for both prices. The protected receiver still uses v1 proofs without signed predecessor reference and reads cursor state before BEGIN IMMEDIATE. None is fixed by this ADR.

## Q11 — Mark precedence and bounded independent provenance (APPROVED: A)

- At the original decision cutoff, prefer a provenance-verified, complete, contract-matched official native leader mark from the valid selected-account observation **only while fresh under the versioned source-clock policy**. A five-minute-old native valuation does not become fresh because an entry is due.
- If that valuation is missing or stale, allow a separately authenticated source-venue mark **only** under an explicitly versioned fallback policy binding native instrument/DEX, original as-of and first-known clocks, provider trust, price semantics and maximum age.
- Never silently reuse the follower quote, historic fill, bar close or unbounded T0 mark. Equal numeric values from genuinely independent proven price sources are allowed.
- Missing/ambiguous/stale required mark blocks **new-risk** on that opportunity. Preserve source continuity/inventory and protective-risk responsibilities; do not infer flat.
- Maximum mark age, clock skew, accepted feed, per-contract cadence and destination quote-side thresholds are **not approved numbers** by this decision. Require measurement and versioned policy in the next design frontier.

**Rejected:** unconditional dedicated mark-feed replacement; indefinite T0 mark reuse; follower-price fallback.

## Q12 — Account-scoped financial HALT on contradictory broker evidence (APPROVED: A)

- An impossible terminal status, incomplete cumulative fills, incoherent cutoff/inventory or mismatched reservations blocks new-risk admission and latches the affected **protected financial account**. A reported FILLED with only 60% independently confirmed cumulative fills is contradictory.
- Preserve actual fills, outstanding reservations, held exposure, ambiguous remote effects, and independent protective outcomes. Neither status nor acknowledgement alone releases risk or authorizes a replacement order.
- Unrelated official source/public research streams continue, unless they share the failed trust/transport boundary. Do not convert a Guardian account issue into an unrelated source GAP.
- Guardian owns financial HALT and verified recovery. Protective reductions require independently reconciled current holdings and valid market/risk authority, not automatic exception to HALT.

**Rejected:** intent-only quarantine while admitting other new-risk orders on the same financially incoherent account.

## Q13 — Original-version historical verification (APPROVED: A)

- Validate historical records under original economic/event versions and immutable SHA chains. Newly introduced invariant fields are not retroactively required of old signed records.
- A historical event lacking sufficient original evidence for a currently relevant financial invariant is explicitly classified as **legacy semantic uncertainty**: neither corrupted by assumption nor proven safe.
- Permit read-only forensic/source observation, but block the affected protected new-risk capability until independent authentic account/broker reconciliation establishes a valid forward safety boundary.
- Never rebuild, reseal, erase or silently reinterpret old journal economic obligations, HALT or trust floor. Exact legacy-kind verifier coverage and evidence-anchored forward checkpoints remain next-frontier choices.

**Rejected:** destructive historical rebuild or blanket grandfathering of SHA-valid history.

## Q14 — Scoped recovery signature, separate remediation verification (APPROVED: A)

- A protected role-scoped signer authenticates a recovery **request**, binding account, incident, specific latched HALT reason(s), current journal head/sequence, boot epoch, policy/release identity, nonce, issue/expiry time and immutable evidence references.
- Independently verify cause-specific remediation against trusted source, account, broker and financial evidence. Operator identity or a signed digest is **not** proof that the condition is fixed.
- Wrong account/reason, expired, revoked or replayed requests fail; preserve unrelated HALTs and unknown executions. Record requested, verified and denied outcomes separately. Verified final clearance revokes permits, advances epoch and DISARMS, never auto-arms or sends orders.
- Do not mandate two-person approval for every routine SHADOW incident. Exceptional high-impact overrides may require elevated independent review; detailed role custody, key rotation, validity and evidence schemas remain Round 4 decisions.

**Rejected:** digest-only operator assertion, signature-as-remediation, universal dual approval.

## Q15 — Immutable signed prospective stream-head anchor (APPROVED: A)

- At approved cutover establish a signed, independently pinned per-stream head anchor covering selected account/native DEX scope, producer signer/release, generation/epoch, committed cursor, original chain head and cutoff/first-known boundary.
- Verify the anchor in the consumer's own trust context, then require all **successor** v2 events to authenticate their predecessor against that pinned durable head. A signed present-head SHA without checkable predecessor is insufficient.
- New prospective baseline does not create an entry signal. Never make a historical event first-known at cutover, change v1 signed bytes, or assert that a new cutoff proves all upstream history prior to the anchor.
- Source chain mismatch, signer/epoch/scope drift fences its affected stream. Exact wire version, release compatibility, key rotation and handshake remain Round 4 choices.

**Rejected:** full genesis replay as prerequisite for prospective SHADOW cutover; upgrading v1 authenticity claims by assertion.

## Q16 — Missed T+300 means expiry, not catch-up (APPROVED: A)

- Preserve the original first-local-known T0, frozen identity, original T0+300 due instant and original policy-specific grace. Process restart, queue replay and worker downtime cannot reset them.
- If the allowed opportunity window elapsed without a verified attempt, record EXPIRED/MISSED with original event, due time and observed lateness. **No new-risk catch-up order** or new intent identity.
- An earlier dispatched but unconfirmed operation is UNKNOWN, not expired or a fresh retry permit; reconcile under its existing effect/order identity.
- Protective reduction remains separate and may act promptly only from independently known held inventory, legitimate source/risk rationale and fresh risk/market evidence. Failed protective outcomes remain unresolved and accountable.

**Rejected:** resetting the five-minute clock or executing late new risk after restart.

## Q17 — Packet envelope trust, then isolated per-wallet quarantine (APPROVED: A)

- Verify the authentic whole-packet signed envelope and exact original payload digest **before** applying any event; an unauthentic/tampered envelope invalidates the entire packet.
- After envelope authenticity, validate each account's event chain and semantic scope independently. A wallet-attributable invalid event quarantines that account/its dependents, without advancing its valid cursor or inventing flat positions.
- Unrelated valid streams may durably progress; preserve their independent cursors and exact event identity. A partial packet stays PARTIAL (not COMPLETE) until explicit audited valid resolution of every included event.
- Replays must not duplicate A/C effects or skip B. Shared signer compromise or common transport integrity error fences every affected stream. Specific quarantine terminal disposition and retention/restart protocol remain Round 4 decisions.

**Rejected:** blocking independent healthy streams for one attributable failure; silently skipping one wallet and reporting complete packet success.

## Consequences, owners and remaining frontier

**copytrade-pm:** signed leader mark/source proof and native scope, frozen timing and paper per-consumer effects; PM03/PM04 research finance authority unchanged.

**prop-production:** protected source receiving/projection, broker evidence, account HALT, protected legacy finance journal and recovery. Guardian remains sole broker-admission owner.

The upcoming design frontier must settle: mark freshness/versioned provenance; broker cutoff/reservation accounting; legacy semantic checkpoint; recovery key/role/override/rotation; v2 chain handshake/compatibility; partial packet terminal disposition/retention; and adversarial proof/rollout requirements. **No code, push, merge, deployment or financial authorization is approved.**
