# ADR — Restart fencing, scope generations, protective reductions and compatibility

**Date:** 2026-11-09
**Status:** Q14–Q18 **APPROVED FOR ARCHITECTURAL DESIGN**. Not implementation, schema migration, merge, deployment or trading authorization.

**Prerequisites:** [Q3/Q4 migration guardrails](2026-11-09-pydantic-native-migration-guardrails.md), [Q5–Q8 contract ownership](2026-11-09-pydantic-native-contract-ownership.md), [Q9–Q13 state semantics](2026-11-09-pydantic-native-state-semantics.md), [position-first V4 T+300](2026-11-08-position-first-t300.md).

## Context and evidence

The existing `PersistentAccount.begin` creates a GAP and new epoch and requires a subsequent baseline. V4 journals retain first-known receipts. Signed packets and spool cursors are separate filesystem publications. Multiple portfolios can share selected source accounts while holding separate simulated inventory. `prop-production/src/prop_production/compatibility.json` already pins companion commits and versioned wire contracts. The 28-family implicit-state audit identified heterogeneous risk; not every finding needs a new reducer.

## Q14 — Crash/restart and replay (APPROVED)

- A process crash or source continuity interruption **does not** create a position change, a revised first-known clock, a simulated close or renewed authorization.
- Preserve committed source events, source/local/decision/execution clocks, pending-intent history, actual simulated holdings and durable risk/HALT latches across restart.
- If continuity cannot independently be proven across the interruption, fence new-risk admission, invalidate pending pre-interruption entries, and establish a fresh complete selected-account baseline. The baseline never starts T+300.
- Resume a still-pending existing new-risk intent **only if** independently complete prospective continuity is established across its entire original observation interval, the original T0 and source/portfolio scope remain valid, and the original one-attempt policy has not been consumed; otherwise cancel it without creating replacement T0.
- Idempotent event replay must not duplicate first-known evidence or model a second financial effect. Reconciliation of unresolved holdings/outcomes must not be mistaken for a fresh source observation.

**Concrete counterexample:** A selected position is first known at T0; worker fails at T0+180; reconnect at T0+360 shows same position. Without proved uninterrupted continuity, no late entry is authorized just because T+300 elapsed.

## Q15 — Selected account and scope generations (APPROVED)

- Identify each selected parent/child and complete native perp scope by its independently authenticated account identity, explicit DEX/market census and versioned scope generation.
- Identity, relevant DEX membership or materially changed scope/contract semantics breaks prior continuity for the **affected** selected account; fence that account's new entries and require a separately verified complete baseline.
- Do not infer flat from disappearing positions or from a new scope; preserve follower financial holdings and any unresolved exits under their separate authority.
- An unrelated new exchange listing does not change the semantic identity of an unchanged selected contract. A global outage or shared feed integrity failure can still fence a wider set when warranted; targeted fencing is not permission to ignore shared dependencies.
- Shared source-account invalidation propagates to every dependent paper pod/portfolio without rewriting unrelated selected accounts, active ledgers, or historical research data.

## Q16 — Risk-reducing actions during HALT and outages (APPROVED)

- Financial HALT stops **new risk**, remains durable and separate from source/market readiness; it does not erase owned exposure or imply that all risk-reducing actions are forbidden.
- A verified source reduction, protective loss stop or separately authorized safety policy may request a constrained **risk-reducing** action. It must use independently valid inventory, exposure direction, and required current execution evidence; it cannot increase worst-case gross/position risk by misclassifying an unknown outcome.
- A source gap **alone** cannot justify an assumed flat or uncontrolled forced close. Without needed market/account/order evidence, keep the attempt blocked/unresolved and surface remediation; do not fabricate a fill, price, or cleared reservation.
- Protective reductions are a different lifecycle from the **single market attempt at exact first-known T+300 for new risk**. They may have bounded, idempotent retry/reconciliation semantics; unknown dispatch outcome is neither a confirmed failure nor an automatic invitation to submit another attempt.
- Protected Guardian risk/authorization, broker order/outcome authority and broker permissions stay independent of paper-research simulation.

## Q17 — Repository-owned schema compatibility (APPROVED)

- Keep Pydantic models owned by their authority: provider/transport in `trading-connector`, research/observed-source/paper in `copytrade-pm`, permits/financial execution in `prop-production`. Avoid a global shared Pydantic package or imported class identity as a trust root.
- Exchange explicit versioned **wire** schemas and stable semantic contracts. Changes affecting source account identity/scope, event clocks, quantity, signatures, financial risk, permits or order identity must fail closed unless a consumer explicitly supports that version and semantics.
- Pin and verify the **existing** Guardian compatibility manifest, concrete companion commits, signed provenance and consumer contract tests; do not introduce a second compatibility authority.
- Historical signed records and SHAs stay byte-stable. Any new schema representation must be a separately versioned derived interpretation rather than a silent history rewrite.
- Compatible additive diagnostics may evolve independently only when their optionality and nonfinancial status have been explicitly specified and tested. Exact version-negotiation and supported upgrade windows remain an implementation-design question.

## Q18 — Risk-weighted proof of all 28 dispositions (APPROVED)

- All 28 audited families require an individually recorded **FIXED / EXPLICIT-AND-VERIFIED / RETIRED-NOT-REACHABLE / DOCUMENTED-INTENTIONAL** disposition with identifiable code, tests or reachability evidence. Audit classification and proposed migration are not proof of closure.
- Financial/source-critical families: causal observation and transition tests; order/fill/cancel races; HALT monotonicity; fault injection; restart and replay. A failed safety invariant prevents the affected engineering promotion.
- Persistence/inter-repo families: prove publication/fsync order, cursor replay, idempotent commits, crash-recovery and schema pin compatibility. No network call inside a financial journal transaction.
- Monitoring/research families: relevant status transitions, negative evidence and consumer integration tests; avoid high-cost unrelated ceremonies.
- Legacy retirement: inspect code callers, CLI/scripts, pinned installed releases and reproducible historical consumers before deletion. Preserve archival contracts and prove removed paths unreachable.
- Scientific follower alpha, live order permission, actual deployments and financial policy changes remain separately evaluated/authorized. Engineering green never silently promotes any of them.

## Alternatives rejected

- Resume due new-risk entries from any reconnect baseline or unverified time gap.
- Restart all source identities merely because one selected DEX scope changed; or silently assume missing positions are flat.
- Treat HALT as clearing exposure, or retry unknown broker orders without reconciliation.
- Install a global Pydantic model package as cross-repository authority, auto-accept unknown financial fields, or repin existing Guardian compatibility state without consumer checks.
- Require blanket exhaustive rewrites of all 28 families or mark a documented design as a completed fix.

## Consequences and remaining decisions

The above are **semantic guards**, not a finalized implementation interface. They establish the proof obligations for [the 28-family ledger](../PYDANTIC-NATIVE-STATE-GRILL-20261109.md). Q19–Q24 subsequently approved those dependency-ready semantics in [Pydantic validation/runtime boundaries](2026-11-09-pydantic-native-validation-runtime.md): strict provider normalization, typed evidence errors, immutable wire hashes, pure reducers, existing journal transactions, minimal core deps and optional ecosystem adoption. Stage ordering, correction-oracle semantics, release canary and the first ecosystem pilot were subsequently decided in [Q25–Q29](2026-11-09-pydantic-native-sequencing-ecosystem.md). [Q35–Q39](2026-11-09-pydantic-native-failure-and-spec-readiness.md) subsequently approve failure quarantine, consumer ownership and specification readiness; implementation remains unperformed.

No code, released package, SQLite or service was modified.
