# Pydantic-native interface choices — Round 7 grill (Q30–Q34)

**Date:** 2026-11-09
**Status:** Q30–Q34 **APPROVED FOR ARCHITECTURAL DESIGN**, NOT IMPLEMENTED. This is the original decision-tree record; [the Q30–Q34 ADR](decisions/2026-11-09-pydantic-native-domain-interfaces.md) is the binding summary. Implementation signatures remain unsettled and no coding is authorized.

**Code evidence inspected at `175d54d`:**
- `pm_v4_selected_positions.official_accounts()` binds one shared `scope_sha` to selected parents and the full DEX catalog SHA, which is useful for observer-config proof but not the same as each account's economic-position scope.
- `pm_forward_source_observation.read_public_all_dex_scope()` intentionally emits `account_scope_complete=False` and `status=BLOCKED_INCOMPLETE_WHOLE_WALLET` for a per-account all-DEX observation. `pm_fixed_k_source_scope.assess_selected_parent_perp_scope()` can independently accept that scoped perp book for NAV-free research. This is legitimate **different completeness semantics**, but the shared field names risk misinterpretation.
- `pm_e4_prospective._account_state()` requires each DEX to have `marginSummary`, including `accountValue`, `totalNtlPos`, `totalMarginUsed`, even though source NAV is not a sizing requirement under FIXED_K_NATIVE_QUANTITY. Determine from actual official message semantics whether the mandatory presence establishes a complete frame, or is only unrelated diagnostics, before relaxing it.
- `pm_forward_stream_journal.append_checkpoint()` already has deterministic `stream_id`, expected `cursor`, event SHA, unique event SHA and commit-chain verification, and `verify_official_position_transition()` already rejects intervening GAP/BASELINE/SCOPE. Preserve these good contracts.
- `pm_forward_single_shot` already derives entry intent identity from `run_id`, pod, source sequence, first-known and policy version, and derives exit identity separately. Preserve archived IDs; improve semantics rather than invent a second global ID registry.
- PM-03/04 are the existing simulated finance owner; `prop-production` Guardian owns real authority. Do not create a global `WalletState` or a new financial ledger.

## Q30 — Split evidence identity and canonical domain projections?

**Option A — Giant Pydantic observation object:** Contains original wire, provider metadata, positions, admission flags, current readiness, pending attempts and model serialization in one structure. **Rejected recommendation:** mixing trusted raw bytes with normalized projection invites accidental reserialization and source-authority confusion.

**Option B — Small immutable domain contracts (RECOMMENDED):**
- **SourceEvidenceRef**: SHA/receipt pointer + separately captured original clocks, not a replacement for original signed raw bytes.
- **SelectedPerpScope**: selected account identity, required default/HIP-3 DEX census, contract namespace, scope generation, and evidence of completeness.
- **CanonicalPositionBook**: finite exact Decimal signed native quantities keyed by native instrument, with scope binding and source/provider/local receipt clocks; numeric formatting has no economic effect.
- **PositionObservation**: tagged result `BASELINE` / `UNCHANGED` / `CHANGED` / `GAP` / `SCOPE_CHANGED` / `INVALID`, with no success flag conferring finance.
- **SourceTransitionDecision**: next checkpoint + proposed journal effects or explicit rejection; no broker mutation, no implicit network I/O.

Those names and fields are **contract examples**, not approved implementation signatures. Historical `paper_source_book_v1` and `paper_observer_stream_event_v1` remain readable and preserve their SHA identity.

**Counterexample:** two provider raw frames have unequal message SHAs but equal Decimal position vectors; an `UNCHANGED` economic observation must still preserve both auditable wire identities as appropriate.

## Q31 — What should be the identity of a transition and modeled effect?

**Option A — Hash only current economic positions:** Incorrect. `flat → +20 → flat → +20` revisits the same state but includes two distinct genuine transitions.

**Option B — Preserve existing stream and intent identities; derive versioned effect keys from committed events (RECOMMENDED):**
- Observation identity: existing source stream ID, epoch, monotonic cursor/sequence, raw SHA, first-known receipt and scope-generation proof.
- Economic state equality: only for classifying **whether** a change occurred, not as the unique transition ID.
- Genuine transition identity: one committed event/receipt in a valid scope epoch, unique across replay.
- Paper new-risk intent: keep the existing hash-based `run_id + pod + source_seq + original_first_known + policy_version` family where valid, subject to historic-version reader compatibility.
- Protective exit / unknown outcome keys: separate idempotent effect IDs, bound to committed attempt and financial owner; no automatic retry with new ID after uncertainty.
- Commit before dispatch; on restart reuse the same durable ID rather than minting fresh IDs.
- If a future per-account scope-generation ID changes ID construction, version the scheme and preserve the original v1 derivation for archived journals.

**Counterexample:** a worker crashes after a modeled effect commits but before the receipt ACK; reprocessing the same source event must not double-count cash or invent a second order.

## Q32 — What counts as a complete source account?

**Option A — Single `account_scope_complete` boolean:** Reproduces overloaded legacy semantics; an incomplete whole wallet can still have a valid complete *selected* per-account perp book.

