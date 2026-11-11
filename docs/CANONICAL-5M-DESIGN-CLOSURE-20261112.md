# Canonical five-minute copy-wallet design closure and acceptance map

**Date:** 2026-11-12
**Status:** Q1–Q24 APPROVED FOR ARCHITECTURAL DESIGN (Q2=B; Q13=B; all other Q=A). Documentation only. **No implementation, push, merge, deployment, financial authorization or scientific qualification is implied.**

**Binding decisions:** [checkpoint/CWSA ADR](decisions/2026-11-11-canonical-5m-checkpoint-grill.md). **Earlier current installed policy:** [first-known T0+300 ADR](decisions/2026-11-08-position-first-t300.md). **Related safety constraints:** [existing invariant-design closure](decisions/2026-11-11-invariant-grill-design-closure.md).

## 1. One abstraction, three already-owned truths

- **CWSA source continuity:** One canonical economic position target per selected Hyperliquid account/all required DEX scope and UTC five-minute checkpoint, backed by complete original native REST evidence. A durable checkpoint **outcome** is not necessarily a **target-change signal**. Source epochs belong only to source scope/authority.
- **Signed copy mandate:** An immutable, account/pod-bound relationship to that source, frozen `k`, allowed markets, active timing and risk rules, activation baseline and signed generation. Follower mandate succession does **not** reset the common CWSA source epoch. A mandate is a value/relationship contract inside existing authority, **not a third runtime service**.
- **Independent finance:** Each virtual-paper PM03/PM04 account and protected Guardian holds its own actual positions, pending effects, risk, journals and explicit opportunities. Guardian alone owns real order intents and broker reconciliation. A source target cannot grant a broker permit or erase an unknown/old-generation order.

**No implicit FSMs:** Each owner must validate a typed (predecessor, event, causal evidence, signed policy, actor, time cutoff, guard, next state, local durable outcome) transition. Invalid transitions produce an attributable rejection. Do not infer the current state from `is_active`, `ready`, presence/absence of position rows, elapsed wall time, a cache, worker health or a combination of unrelated booleans. No new central FSM, second Guardian, global database transaction, extra financial journal or duplicated per-source T+300 timer.

## 2. Explicit legal transition maps (target requirements)

These are separate conceptual aggregates, **not code that exists today**. Their names are descriptive; the future signed wire schema must be versioned.

### CWSA selected-source continuity

| Predecessor | Authenticated event and guard | Successor | Durable outcome |
| --- | --- | --- | --- |
| UNANCHORED | First complete, in-policy native account/DEX checkpoint | CONTINUOUS | BASELINE; no new risk |
| CONTINUOUS | Next eligible complete scope-identical state, economically unchanged | CONTINUOUS | UNCHANGED checkpoint; no new signal |
| CONTINUOUS | Next eligible complete scope-identical state, economically changed | CONTINUOUS | CHANGED checkpoint plus one target-change signal |
| CONTINUOUS / UNANCHORED | Missing/stale/incomplete/incoherent checkpoint, wrong signer or broken sequence | FENCED | UNAVAILABLE/QUARANTINED; no new-risk signal |
| FENCED | First newly verified complete scope-identical state | CONTINUOUS | RECOVERY_BASELINE; no opening, possible independently verified risk reduction |
| FENCED | Further unavailable checkpoint | FENCED | UNAVAILABLE; no risk |
| Any | True source-account/scope change under newly approved source epoch | UNANCHORED (new epoch) | SCOPE_CHANGE; no inherited source entry |

Each UTC checkpoint obtains one durable outcome per source/scope/epoch. Successful source checks do not imply the follower mandate is active or Guardian finance is safe.

### Signed destination copy mandate (per destination/pod)

| Predecessor | Authenticated event and guard | Successor | Durable outcome |
| --- | --- | --- | --- |
| New immutable signed mandate | Valid future-effective activation request | AWAITING_BASELINE | Generation sealed; no opening |
| AWAITING_BASELINE | First complete eligible common-source checkpoint at/after mandate activation | ACTIVE | DESTINATION_BASELINE; no copy-current entry; CWSA stream unchanged |
| ACTIVE | Authorized account-bound pause | PAUSED | New-risk embargo; existing exposure persists |
| ACTIVE / PAUSED | Authorized retirement/replacement | RETIRED | No openings under old generation; retain risk/financial ownership |
| PAUSED / RETIRED | Reenable/revise request | **New** AWAITING_BASELINE generation | New signed release and baseline; old generation never resurrected |

