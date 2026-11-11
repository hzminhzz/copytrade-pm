# ADR: Canonical five-minute position checkpoints (design grill)

**Date:** 2026-11-11
**Status:** OWNER-APPROVED TARGET POLICY (Grill Q1=A); documentation only, not implemented, merged, deployed, scientifically qualified or trading-authorized.
**Scope:** Shared source-signal interpretation for `copytrade-pm` virtual paper and `prop-production` Guardian. Source-provider authority (Q2) and detailed checkpoint contracts are still undecided.
**Related current contract:** [Official selected-position first-known T+300](2026-11-08-position-first-t300.md). That contract and its running services remain unchanged pending a separately authorized, versioned release/cutover.

## Decision

Adopt a new **five-minute position-state sampling policy** as a prospective architecture target. At UTC checkpoint boundaries (00:00, 00:05, 00:10, ...), a single Canonical Wallet Signal Authority (CWSA) compares verified, complete selected-account economic position vectors with the prior admitted checkpoint under its declared scope and policy version. An actionable change produces a shared, durable, proof-carrying target-state signal consumed by all 16 virtual-paper portfolios and the protected Guardian. Unchanged positions do not produce a new trade instruction.

CWSA owns canonical checkpoint/time identity, verified account/scope and position-state interpretation, deduplication and signal provenance. It does **not** own follower financial inventory, broker permission, modeled paper fills, live execution, risk or HALT. Independent paper PM03/PM04 and Guardian retain their respective finance, verification, target application and journals. A shared source checkpoint is not a shared account order or global finance commit.

This **replaces event-triggered first-known T0+300 for the *new policy***; it does **not** preserve five minutes of minimum post-transition delay. A change immediately before a boundary can be acted on soon after that boundary, subject to proof, processing latency, quotes, risk and financial admission. A source round-trip within a five-minute interval may be invisible to the sampled policy. This is a strategy change requiring separately matched costed follower economics and prospective qualification; historical T+300 results are not equivalent.

A canonical checkpoint is not automatically an executable signal. A missing, stale, invalid or incomplete selected-account sample must not be read as a zero/flat position or a valid new-risk opportunity. Restart, reconnect, delayed samples and scope changes must not create retrospective source signals or reset a historical financial action. Protective reductions/HALT and existing follower financial exposure remain separately owned; exact behavior during missing samples and intrawindow reductions is pending Grill Round 2.

## Why this abstraction

The existing source-to-paper path schedules per-observed-transition T+300; `prop-production.v4_timing.V4ShadowProjection` separately schedules market-level T+300 eligibility. These implementations can diverge on local first-known time, coalescing and recovery. One checkpoint-state authority removes the *need for duplicated source timing*, not the need for independent Guardian verification and durable uncertain-broker-outcome recovery.

The alternative rejected for this *new policy* is to keep independent first-transition clocks for each consumer. The existing T+300 system remains a supported historical/current version until deliberately retired through a new contract and reversible release.

## Explicitly unresolved: next design frontier

- Sampling cutoff: exact UTC boundary versus bounded as-of window; evidence availability, latency and late arrival.
- Missing checkpoint/gap semantics: rebaseline, resumed changes, restrictions on inferred exits and new risk.
- Target-state signal identity and deduplication across source generations, portfolios, delayed/replayed observations.
- Changes in a sampled target versus independently held follower inventory, protective reductions, opposing positions and missed/existing orders.
- Provider evidence: official complete-position primary versus independently qualified Vike/hybrid (Q2 remains **OPEN**).
- Financial proof and release cutover: Guardian verifies signatures, complete scope, market/account finance and signed k; no execution permit from a source signal.

## Safety and migration constraints

No code, service, wire, source/financial journal, existing policy, signed release, tests or authorization is changed by this ADR. Do not reinterpret v1/v2 source receipts or old financial events under the new strategy; use a new policy/wire identity and explicit forward-only cutover. No retroactive alpha claim from historical fill timestamps. Missing external provider proof continues to block affected actions.
