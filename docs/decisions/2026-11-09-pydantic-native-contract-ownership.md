# ADR — Pydantic-first domain contracts, reducers and ownership

**Date:** 2026-11-09
**Status:** Q5–Q8 **APPROVED FOR DESIGN**, pending exact interface and lifecycle semantics. This decision does **not** authorize application code changes, deployment, trade execution, or scientific qualification.

## Context

The November 9 28-family implicit-state audit found distributed lifecycle control in source observation, virtual-paper intents, PM-03 risk, durability, monitoring, historical research and browser tooling. The owner wants an extensible Pydantic-native foundation to support future Pydantic Graph, Evals, AI, Monty and Logfire where they earn their complexity, and prefers autonomous engineering rather than preserving old implementation details.

The independent [Q3/Q4 migration guardrails](2026-11-09-pydantic-native-migration-guardrails.md) and [V4 position-first T+300 ADR](2026-11-08-position-first-t300.md) remain binding.

## Q5 — Pydantic-first typed domain contracts (APPROVED)

Use Pydantic as the **default** for externally received domain records, cross-module domain events/results, configuration and policy contracts, and versioned inter-repository payload validation. This does not require converting every object to `BaseModel`: retain small dataclasses, plain Decimal math, Polars/DuckDB arrays and immutable internal structures when their interfaces are more precise and economical. Validation alone does not establish source authenticity, transition legality, event ordering or financial authority.

Reject the two extremes: Pydantic only at provider edges leaves unsafe cross-module interpretation; Pydantic on every internal class creates migration churn without increasing domain depth.

## Q6 — Typed events plus one deterministic transition owner per lifecycle (APPROVED)

Each consequential lifecycle must define legal states, transition events, temporal preconditions, deterministic decisions and explicit invalid-event behavior. One owner decides transitions; transport, CLI, UI and persistence adapters do not independently mutate its state. Reuse established PM-03/04 financial reducers and SQLite journals where proven rather than duplicate their authority. Pydantic validates contracts; a pure reducer owns behavior; an existing transaction owner persists results.

Pydantic Graph is **not** mandatory for all state machines: adopt it only for independently evaluated orchestration where it reduces interface burden and does not displace durable journals. Retain intentionally valid multidimensional state rather than forcing all dimensions into one enum.

## Q7 — Domain-owned versioned cross-repository contracts (APPROVED)

Do **not** create a single global Pydantic-model package shared by all repositories. `trading-connector` owns provider normalization; `copytrade-pm` owns source evidence admission, research, paper intents and simulated finance; `prop-production` Guardian owns protected permits, reconciliation and broker execution. Exchange explicit versioned payload schemas and test cross-repository consumer compatibility. A shared type import alone is not an authorization contract.

No new wallet registry, event database, independent financial ledger or broker route.

## Q8 — Evidence-based legacy retirement (APPROVED)

For each of the 28 audit families select `FIXED`, `EXPLICIT-AND-VERIFIED`, `RETIRED-NOT-REACHABLE` or `DOCUMENTED-INTENTIONAL`. When a legacy path has no installed runtime consumers, supported research/backtest contract, or unique invariant, prefer retiring it to rebuilding it in Pydantic. Preserve immutable historical data and required archived-replay interfaces. Prove reachability with code, CLI entrypoints, installed release manifests and tests before deletion.

## Consequences and open frontier

- Strong typing concentrates input interpretation and makes later ecosystem extensions feasible, but does not remove all risk or justify a framework rewrite.
- Source, paper, finance, registry and Guardian continue to have distinct authority boundaries.
- Q9–Q13 are now **APPROVED FOR DESIGN** in [the state-semantics ADR](2026-11-09-pydantic-native-state-semantics.md): economic vs evidence identity, latched HALT independent of readiness, desired/pending/attempted/actual exposure, durable at-least-once publication, and independent status dimensions. Details of restart/scope, reduction retries and schema upgrade compatibility remain open.
- No classes, schemas, code paths, tickets, or running services have been changed as a result of this design approval.

Track all 28 in [the design ledger](../PYDANTIC-NATIVE-STATE-GRILL-20261109.md).