A paused/retired mandate is not a flat broker account. A previous generation's position, unknown order and pod P&L remain attributed to that old generation. **Only one opening-effective signed generation per account/pod at a time**; total account risk includes old residuals. Replacing one follower does not reset the source's shared continuity epoch.

### New-risk opportunity (one consumer's own effect)

| Predecessor | Event and guard | Successor | Durable result |
| --- | --- | --- | --- |
| No opportunity | One eligible genuine target-change signal + ACTIVE signed mandate + no source/financial veto | REVIEWABLE | Deterministic source signal × mandate generation × consumer opportunity ID |
| REVIEWABLE | Verified temporary pre-dispatch dependency gap, **proven no possible broker side effect** | PRE_DISPATCH_BLOCKED | Original deadline retained; reason and evidence |
| PRE_DISPATCH_BLOCKED | Original deadline not reached, transient cause independently corrected, no possible dispatch | REVIEWABLE | Same opportunity ID; fresh checks, no extra opening attempt |
| REVIEWABLE | All native source/market/account/risk proofs valid and protected local intent durably committed | COMMITTED_ONCE | **One** financial intent per consumer opportunity; broker lifecycle then belongs to Guardian |
| REVIEWABLE / PRE_DISPATCH_BLOCKED | At or after original immutable expiry; terminal policy rejection or separately authorized pause | MISSED | Durable terminal nonopening disposition |
| COMMITTED_ONCE / MISSED | Source duplicate, unchanged later checkpoint, replay, restart, late data | Same terminal opportunity | No new order/attempt |

**Expiry:** earlier of the next UTC five-minute checkpoint boundary and independently signed freshness-bounded opportunity deadline. At equality, expiry wins. Each later genuine source change is a **new** opportunity with its own ID; a leader increase may target the full latest frozen-k desired position after a missed initial entry (Q15), but not when a conflicting broker effect is UNKNOWN. Source-driven closes/reductions and independent Guardian protective action remain separately classified; they do not become repeated new-risk entry attempts.

**Broker order lifecycle:** Retain the existing financial journal's own typed order/ack/cancel/partial/UNKNOWN/terminal states. A committed order with unknown remote outcome is outstanding exposure and cannot be resubmitted as a fresh order. Reconciliation must establish native terminality, cumulative fills, account/pod attribution, reservations and remaining obligations before conflicting opening risk can be reconsidered.

## 3. Netting and reversal examples with required outcomes

| Scenario | Approved outcome |
| --- | --- |
| Wallet A valid + BTC, wallet B source DEX unavailable | A may act if independent portfolio/account safety permits; B emits UNAVAILABLE and cannot authorize new risk; economic portfolio coverage incomplete |
| Existing +10 BTC leader baseline under newly enabled pod | Record DESTINATION_BASELINE, no immediate copy; wait for a genuine subsequent position change |
| 00:05 source +10 BTC, follower entry missed; 00:10 unchanged +10 | New-risk opportunity MISSED; unchanged checkpoint cannot repeat |
| 00:15 valid increase +10 → +11 after missed opening | One **new** full-target frozen-k opportunity, if risk and prior broker outcomes permit |
| Three pods' target orders net to zero | Guardian applies individually proven pod risk/attribution; no fictitious net broker execution, fee or P&L |
| Signed old mandate replaced while an old opening is UNKNOWN | New generation may baseline but cannot double-open conflicting risk; old generation and journal retain UNKNOWN until independently reconciled |
| Leader long → short | One cross-zero order **only** if venue-native semantics and all guardrails prove safe; else verifiable reduce-only and durable MISSED opposite-side opening |
| Source checkpoint unavailable just before opportunity expiry | Opening expires on its original deadline; source recovery cannot backdate or revive it |
| Operator pauses one copy mandate | No new openings for that mandate; existing account risk/protective reductions remain managed, no implied flatten |
| Rollback to binary that cannot read new financial schema | Do not downgrade or rewrite; fence new risk / DISARMED, preserve old journal and independent recovery |

