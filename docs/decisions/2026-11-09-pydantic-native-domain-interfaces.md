# ADR — Pydantic-native domain interface partition and diagnostic-eval boundary

**Date:** 2026-11-09
**Status:** Q30–Q34 **APPROVED FOR ARCHITECTURAL DESIGN**. Names below are conceptual interfaces, not approved Python signatures. No code, dependency, schema migration, commit, merge, deployment or order authorization is permitted by this ADR.

**Prior decisions:** [Q3/Q4](2026-11-09-pydantic-native-migration-guardrails.md), [Q5–Q8](2026-11-09-pydantic-native-contract-ownership.md), [Q9–Q13](2026-11-09-pydantic-native-state-semantics.md), [Q14–Q18](2026-11-09-pydantic-native-recovery-and-compatibility.md), [Q19–Q24](2026-11-09-pydantic-native-validation-runtime.md), [Q25–Q29](2026-11-09-pydantic-native-sequencing-ecosystem.md), plus [V4 first-known T+300](2026-11-08-position-first-t300.md).

## Context from repository and primary source

At `175d54d`, `pm_forward_source_stream.PersistentAccount.observe()` classifies complete official frames through manual dictionaries; `pm_forward_stream_journal` already stores per-stream epoch, cursor, SHA-bound journal checkpoint and receiver clocks; `pm_forward_single_shot` already builds deterministic new-risk entry and exit IDs. `pm_v4_selected_positions.official_accounts()` fingerprints a whole observer configuration, including all parent selections and a global DEX catalog. That scope hash is **not equivalent** to one selected account's economic position scope.

The legacy `paper_source_book_v1` uses `account_scope_complete=False` to mean incomplete *whole-wallet financial scope*, while `pm_fixed_k_source_scope` separately accepts a complete selected-parent perp observation for fixed-k research. These are intentionally different completeness standards but have confusing names.

The Hyperliquid official WebSocket subscription schema documents `allDexsClearinghouseState` and `WsAllDexsClearinghouseState` containing per-DEX `ClearinghouseState`, whose declared fields include `marginSummary`. This is evidence to **retain the documented envelope** rather than drop `marginSummary` solely to avoid a leader NAV check. It does **not** establish source NAV sufficiency for equity-relative replication or that all actual wire encodings are identical to the TypeScript description. Inspect authentic captured native frames before changing array-vs-map encoding support or mandatory fields. Source: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions

## Q30 — Evidence reference and canonical economic projection (APPROVED)

Implement the **small-contract option**, not one global `WalletState`:

- `SourceEvidenceRef`: immutable original native raw-byte/receipt identity, original clocks and provenance *reference*. Historical signed data is not replaced by reserialized Pydantic output.
- `SelectedPerpScope`: exact native account (parent/child independently selected), declared DEX/market identity, active generation and separately tested complete-book evidence.
- `CanonicalPositionBook`: strict exact Decimal signed native quantities by native instrument, complete scope binding and distinct source-event / local-known times; `"20"` and `"20.0"` are economically equal but not the same raw frame.
- `PositionObservation`: tagged, semantically disjoint BASELINE, UNCHANGED, CHANGED, GAP, SCOPE_CHANGED and INVALID cases; a valid observation cannot itself grant permission to trade.
- `SourceTransitionDecision`: proposed deterministic next checkpoint and journal effect intents, or explicit rejection; no hidden I/O, mutation of unrelated finance or signer authorization.

Reusing proven existing journal/receipt structures is the default; create versioned new contracts only where a narrow typed seam requires it.

## Q31 — Transition and effect identity survives replay (APPROVED)

- Preserve source stream ID, signed receipt reference, source epoch, monotonic cursor, verified source scope and first-known clock. The *economic state vector* is **not** an event ID: `FLAT → +20 → FLAT → +20` contains two independent transitions to the same final state.
- Preserve existing archived deterministic PM04 intent derivation where valid (`run_id`, pod, source sequence, original first-known, rule version), and existing separate exit IDs. Future identity-version changes must not retrospectively alter original signed/journal hashes.
- Bind each downstream per-portfolio modeled intent/effect to one committed source event and the owning run/pod, not an uncommitted queue receipt or a timestamp regenerated after restart.
- A repeated event with the same verified identity is an idempotent replay; a conflicting payload at the same identity is a divergence, never a silently accepted replacement. Unknown dispatch outcome is not a new attempt permit.

