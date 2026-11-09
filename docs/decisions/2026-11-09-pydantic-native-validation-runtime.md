# ADR — Pydantic domain validation, evidence preservation, and runtime isolation

**Date:** 2026-11-09
**Status:** Q19–Q24 **APPROVED FOR ARCHITECTURAL DESIGN**. Do not implement, install dependencies, migrate data, commit, merge, cut over or deploy from this ADR.
**Depends on:** [Q3/Q4 redesign guardrails](2026-11-09-pydantic-native-migration-guardrails.md), [Q5–Q8 typed ownership](2026-11-09-pydantic-native-contract-ownership.md), [Q9–Q13 state semantics](2026-11-09-pydantic-native-state-semantics.md), [Q14–Q18 recovery and compatibility](2026-11-09-pydantic-native-recovery-and-compatibility.md), and [V4 first-known T+300](2026-11-08-position-first-t300.md).

## Context / actual code

`src/copytrade_pm/pm_e4_prospective.py` consumes native decimal strings and publishes string-valued positions; `pm_forward_source_stream.PersistentAccount.observe` compares those strings. `pm_forward_stream_journal.py` verifies original raw SHA and a versioned canonical JSON journal. `pm_forward_journal.PaperJournal` owns SQLite writer locks and local financial transactions. `pyproject.toml` currently has no Pydantic dependency. A Pydantic-specific domain layer must **not** take ownership of the raw signatures, journal, protected Guardian, or account finance.

## Q19 — Strict domain validation with explicit provider conversion (APPROVED)

- Source-adapter parsing is the sole permitted conversion seam: accept documented finite native number strings such as `"20"` and `"20.0"` into exact Decimal economic values. Do **not** use `float` round trips or implicit assumptions about market precision.
- Normalize only the *economic projection*; preserve raw received bytes and all attached SHA/signature fields without modification. Decimal representation equality and stable instrument/account identity determine economic position equality.
- Internal domain contracts are strict about types, required fields, account/subaccount and native DEX/market identity, complete selected scope, monotonic clocks and input provenance. Financial/authorization schemas must reject unknown critical fields. A provider envelope can retain unrecognized raw diagnostics separately; it must not silently reinterpret them as permitted financial meaning.
- Reject NaN/infinity, booleans as financial numbers, inappropriate negative values, ambiguous timezone/naive clocks, duplicate instruments, unknown native market identity and invalid scope. Provider-specific exceptions must be explicit and tested; no blanket permissive coercion.

## Q20 — Typed evidence-validation outcomes, not implicit authorization (APPROVED)

Use disjoint semantics for **VALID**, **INVALID**, **INCOMPLETE**, **STALE**, **UNSUPPORTED_VERSION**, and **TEMPORARILY_UNAVAILABLE**. They are *contract/evidence diagnostics*, not final trading or scientific verdicts. A valid contract continues through separate transition, continuity, admission, risk and Guardian checks; it grants no permit. Distinguish deterministic invalid evidence from retriable transport failure. Never convert an unavailable or unknown field into zero/flat/approved.

## Q21 — Immutable wire/evidence identity versus derived model serialization (APPROVED)

- SHA/signature verification applies to the original source/evidence wire and its already-established canonical serialization rules. Do not invoke Pydantic `model_dump` or `model_dump_json` to recompute old source signatures or rewrite journal history.
- New domain schemas are versioned derived contracts with explicit consumer support, compatibility pins and separately verified migrations. Historical versions must remain readable at their original meaning where required.
- Changes to future event contracts are separately versioned. Document changed behavior instead of adjusting archived hashes or retconning first-known clocks.

## Q22 — Pure reducer plus existing transactional owner (APPROVED)

Boundary adapter validates input -> single deterministic domain transition owner assesses event -> returns typed state change, rejection reason and **proposed effect intents** -> the existing journal authority commits local state/effects atomically -> separate dispatcher performs external I/O after commit -> idempotent acknowledgment/reconciliation. Do not introduce a second event store, financial ledger, network I/O in SQLite transactions, automatic retry of unknown financial outcomes or a Pydantic model with hidden stateful side effects.

A typed invalid transition must be a no-op for financial authority except for an explicit, separately committed diagnostic/quarantine event. Replay of committed events must not create a new T0, second financial effect or cleared HALT.

## Q23 — Minimal core dependency and performance boundary (APPROVED)

- Introduce narrowly pinned **Pydantic Validation** into core at the selected domain interfaces *when implementation is separately authorized*. Settings, Graph, AI, Evals, Monty and Logfire remain optional, separately pinned and context-isolated; do not install them from this ADR.
- Keep Polars/DuckDB/parquet columnar research, deterministic Decimal arithmetic, and hot-loop replay as their own implementations. No per-row `BaseModel` construction across millions of bars merely for framework consistency.
- Baseline/benchmark provider ingress, model validation, replay throughput, peak RSS, imports and cold start before setting performance budgets. Guard against regressions that materially impair source freshness or observer shared-IP budgets.

## Q24 — Evidence-based Pydantic ecosystem adoption (APPROVED)

A proposed plugin/stack must have a concrete existing workflow, authority owner, measurable acceptance test, optional runtime isolation and opt-in deployment/rollback. It must not become new policy/ledger/evidence/Guardian authority:

- **Pydantic Settings**: candidate when consolidating fragmented runtime configuration; never distribute or log secrets.
- **Pydantic Graph**: candidate for nonfinancial research orchestration after comparing with a small pure reducer; do not substitute transient graph state for durable journals.
- **Pydantic Evals**: candidate for audited research-agent correctness (wallet diagnostic reasoning, abstention, tool-call provenance), **not** economic alpha.
- **Pydantic AI**: candidate for agent investigation/recommendation, not new-risk admission or broker mutation.
- **Monty**: candidate only when untrusted model-authored Python is necessary, with host-capability restrictions, private evidence isolation and no broker/signer tools; not Polars/CPython replacement.
- **Logfire**: optional traces via an explicitly secured telemetry route; retain existing Grafana as operator display, protect private wallet/account information.

## Alternatives considered and rejected

1. Permissive system-wide coercion instead of explicit provider-specific conversion.
2. A single generic exception representing invalid evidence, stale quotes, transient outages and unsupported financial schemas.
3. Recompute historical source SHA using new `model_dump` serialization.
4. A second generic event bus/state store or Pydantic model that commits financial state by itself.
5. Add every Pydantic ecosystem dependency and convert columnar dataframes to models immediately.
6. Treat agent evaluation scores as broker authorization or positive follower economics.

## Consequences and next frontier

Q19–Q24 settle **what** the model/effect boundary must preserve. Subsequent [Q25–Q29](2026-11-09-pydantic-native-sequencing-ecosystem.md), [Q30–Q34](2026-11-09-pydantic-native-domain-interfaces.md) and [Q35–Q39](2026-11-09-pydantic-native-failure-and-spec-readiness.md) decisions settle migration priority, semantic-difference oracles, canary evidence, interface ownership and specification readiness; measured performance thresholds remain read-only S0/baseline engineering facts. See [28-family ledger](../PYDANTIC-NATIVE-STATE-GRILL-20261109.md), [acceptance matrix](../PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md), and [proposed migration roadmap](../PYDANTIC-NATIVE-MIGRATION-ROADMAP-20261109.md). All 28 families remain unresolved until implementation/reachability proof is produced.
