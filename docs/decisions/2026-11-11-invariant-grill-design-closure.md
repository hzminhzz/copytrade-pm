# Invariant grill — design closure and implementation acceptance map

**Date:** 2026-11-11
**Status:** ARCHITECTURAL DESIGN SETTLED across owner-approved Q1–Q33, recorded in the five linked ADRs. **IMPLEMENTATION NOT STARTED BY THIS GRILL.** This document is a read-only specification-readiness map, not a release, independent scientific result, executable artifact, trading permit or request for another approval round.

## One higher-level abstraction

**A proof-carrying, domain-owned transition** separates three concerns that have previously been confused:

1. **What was observed?** Original authenticated evidence, independently verifiable source/account/provider identity, timestamp, scope, chain/cursor and immutable content.
2. **What decision is justified?** A causal, versioned eligibility/risk decision using only first-known/as-of input, original T+300 policy, independent marks, frozen k, and the applicable consumer's own preconditions.
3. **What actually changed?** Exactly one owner-bound local durable effect, rejection or unresolved disposition with replay identity, checked economic invariants, and explicit outstanding risk.

Research source evidence can make a prospective opportunity **eligible**; it cannot commit a protected financial intent or grant a broker permit. Paper effects are committed by PM03/PM04. Protected finance is committed only by prop-production Guardian. Each local journal has its own atomic transaction and cursor; **no global distributed transaction** is promised. Pydantic expresses strict boundary schemas; existing SQLite journals supply durability; the existing source producer supplies original provenance. Prefect remains optional for bounded offline research, not authority or the live event hot path.

This is a **shared set of semantic constraints**, not a mandate to implement a central service, global state machine, cross-repository shared Pydantic class, universal receipt type or a redundant approval framework.

## Eight residual audit findings — four ownership seams

| Findings | Root seam | Required verifiable outcome | Actual owner |
| --- | --- | --- | --- |
| F01 | Independent price/provenance | Fixed-k uses source native notional with authentic leader mark and distinct follower quote; missing evidence fences new risk | copytrade-pm sizing and observed paper |
| F02, F08 | Authenticated source transition | Signed predecessor-bound v2 events; expected cursor/head checked inside local transaction; wrong order and concurrent writers cannot skip | copytrade-pm producer + prop-production protected receiver |
| F03, F04, F05 | Protected financial transition | Guardian commits semantically valid reservations/fills and HALT recovery; provider terminality and signed recovery request never substitute for independent financial proof | prop-production Guardian/gateway/journal |
| F06, F07 | Local effect/delivery boundary | Deterministic per-consumer effects after crash; independent wallet quarantine; packet COMPLETE versus RESOLVED_WITH_QUARANTINE never misreported | copytrade-pm paper + prop-production source receiver |

F02 was inferred from a stale pre-transaction read and requires a verified concurrent race test; no exploited runtime race has been established. F06 is a cross-database atomicity limitation, not something to solve with an imaginary global lock. F07 partial progress is intentional when explicitly and durably represented.

## Minimal implementation-proof contract

For each owner, demonstrate:
- **Safety:** malformed, stale, forged, conflicting, out-of-order and cross-scope evidence cannot produce a newly authorized effect.
- **Causality:** original T0, signed chain and consumed source head are not rewritten by replay, restart, correction or new market data.
- **Economic conservation:** original account/intent/execution/cumulative fills/reservations and risk latches remain consistent, with unknown outcomes retained.
- **Idempotence:** at-least-once delivery and local transaction failure yield no duplicated consumer effect, order or invented recovered opportunity.
- **Fault isolation:** account-scoped broker financial failures and independently attributable wallet source faults fence only correct dependents; shared trust failure fences all its dependents.
- **Compatibility:** original signed v1 evidence remains verifiable under its own version; v2 starts with signed prospective head anchor and no downgrade.
- **Reversibility:** commit-bound compatible code rollback does not rewind ledger, original evidence, financial effect, HALT or signer trust floor.

Use the risk-weighted adversarial cases approved in Round 5 and the **existing native acceptance gates**. Reuse original 28-family test evidence only where the scenario is genuinely identical; no passing test count from old revisions substitutes for newly tested code. No network I/O in a protected journal SQL transaction. Keep all first-known/fill/decision times distinct.

## Engineering and release sequence — a program, not repeated owner votes

1. **Inspect and freeze facts:** current commit/pins/services, authentic source-mark age distributions, preserved journals and broker API limitations, baseline costs and disk/WAL. This is fact retrieval, not a new design grill.
2. **Implement source truth:** independent source-mark evidence, signed prospective source predecessor/anchor, verified cursor ownership and packet quarantine; keep source observation read-only.
3. **Implement destination effects:** causal idempotent paper effect; separately normalize broker statuses, semantic Guardian commits/replay and independently verified scoped recovery. Never promote paper accounting to Guardian authority.
4. **Verify engineering:** focused adversarial/regression/combined-fault tests, exact clean cross-repo manifest and negative guards; economic before/after frozen-k comparison retains original historic evidence without claiming alpha.
5. **Separately authorize operational SHADOW:** staged pinned source-only canary with genuine post-baseline events, repeat/restart/gap tests and measured resource budgets. Do not infer deployment acceptance from a PR merge.
6. **Keep protected finance and trading independent:** authentic reconciled account/history, Guardian permit and risk contract, future-effective signed release, independent science and explicit real-broker authorization remain separately gated.

No step automatically begins or grants the next. A safe code merge may occur without impossible future economic evidence; a protected active policy change cannot.

## Factual unknowns and bounded follow-up, NOT new architecture questions

- Authenticated per-native-market leader-mark age/cadence and genuinely independent follower executable quote provenance; there is no approved arbitrary max age or fallback instrument list.
- Real coherent provider history cutoff, terminal order/fill semantics, account cash/equity/provenance and permission, especially for Propr and Bybit.
- Current root-owned signer/key pins and revocations, source v2 cutover anchor and backward-compatible installed bundle identities.
- Measured SQLite event rates, WAL growth, lock contention, retry bounds, quarantine retention, backlog and recovery under actual VPS load.
- Reproducible before/after net follower economics from genuine matched causal opportunities. Engineering tests and historical simulations do not establish economic qualification.
- Actual deployment and service revision at operation time; dated source docs are not proof of a running PID.

The implementation/spec owner may turn these into **bounded measurable tasks and fail-closed defaults**, including versioned limits, without another cosmetic grill. Any material new risk threshold, protected release or trading permission still requires its existing legitimate authority. Until measured/attested, the corresponding risk-increasing operation remains blocked.

## Documents and authority links

- [Round 1: invariant ownership](2026-11-11-invariant-enforcement-grill-round1.md)
- [Round 2: trusted reconciliation](2026-11-11-invariant-enforcement-grill-round2.md)
- [Round 3: scoped failures](2026-11-11-invariant-enforcement-grill-round3.md)
- [Round 4: contract and economic migration](2026-11-11-invariant-enforcement-grill-round4.md)
- [Round 5: adversarial acceptance and reversible release](2026-11-11-invariant-enforcement-grill-round5.md)
- Existing [Nov 9 Pydantic-native acceptance](../PYDANTIC-NATIVE-ACCEPTANCE-RESULTS-20261109.md), [position-first T+300](2026-11-08-position-first-t300.md), [merge vs runtime promotion](2026-11-10-merge-vs-runtime-promotion.md) and protected prop-production compatibility/deployment/verification documents.

**Design frontier: CLOSED for this problem statement.** Implementation, acceptance and operational state remain unverified for the new findings. No implementation, push, merge, deployment or order action has been authorized.