## 4. Final acceptance contract (proof, not a readiness-label waterfall)

| Boundary | Minimum evidence and positive/negative oracles | Owner |
| --- | --- | --- |
| Native source | Complete explicitly enumerated selected account/DEX census including authenticated empty scopes; original REST raw bytes and exact signed Decimal quantities; causal clocks; measured age/skew/grace, 14-account load/rate/resource budget | CWSA source adapter |
| Source continuity | Deterministic checkpoint outcomes; valid same-scope economic change only; gap and late sample quarantine; recovery baseline; duplicate/reordered/clock-regressing/scope-change negative tests; isolated wallet faults | CWSA reducer/journal |
| Copy mandate | Signed account/source/pod/asset/k/policy version binding, activation nonactionable, material-generation succession, single opening-effective policy, old-generation exposure conservation, pause not flatten | Signed release verifier + owner-local consumers |
| Consumer opportunity | One-shot source signal × mandate × consumer identity; original deadline; bounded **no-dispatch** recheck; no retry after possible dispatch; missed initial then new genuine increase; independent source-driven close/reduction behavior | PM03/PM04; Guardian protected journal |
| Pod and broker finance | Fixed-k source-notional with independent follower price; actual positions and reserved unknown effects; independent pod risk/fees/fills/conservation; one guarded net order where native-safe; prove cross-zero vs reduce-only fallback; fills/cancel/UNKNOWN crash/restart | Guardian / native connector; virtual paper independent |
| Cross-repository compatibility | Version-specific signature, wire and release pins; no silent reuse of T0+300 proof or `portfolio_release_v1`; original historical replay; strict downgrade rejection; exact signed compatibility manifest | Existing trusted release and producer/consumer owners |
| Paper / prospective science | Matched old T0+300 vs new grid actual-known/source-coverage cohorts, delayed exits, missed and later full-target entries, fees/slippage, tail loss/drawdown, account+pod netting; report incompleteness rather than inventing alpha | Existing research/qualification authority |
| Reversible activation | Read-only dual observation and shadow; independently verified virtual paper; signed future-effective **single** protected policy; separately proven native broker account/history/order permission; named compatible rollback preserves journals, HALT and unknown effects | Existing release authority and Guardian |

**No made-up threshold:** Exact source-age, cross-DEX skew, checkpoint processing grace, opportunity maximum age, acceptable fault rate, provider capacity, scientific decision criterion and native broker capability must be measured, signed and independently tested before each affected protected admission. Missing evidence blocks only its relevant capability; read-only research stays available. Past test counts and hypothetical follower mids cannot be silently promoted to profitability or live permission.

## 5. Audit closure and remaining factual blockers

**Design frontier:** Q1–Q24 are decided. No remaining material user-choice is exposed by this architecture grill. The next work is an **implementation-ready specification and evidence-driven tests**, not another set of booleans or ceremonial readiness questions.

**Verified code mismatch (checked in isolated documentation worktrees, no implementation):**
- `copytrade_pm.pm_source_contracts` has typed position observations and economic Decimal equality, but its existing reducer accepts `previous["baseline_valid"]`, follows event-driven first-known semantics and is **not** a scheduled checkpoint authority.
- `prop_production.v4_timing.V4ShadowProjection` still owns `INTENT_TIME_MS=300_000`, so it would duplicate the source clock under the approved new strategy.
- `prop_production.release.ReleaseVerifier` strictly parses `portfolio_release_v1` and `batch_seconds=300`; signed mandate generations and opportunity deadline policy are not implemented.
- `prop_production.financial_semantics.validate_transition` verifies important financial invariants, but it is not evidence the approved checkpoint/mandate/opportunity transition tables or an authenticated Propr order route exist.

**Factual blockers:** native REST 14-account/all-required-DEX freshness/capacity with actual source timestamps; independent native follower market/account/broker evidence and single-order reversal semantics; exact trusted signer and schema compatibility; actual matched prospective net follower economics; external release/financial authorization. **No implementation, deploy or authorization follows from this documentation.**

**User instruction carried forward:** abstraction first; deepen the existing owner transition boundaries, not add services; **never use implicit state machines**.