**Option B — Separate proofs and generations (RECOMMENDED):**
- `SelectedPerpBookCompleteness`: exactly selected parent/child account, native DEX census, position vector, required official timestamps, event continuity.
- `WholeWalletFinanceCompleteness`: separate leader NAV, collateral, spot/vault and unrelated subaccount financial accounting; irrelevant as a **universal** gate to fixed-k mirroring, required only for explicit policies that depend on it.
- `ObserverGeneration`: the entire configured roster, subscribed transport and provider catalog snapshot.
- `AccountScopeGeneration`: one selected account's relevant native DEX/instrument semantics, unaffected by unrelated catalog additions.
- `PortfolioDependency`: identifies which of 16 paper ledgers depend on a fenced source account, and propagates invalidation without broad resets.

**Unknown prerequisite for actual implementation:** Prove whether the native provider's `marginSummary` is part of the official completeness envelope. Do **not** silently weaken native scope proofs merely because NAV isn't used for sizing; if it's only supplemental metadata, model it as optional diagnostic and preserve raw evidence.

**Counterexample:** global HIP-3 catalog adds a market untouched by a selected account; the observer generation changes, but that account's already-proven economic contract does not automatically change. Relevant selected instrument size precision change does fence that contract.

## Q33 — Who owns the new state aggregate and how is risk kept independent?

**Option A — Universal typed `WalletState` with source health, strategy quality, pending orders and Guardian risk:** Includes invalid combinations, second financial authority and conditional coupling.

**Option B — Separate aggregate owners using one directional contract pipeline (RECOMMENDED):**
- **ObservedAccount** reducer owns prospective source baseline/continuity/position state; receipt owner is existing PaperJournal transaction.
- **PaperOpportunity** reducer owns new-risk source intent, T+300, coalescing, consumed attempt and exit-opportunity metadata; never cash or booked inventory.
- **FollowerFinance** (existing PM03/04) owns cash/equity, per-pod quantities, unresolved exposure, risk limits and durable HALT; remove scattered direct mutations through a focused finance policy transition owner.
- **Guardian** retains independent protected account snapshot, signed release/permit, durable intent and broker reconciliation. Source/Pydantic schema success alone does not grant permission.
- **WalletEligibility** from SQLite and dated evidence, **ResearchQuality** from economic analyses, and **OperationalReadiness** from observers are separate materialized facts, not writable parts of the source aggregate.

Minimal public contracts are typed; pure reducers run without wall-clock, filesystem, broker network or agent calls. No duplicate financial journal.

**Counterexample:** a wallet is source-healthy, financially under $1000 and historically profitable, while follower HALT is active. All facts can coexist; no single `ACTIVE` state can replace the independent decision.

## Q34 — What will make Pydantic Evals a useful scientific instrument for agent reasoning?

**Option A — Have an LLM judge outputs without independent labels and call the score 'wallet quality':** Wrong; it confuses fluent explanations with causal accuracy or trading alpha.

**Option B — Offline labeled agent-diagnosis comparison (RECOMMENDED):**
- Construct privacy-safe wallet cases as of their real known time (withdrawal, liquidation, true trading loss, unrealized drawdown, inactive but solvent, top-up, stale source data, ambiguous cause).
- Label from source/account/transaction evidence distinct from the agent under test. Require `UNKNOWN / INSUFFICIENT_EVIDENCE` where causal diagnosis cannot be established.
- Compare model/eval results with a deterministic baseline: threshold-based equity and activity classification plus verifiable attribution of observed account changes.
- Score false confident claims, abstention precision, correct evidence citation, time leakage, tool misuse and cost per useful diagnosis; never convert agent verdict to live selection, protective exit or broker order.
- Keep a disjoint holdout by wallet and time, or clearly disclose lack of independence. No optimistic agent-generated truth set.
- Refer to official Pydantic Evals Dataset/Case/evaluator contracts before code, and pin the dependency only after experiment authorization.

**Counterexample:** a wallet equity drop of 55% coincides with large withdrawals and a falling crypto market. Without transaction-level decomposition, an agent must not declare trading-edge collapse from equity alone.

## Resulting dependency tree

- **Q30 and Q32** establish projection boundaries and *what* completeness means. These are semantically independent but must both be settled before implementing the final scope envelope.
- **Q31** establishes identity/effect idempotency independent from which Python model classes hold the fields.
- **Q33** establishes authority partitioning without choosing a specific library for the reducer.
- **Q34** establishes an optional offline research evaluation standard independent from source and risk migration.
- After Q30–Q34: **Next frontier** can settle invalid-message severity by continuity impact, exact source+paper aggregate interface examples, aggregate fanout commit/cursor ownership, and S0/S1 canary evidence levels. Do not ask decisions that depend on unresolved Q30/Q32 first.

## Current approval and execution status

Q3–Q39 APPROVED DESIGN; [Q35–Q39 binding ADR](decisions/2026-11-09-pydantic-native-failure-and-spec-readiness.md). This document retains the **historical alternatives discussed** rather than an unresolved decision frontier. All 28 audit families have an assigned design disposition and [test matrix](PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md), but **0/28 implemented/verified closures**. No code, dependency, commit, merge or deployment permitted.
