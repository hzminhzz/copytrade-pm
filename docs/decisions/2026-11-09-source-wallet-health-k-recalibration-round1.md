# ADR — Pydantic-native source reliability, wallet-health facts, and risk-budgeted k recalibration

**Date:** 2026-11-09  
**Status:** **Q1–Q3 APPROVED FOR ARCHITECTURAL DESIGN by owner** in Grill With Docs Round 1. These are architectural commitments, **not implementation, schema migration, commit, merge, service change, scientific promotion, or trading authorization**. The decision tree remains open.  
**Repository baseline inspected:** `copytrade-pm` `origin/main=6c07cc6d36099135881be27a072c426a52a24f24`, in an isolated read-only-derived DevSpace worktree. Dated runtime observations do not override future live checks.

## Context and evidence

The existing 16-portfolio Pydantic-native V4 SHADOW consumer reads one official source journal for 14 selected parent accounts; it maintains 16 separate simulated PM03/PM04 account ledgers. The installed `copytrade-v4-sixteen-source-0911.service` was observed active with **24 cumulative restarts**, most recently failing through `PaperJournal._writer()` with `PAPER_JOURNAL_BUSY_OR_UNAVAILABLE`. The Pydantic 16-portfolio consumer's SQLite BUSY retry does **not** repair that source producer. The original live ACT10 change was correctly canceled on a source GAP before T+300; it was not a successful 16-campaign entry. See [the rollout evidence](../PYDNATIVE-V4-SIXTEEN-SHADOW-20261109.md).

In current code, `pm_forward_journal.PaperJournal._writer` acquires a nonblocking filesystem lease, opens a SQLite connection with a one-second wait, configures WAL/FULL, and maps both lease failure and SQLite OperationalError to the same diagnostic. `pm_forward_continuous_transport.SerialWriter` marks that error as a lifetime failure. The **exact contention mechanism/owner is UNKNOWN** from the available wrapper and service trace; do not label it SQLite lock starvation or blame a particular reader without additional evidence.

The [fixed-k policy](../RISK-BUDGETED-K-SIZING-20261106.md) does not require leader whole-wallet NAV. The selected account's complete native perp position book, verified follower risk and a frozen per-pod k are separate from wallet eligibility and strategy quality. The [Pydantic wallet-health Evals pilot](../../experiments/pydantic_wallet_health/README.md) has synthetic accounting cases, **not** independently validated real-wallet edge-decay labels. The current 16-scenario campaign contains separate paper-only research k derivations; it is not a general automatic k release system.

## Q1 — Repair the existing source writer, not replace its persistence authority (APPROVED)

- **Keep the existing official selected-account position evidence and SQLite PaperJournal as the durable source/stream checkpoint owner.** Prefer correcting the current single-writer/transaction seam, lease lifetime, database open/configuration, and bounded recovery over adopting PostgreSQL, an event broker or a second event store for this incident.
- Before choosing a concrete remedy, distinguish the filesystem lease conflict, SQLite BUSY/LOCKED during setup/commit, verifier WAL interactions, and actual disk/corruption faults with bounded private diagnostics; measure queue/backpressure and write/commit latency. Neither timeouts alone nor automatic reconnects are considered proof of a fix.
- Preserve the original raw source evidence, source-event and first-local-known clocks, per-selected-account scope generations, journal/SHA chains, and unbroken causal continuity. An uncommitted or lost event cannot be reconstructed as a prospective first-known event from historical fills. A gap must fence new-risk intents without clearing follower inventory or HALT.
- The exact transient-busy retry bound, durable buffering rule, per-account vs shared socket failure scope and operational acceptance thresholds remain **OPEN**. No production change follows automatically from approval of this direction.

## Q2 — Separate wallet eligibility, financial attribution and strategy quality (APPROVED)

- **Wallet eligibility** is a dated deterministic participation assessment. Identity, source-account scope, evidence age, activity and a declared capital policy are separate input facts.
- **Wallet financial attribution** explains changes in observed capital using verifiable deposits/withdrawals, realized and unrealized trading outcomes, funding/fees, liquidation and unexplained residuals. Equity decline alone must never be relabeled a trading loss or edge decay.
- **Strategy quality / edge decay** describes deteriorating **cost-adjusted follower economics** over explicit point-in-time windows, not simply lower wallet equity, inactivity, a liquidation label or source-wallet PnL.
- Preserve distinct `VALID/INVALID/INCOMPLETE/STALE/UNKNOWN` evidence meaning and capability-specific admission. Missing transfer history or insufficient follower observations creates `UNKNOWN` or `INSUFFICIENT_EVIDENCE`, **not** a fabricated classification, automatic exclusion or inferred zero balance.
- Treat the previously selected `$1,000` wallet-equity floor as an eligibility policy **only where the relevant capital evidence is authentic, attributable and scoped**; do not reintroduce whole-wallet NAV as a universal fixed-k admission requirement. The exact equity measure, source/cadence and automation effect remain **OPEN**.
- Existing SQLite owns wallet identity, aliases, exclusions and portfolio metadata; research read models do not write exclusions, change subscriptions, or command Guardian.

