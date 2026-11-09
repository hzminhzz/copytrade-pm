# ADR — Pydantic-native redesign: compatibility and migration guardrails

**Date:** 2026-11-09
**Status:** Q3/Q4 **APPROVED FOR ARCHITECTURAL DESIGN**; subsequent Q5–Q39 design decisions are approved in the linked ADRs and summarized in [the design closure report](../PYDANTIC-NATIVE-DESIGN-CLOSURE-20261109.md). Implementation and deployment remain **NOT AUTHORIZED**. **No implementation, merge, installation, service cutover, or trading authorization** follows from this ADR.

## Context

The November 9 implicit-state audit classified 28 nontrivial lifecycle families in `copytrade-pm`. Multiple existing interfaces pass dictionaries, strings, and mutable flags between official-source observation, virtual paper, evidence persistence, financial accounting and monitoring. User wants maximum autonomous engineering throughput and a Pydantic-native foundation for potential future Graph/Evals/AI/Monty integration, without requiring the user to write code.

The **position-first V4 ADR** (`2026-11-08-position-first-t300.md`) remains authoritative: selected official complete positions, first-known time, one T+300 attempt, immediate source/risk reductions, independently verified evidence, PM-03/04 financial accounting, and Guardian's separate protected authorization.

## Q3 — Approved versioned internal redesign

Allow incompatible internal type, interface, module and lifecycle changes to remove defects, duplicated interpretation, legacy paths and invalid state combinations. Do not require byte-identical behavior of known-defective internal logic. Explicitly version substantive forward-behavior corrections and ensure tests demonstrate the intended new semantics.

Non-negotiable invariants:
- Preserve original raw evidence bytes, SHA identities, historic records and distinct source/receive/decision/execution clocks; never reserialize old evidence as if it were original.
- Preserve first-known **T+300** from a genuine post-baseline official selected-position transition, with no reset from intermediate updates or reconnects. A baseline, gap or retrospective fill cannot create a new entry.
- Preserve fixed-k and PM-03/04 portfolio risk, durable HALT, unresolved positions, price freshness, one-shot intent semantics, and independent follower equity/limits.
- Preserve separation from `prop-production` Guardian's protected finance and broker/order authority. No research approval becomes trading authorization.
- Preserve genuine immutable SQLite/source journal provenance. Do not silently backfill first-known information or replace official position authority with Vike fills.

Compatibility to existing historic journal schemas and exact public serialization requires explicit migration design. Do not infer that Pydantic validation itself provides persistence, authorization, financial risk controls or durable state transitions.

## Q4 — Approved autonomous incremental replacement

An agent can conduct the entire separately authorized engineering program: inspect current Git/OS evidence, derive bounded-context work units, implement in isolated worktrees, test invariants, repair ordinary failures, review diffs and complete routine code integration. No recurring per-class or per-ticket human coding approval is needed.

Use focused contract, adversarial, replay and crash tests as appropriate. Reuse existing transactions and source finance authorities. Prefer a coherent one-lifecycle replacement and deletion of redundant old paths to a parallel architecture maintained indefinitely.

A merge is not a deployment; a deployed revision is not trading-authorized or scientifically qualified. Reversible cutover and rollback procedures must be verified. Scope-changing production deployments, financial-policy/risk changes, irreversible data operations and funded/broker trading remain subject to their existing explicit authorization and independent review.

## Alternatives rejected for Q3/Q4

- Preserve all old implementation behavior and state hashes, including known defects.
- Replace the entire repository in one big-bang V5 rewrite before validating individual seams.
- Maintain old/new parallel logic indefinitely solely to match broken behavior.
- Treat unit tests or simulations as proof of actual execution or scientific profitability.
- Delegate coding to other agents by default rather than having ChatGPT directly execute requested implementation.

## Consequences

This is permission to design a more coherent typed architecture, **not** a choice of Pydantic Graph, Monty, Evals, or AI. The migration will require consciously versioned internal contracts, focused safety tests and independently reviewed financial cutover constraints.

All 28 families must receive a documented, testable disposition. Retained explicit reducers and retired unsupported legacy paths count as resolved when their ownership/semantics and absence of live dependencies are verified. A new framework is not itself evidence of closure.

Track all family dispositions in [the 28-family design ledger](../PYDANTIC-NATIVE-STATE-GRILL-20261109.md). Subsequent Q5–Q39 choices settle Pydantic-first contracts, deterministic reducers, source/finance authority, HALT, causal timing, persistence, ecosystem staging and failure/canary rules. [The design closure report](../PYDANTIC-NATIVE-DESIGN-CLOSURE-20261109.md) distinguishes settled architectural policy from read-only S0 fact checks and incomplete engineering execution.
