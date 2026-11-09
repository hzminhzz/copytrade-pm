# ADR — Economic-state identity, latched safety, intent separation and durable delivery

**Date:** 2026-11-09
**Status:** Q9–Q13 **APPROVED FOR ARCHITECTURAL DESIGN**. No code implementation, schema migration, deployment, financial-policy amendment, or trading permission is authorized here.

**Prerequisites:** [Q3/Q4 migration guardrails](2026-11-09-pydantic-native-migration-guardrails.md); [Q5–Q8 typed ownership](2026-11-09-pydantic-native-contract-ownership.md); [V4 position-first T+300 authority](2026-11-08-position-first-t300.md).

## Context and evidence

Current selected-account observation logic in `pm_forward_source_stream.PersistentAccount.observe` compares string-valued native positions; raw `"20"` and `"20.0"` may be classified as a position change. Financial HALT can be overwritten by direct `risk = RED` assignments in the execution/journal paths. `pm_forward_observed_paper._known_instruments` may retain routed targets beyond terminal exit. The V4 spool publishes a newly-created final filename before bytes are complete; packet and cursor reside in separate filesystem publications. A single readiness status cannot distinguish source gaps, eligible wallets, unresolved follower exposure, scientific quality or Guardian authorization.

## Q9 — Economic-state identity is distinct from evidence identity (APPROVED)

- Keep original source bytes, receipt SHA, native event time and first-local-known time immutable and separately addressable.
- Derive prospective position changes from **validated, complete, scope-identical economic position books**, using exact finite Decimal quantities rather than formatting differences. `"20"` and `"20.0"` are one economic exposure. Nonposition metadata differences remain auditable but do not create new-risk intents.
- A source scope/census or selected-account identity change invalidates the prior continuity proof, requires a separately proven complete baseline, and never retrospectively creates a transition or invents a flat. Exact scope epoch policy remains a subsequent design question.
- A baseline, duplicate/unchanged frame, gap, repaired historical fill or unverified source-flat is not a new-risk transition. No first-known clock is backdated or restarted by non-entry updates.

## Q10 — Financial restriction is separate from transient readiness (APPROVED)

- Durable financial HALT and contractual breach latches must be monotonic across market-data failures, funding diagnostics, connectivity events and process restarts until an explicitly authorized, auditable reset.
- Readiness dimensions (e.g. quote health, source continuity, account reconciliation) may change without clearing a financial latch. GREEN/RED diagnostics never overwrite HALT.
- The safety policy may permit independently valid risk-reducing actions without reopening new-risk admission. Exact reduction prerequisites and recovery behavior are a later design question.
- Guardian retains an independent, non-inheritable protected HALT and risk authority; PM-03 changes do not reset Guardian.

## Q11 — Intent and financial inventory have different owners (APPROVED)

Separate **desired source exposure**, **pending paper intent**, **terminal modeled attempt**, **modeled follower holdings**, and **unresolved execution/exposure**. A routed target is not authoritative inventory.

- New-risk intents have at most one modeled market attempt under the existing exact first-known T+300 contract; do not convert rejection into unbounded target chasing.
- Actual modeled exposure and unresolved broker/paper states persist independently of a consumed intent.
- Verified reductions or protective stops can generate subsequent constrained risk-reducing attempts even after a terminal entry attempt; failures and incomplete/unknown outcomes stay visible and cannot be assumed flat.
- A fully reconciled terminal exit must not retain unrelated nonzero routed targets as a phantom market-price requirement.

## Q12 — Atomic local publication and idempotent at-least-once delivery (APPROVED)

- Treat the existing immutable journal as the evidence authority. A signed file packet must be fully written and fsynced under a private staging name, atomically published, and its directory fsynced **before** advancing the producer cursor.
- Crash recovery must distinguish staged/incomplete, published/unacknowledged, cursor-advanced, and consumer-committed states. Do not silently delete published evidence or import source history as first-known.
- Cross-filesystem/journal delivery may repeat packets. Consumers must verify signatures, stream identity, monotonic cursor/event IDs, digest and original clock, then commit idempotently before acknowledging effects. Duplicate evidence is acceptable; fabricated/lost intent or duplicate financial effect is not.
- Do **not** claim globally exactly-once delivery without a proven atomic authority covering producer and consumer. Exact failure-point recovery and cursor handoff remain design and test questions.

## Q13 — Independent readiness and qualification dimensions (APPROVED)

Keep **wallet eligibility**, **source observation continuity**, **market/quote validity**, **financial restriction**, **worker/transport health**, and **scientific qualification** as separately owned, typed facts. Derive capability-scoped admission deterministically rather than compressing all into `ACTIVE`/`GREEN`/`RED`.

- Healthy receipt collection does not imply completed follower economics or protected order authorization.
- A profitable wallet can be ineligible; an eligible wallet can have unqualified predictive edge; a financially HALTed account can still have fresh market data.
- Unknown, stale or unavailable evidence must not be converted into a positive permit. Any agent/evaluator can explain or recommend but cannot authoritatively override this admission logic.
- Conform to `prop-production/docs/CAPABILITY-SCOPED-READINESS-20261107.md` and its OBSERVE / PAPER SOURCE COLLECTION / PAPER FOLLOWER ECONOMICS / DEMO / LIVE distinctions.

## Rejected alternatives

- Use raw wire-string equality for position transitions.
- Represent all source, financial, research and worker statuses as one mutable enum.
- Clear HALT when transient data health improves.
- Treat desired/routed positions as proof that follower inventory is flat.
- Promise exactly-once global effects with separate filesystem and SQLite commits and no demonstrated transaction authority.
- Let a Pydantic schema or AI score itself grant risk admission.

## Consequences and next frontier

These are accepted **semantic requirements**, not completed fixes. Source scope change and process restart, bounded protective reduction, schema compatibility, and risk-weighted audit-family closure were subsequently approved for design in [Q14–Q18](2026-11-09-pydantic-native-recovery-and-compatibility.md). Pydantic input policies, error semantics, event serialization and implementation specifics remain open. Existing historical SHAs and signed release manifests are not to be silently rewritten.

See [the full 28-family ledger](../PYDANTIC-NATIVE-STATE-GRILL-20261109.md) and [domain glossary](../../CONTEXT.md).