## Q3 — Risk-budgeted, portfolio/pod-specific versioned k (APPROVED)

- Preserve `FIXED_K_NATIVE_QUANTITY`: full verified selected-source native quantities -> risk-budgeted candidate target notionals at the independent follower quote; no source NAV denominator and no conversion of every fill into a position target.
- The unit of recalibration is **(portfolio version, selected account/pod, sizing policy, evaluation as-of)**, not a wallet-global multiplier. A source wallet legitimately may have different k across multiple portfolios.
- Optimize subject to the existing PM03/PM04 follower financial rules and modeled net costs, exposure/margin, concentration, pending/unknown effects, per-pod losses and daily/trailing floors. For a standard `$10,000` challenge, `$200` per-pod is the existing **nominal loss-trigger scenario**, not a guaranteed maximum outcome or an authorization override.
- Evaluate recent cost-adjusted follower economics using causal point-in-time evidence, rather than maximizing the latest source-wallet profit or assuming PnL scales linearly with k. Model outputs may recommend **hold, decrease or increase**, with insufficiency and confidence explicitly represented.
- Every candidate k revision must be traceable to a source evidence/window/algorithm/policy version and immutable proposal identity. Activation is a **separate versioned portfolio release decision** that preserves existing historical k, original paper-run identity, existing financial journal and past PnL. Automatic activation, open-position transition semantics and reviewer/Guardian approval remain **OPEN**.
- Never reinterpret old P1/P14/P16/E1–E12 paper-history k values, past source first-known clocks or signed artifacts. Never promote a research proposal into broker authorization.

## Binding implementation architecture: reuse Pydantic-native V4 (APPROVED)

This program **MUST adopt the Pydantic-native architecture just engineered**, following [domain ownership](2026-11-09-pydantic-native-contract-ownership.md), [validated evidence semantics](2026-11-09-pydantic-native-validation-runtime.md), [domain interfaces](2026-11-09-pydantic-native-domain-interfaces.md), and [V4 T+300 authority](2026-11-08-position-first-t300.md).

- External provider/evidence records and cross-module domain decisions/results use **domain-owned, explicitly versioned, strict, frozen Pydantic v2 contracts**, with forbidden unexpected critical fields, deterministic validation and explicit `UNKNOWN` outcomes. Proposed conceptual interfaces include `SourceWriterHealth`, `WalletHealthEvidence`, `WalletFinancialAttribution`, `WalletStrategyQuality`, `KRecalibrationProposal` and `PortfolioKRelease`. **These are conceptual names, not approved class signatures or implemented capabilities**.
- A provider adapter alone performs explicit Decimal/UTC normalization; immutable original bytes/signatures/hashes and known-at clocks remain under their existing owners. Never rehash historical evidence using `model_dump`.
- A pure deterministic domain decision function consumes validated facts and returns typed proposals/reasons. Existing source journal, SQLite registry/release authority and PM03/PM04 apply their own committed effects. Cross-repository Guardian stays separately pinned, protected and independently authorized.
- Keep Polars/DuckDB/Parquet for bulk causal analytics and pure Decimal sizing for numerical calculation. **Do not** wrap millions of rows in Pydantic objects or introduce a global `WalletState`/common model package. Pydantic Evals may test wallet diagnosis offline but cannot issue eligibility overrides, financial permits or scientifically qualified alpha.
- No Prefect/Temporal/Pydantic Graph orchestration is justified by these approvals alone. Any later scheduler uses the above typed interfaces, not a second ledger or agent-as-authority.

## Alternatives rejected

1. Replace SQLite or introduce a durable broker without diagnosing the observed source-writer contention.
2. Discard original T0/continuity to make the paper pipeline appear continuously active.
3. Collapse wallet eligibility, capital movements, edge quality, operational readiness and financial risk into one health score.
4. Treat net equity changes as trading PnL, assume missing whole-wallet NAV equals failure of fixed-k, or silently exclude a wallet for missing evidence.
5. Select k solely from recent raw leader profit, update it globally for every portfolio, or overwrite historical run/configuration values.
6. Equate successful Pydantic validation, an agent explanation, or a research k proposal with Guardian order permission.

## Consequences, unresolved interfaces and verification direction

- Reliability work can be specified/tested independently of the slower wallet-health evidence program. Wallet-health monitoring can begin in read-only research; **automatic k increases require independent economic evidence and a decided release boundary**.
- Before implementation, pressure-test transient vs unrecoverable writer failures, producer/consumer crash points, finite queue overflow, account-local vs shared disconnects, equity movement mixtures, insufficient follower samples, and open positions during a k change.
- Current acceptance remains **ENGINEERING DESIGN ONLY**. Research model validity, installed source service health, complete prospective entry/exit coverage, scientific quality and trading authorization must be reported independently.
- **Subsequent status:** Q4–Q9 were approved in [the Round 2 ADR](2026-11-09-source-wallet-health-k-recalibration-round2.md). The current frontier Q10–Q15, including whether Prefect is worthwhile, is tracked in [the design grill](../SOURCE-WALLET-HEALTH-K-GRILL-20261109.md). No implementation, commit, merge, deployment or protected service changes follow from either ADR.
