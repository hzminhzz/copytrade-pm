# ADR — Pydantic-native migration sequencing, semantic oracles, canaries, and optional ecosystem

**Date:** 2026-11-09
**Status:** Q25–Q29 **APPROVED FOR ARCHITECTURAL DESIGN**. No code implementation, dependency installation, commit, merge, runtime service modification or deployment is authorized by this ADR.

**Prerequisites:** [Q3/Q4 redesign guardrails](2026-11-09-pydantic-native-migration-guardrails.md), [Q5–Q8 domain ownership](2026-11-09-pydantic-native-contract-ownership.md), [Q9–Q13 state semantics](2026-11-09-pydantic-native-state-semantics.md), [Q14–Q18 recovery/compatibility](2026-11-09-pydantic-native-recovery-and-compatibility.md), [Q19–Q24 validation/runtime](2026-11-09-pydantic-native-validation-runtime.md). The approved official-position T+300 contract in [V4 position authority](2026-11-08-position-first-t300.md) remains binding.

## Context

The November 9 review of `copytrade-pm` at `175d54d` found a direct source-position identity seam, multiple financial risk writers, a signed packet publication/cursor seam, and established PM-03/04 SQLite authority. We must resolve 28 audited implicit state-machine families with fewer conflicting owners. The design is for autonomous implementation by ChatGPT when explicitly authorized, not for a human operator to write or coordinate code.

## Q25 — First vertical migration and emergency safety order (APPROVED)

Prefer a **complete vertical** `RawOfficialEvidence → ScopedCanonicalPositionBook → ObservedEconomicTransition → durable receipt` over creating a model package in isolation. Restrict each slice to one authoritative lifecycle; migrate all active callers through the new interface, then remove shadowing conditional logic. First migration scope includes economic Decimal equality, exact account/native DEX identity, baseline/duplicate/gap semantics, first-known timing, and raw-SHA-bound original journal commits.

**Exception:** A newly verified reachable financial HALT downgrade or equivalent protected risk defect should be fixed in an independent expedited safety slice rather than waiting behind unrelated Pydantic work. It must preserve existing accounting, consent boundaries and restart behavior; do not conflate safety repair with permission to deploy or change risk policy.

Stage assignments S0–S5 remain a proposed engineering roadmap pending final interface and acceptance design. Executing stages or repinning companions requires separate authorization.

## Q26 — Two behavioral comparison oracles (APPROVED)

Use **old/new differential replay** for semantics that should remain unchanged (e.g., recorded hash, first-known source clock, settled financial ledger, invalid account identity). For intentionally corrected defects, a **separately specified invariant oracle** takes precedence over the old program's incorrect output. Record each intentional semantic difference with scenario, old result, new expected result, rationale, affected historical/forward consumers, and version/migration implications. A failure to match a known defect is a desired difference, not a regression.

The test oracle must not be the same source reducer code under test. No retrospective event may be retimed or reclassified as prospective to make a test pass. Existing signed history remains verifiable even when future transitions are classified differently.

## Q27 — Limited SHADOW source canary and separately authorized rollout (APPROVED)

Keep **implementation**, **engineering verified**, **merged**, **installed**, **genuinely forward-observed**, **scientifically qualified**, and **trading authorized** as independent statuses.

Following separately authorized implementation, verify one bounded, source-account/portfolio-scoped, read-only/virtual-paper canary before rolling out the change to all **16** independent paper portfolios. Prove authentic after-baseline source transition, first-known T0→T+300, one-shot modeled new-risk attempt, verified reductions, distinct simulated inventories, signed identity/scope, handling of reconnect/gap, and durable rollback without historical journal rewind. Synthetic tests do not substitute for genuine forward evidence. There is **no automatic broker, demo or funded order route**. No irrelevant multi-month soak gate is imposed merely for a read-only/paper source upgrade.

This ADR does not itself authorize the canary installation or service cutover. Rollback must be limited to the separately approved installation scope and must retain immutable evidence.

## Q28 — First optional Pydantic ecosystem experiment (APPROVED)

After the core typed-domain layer is stable, prefer an **offline, read-only Pydantic Evals** investigation of wallet-monitoring reasoning (withdrawals, inactive traders, liquidations, observed equity changes vs actual follower edge decay). Use independently annotated time-appropriate cases, tool trace evidence, an explicit abstention/unknown option, and error analysis. These evaluations test **agent diagnosis**, not executable follower net PnL or owner-signed portfolio selection.

Keep Pydantic Graph and AI elective until orchestration/agent workflows demonstrably justify them, Settings elective until configuration duplication warrants it, and Monty deferred pending a specific untrusted-program need and independent host-capability security review. Prefect may be researched separately as a scheduler, never as a state/evidence/finance authority. No model service is allowed inside the mandatory source decision or Guardian financial critical path.

## Q29 — Retain Grafana as operator display; constrain telemetry (APPROVED)

Existing Grafana remains the sole operator presentation. Expose bounded, scrubbed state-transition counts, freshness, error categories, lag, sequence/restart metrics, and scientific-vs-financial capability statuses. An optional Logfire/OpenTelemetry diagnostic pilot must explicitly prove privacy/secret safety for source account identifiers, private signed envelopes, release keys, positions and protected financial details before any external export. No new telemetry system may become a financial journal or authority for decisions.

## Alternatives rejected

- A big-bang all-models conversion before a real source transition slice.
- Blind parity with known buggy behavior as a migration acceptance oracle.
- Direct mass migration of all sixteen paper ledgers before a bounded real source canary.
- Mandating Pydantic Graph, AI, Monty, Logfire, Settings, or Prefect for core observer correctness.
- Replacing Grafana with multiple independent operator consoles during domain refactoring.
- Using successful engine tests or agent diagnostic evals as evidence of trading authorization or positive net follower returns.

## Consequences and next decision frontier

Approved architecture retains [all-28 acceptance matrix](../PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md), [staged migration roadmap](../PYDANTIC-NATIVE-MIGRATION-ROADMAP-20261109.md), [audit disposition ledger](../PYDANTIC-NATIVE-STATE-GRILL-20261109.md) and the [domain glossary](../../CONTEXT.md). The later [Q30–Q34 domain interface ADR](2026-11-09-pydantic-native-domain-interfaces.md) and [Q35–Q39 failure/specification ADR](2026-11-09-pydantic-native-failure-and-spec-readiness.md) settle those design questions. Nothing is implemented or accepted as scientifically qualified solely by this ADR.