## Q32 — Explicit, independent completeness and generation notions (APPROVED)

- `SelectedPerpBookCompleteness`: the selected account's complete official perp/DEX position book, exact instrument identity, required event timestamps and continuous prospective proof.
- `WholeWalletFinanceCompleteness`: leader NAV/spot/vault/all related accounts/collateral sufficiency, **not** a universal fixed-k new-entry gate.
- `ObserverGeneration`: whole observer roster, subscription/configuration and provider catalog identity; a change here is not automatically a change in every selected account's economic contract.
- `AccountScopeGeneration`: one selected account's relevant DEX/position contract semantics; material changes fence affected dependent new-risk intents and require a new complete baseline. Unrelated listings do not automatically invalidate unaffected source books.
- `PortfolioDependency`: the exact set of paper pods/portfolios depending on a selected source account, used for targeted invalidation without merging financial ledgers.

**Fact to verify in S0 before implementation:** The official schema lists `marginSummary` as a ClearinghouseState field; the local parser expects a particular `clearinghouseStates` encoding and required margin fields. Compare official definitions to *original captured native frames*, not just invented fixtures, before changing the native parser. If a field is mandated for detecting complete provider replacement, retain the required presence while keeping NAV optional for fixed-k sizing.

## Q33 — Separate transition owners and independent finance (APPROVED)

- `ObservedAccount`: one deterministic source-position/continuity reducer. Source event/checkpoint ownership remains existing PaperJournal; no new observer database.
- `PaperOpportunity`: new-risk opportunity eligibility, original T0/T+300, coalescing, consumed/expired attempt and protective exit-intent metadata. Its output is **not** actual follower inventory or a fill.
- `FollowerFinance`: existing PM03/04 single authority for simulated cash/equity, booked inventory, attribution, pending/unknown outcomes, pod budgets and durable HALT. Consolidate scattered direct risk assignments without replacing financial accounting rules.
- `Guardian` (in `prop-production`): separate protected permits, real account risk/broker states and independent compatibility pins. Research output cannot clear or mint Guardian authority.
- `WalletEligibility`, `ResearchQuality`, `OperationalReadiness`: independent dated facts combined only by explicit capability-scoped admission; a source-healthy, scientifically unqualified, equity-ineligible, follower-HALTed situation is representable without paradox.

All Pydantic contracts are domain-owned and versioned; Python type import is not a trust credential.

## Q34 — Offline Pydantic Evals pilot tests agent diagnosis, not trading quality (APPROVED)

- Use independently labeled, PIT-correct **read-only** wallet-monitoring cases: withdrawals, top-ups, liquidations, market drawdown, realized trading losses, inactivity, missing history, and ambiguous mixtures.
- Retain raw evidence provenance and independent labels unavailable to the agent at inference time. `UNKNOWN/INSUFFICIENT_EVIDENCE` is an expected valid diagnostic outcome.
- Score factual attribution, confidence/calibration, justified abstention, PIT leakage, source/tool citation, invalid tool action, operational cost and meaningful improvement over deterministic monitoring rules.
- Keep disjoint wallet/time holdout where feasible; never promote model-authored labels to scientific ground truth.
- A successful agent diagnostic eval cannot qualify executable follower economics, update protected selection or clear Guardian HALT.

## Alternatives rejected

1. One Pydantic object that owns source, position, finance, agent and Guardian state.
2. Use final economic state hash as unique transition identity; recompute ids on retry.
3. Require whole-wallet NAV for fixed-k selected perps because legacy `account_scope_complete=False`.
4. Assume every change to the global HIP-3 catalog invalidates every selected account's complete book, or infer missing instruments flat after scope change.
5. Duplicate PM03/04 and Guardian journals inside a new Pydantic Graph.
6. Let an LLM judge its own wallet-edge causal explanations or relabel profit/science.

## Next design frontier and status

Q30–Q34 are binding **design semantics**, not implementations. [The 28-family matrix](../PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md) and [roadmap](../PYDANTIC-NATIVE-MIGRATION-ROADMAP-20261109.md) still record **0/28 engineering closures**. Next independent choices: Q35 malformed provider-event continuity/fencing; Q36 per-authority/cross-journal cursor and effect idempotence; Q37 multi-fault testing methodology; Q38 evidence-minimal SHADOW canary gate; Q39 criteria for an implementation-ready specification. Exact combined-fault expected outcomes depend on Q35/Q36 and must be settled in the next round, even if a provisional matrix is drafted now.
