# Copytrade domain glossary

Canonical domain meanings. This glossary does not specify implementation or storage.

## Agent operation and evidence

- **Operation capability**: A supported software operation and its input/effect contract, distinct from provider execution capability and permission to act.
- **Operation assessment**: An evidence-based account of whether one requested action's applicable prerequisites are satisfied within a declared identity, scope and time; it does not itself grant authority.
- **Evidence dependency**: A specific original observation, owned state or policy on which a claim or decision depends; a change invalidates affected conclusions without rewriting their historical basis.
- **Action plan**: A bounded proposed change with an expected predecessor, permitted effect, verification condition and recovery meaning; separate from authorization and any committed financial intent.
- **Verified postcondition**: Independently checked evidence that the intended owned effect occurred or was rejected; command success alone is insufficient.
- **Reusable finding**: A retained conclusion with reproducible inputs, scope, assumptions and limitations, including negative or inconclusive outcomes; repetition does not create independent evidence.
- **Authentic evidence pack**: A frozen, privately retained set of original owner-produced records and provenance sufficient to verify a historical claim without relying on later mutable state; derived projections and fixtures are not substitute originals.
- **Read-only evidence replay**: Interpretation of pinned original records through their owning verification contracts without publishing new prospective observations, creating financial effects or modifying the original records.
- **Agent E2E evidence manifest**: A versioned account of a task's scope, original evidence identities, content hashes, clocks, applicable contract versions and conclusions; a redacted reference does not itself constitute the original evidence.
- **Workflow verification**: Evaluation of whether an agent selected the correct operation, interpreted genuine evidence accurately, respected scope and authority, and abstained on unsupported claims; separate from the owners' operational and financial readiness.
- **Evidence-blocked E2E case**: A scenario whose required authentic owner proof is unavailable or unverifiable; a correct agent abstention may satisfy its behavior check without completing its real-world evidence requirement.
- **Verification ancestry**: The original predecessor records, sealed identities and owner heads needed to validate a claim's causal chain; an isolated displayed status is not equivalent proof.
- **Historical producer pin**: The exact owner contract and software revision that created an original record, distinct from a later consumer/verifier revision and from the revision currently running.
- **Generation-bounded E2E case**: A historical test whose selected membership, source scope and policy generation are verified at its declared as-of; a changed boundary requires a separately identified case.
- **Owner-head parity**: Agreement of scoped evidence and conclusions under the same meaning-bearing original owner identities, versions and heads; independently advancing live reads are not automatically comparable.
- **Authentic-case falsifier**: A clearly labeled altered copy of a proven original case that tests whether a verifier or agent rejects a specified false claim; it is not authentic positive evidence.
- **Protected owner projection**: A bounded read-only conclusion produced by the protected financial authority from independently verified originals; it neither transfers financial ownership nor grants trading permission.
- **Consistent evidence capture**: A frozen owner-local observation whose records, heads and predecessor proof belong to one coherent read cutoff; independent authorities may have different cutoffs and must not be represented as one atomic global state.
- **Pre-registered answer oracle**: An independently reviewed, evidence-bound expected conclusion fixed before agent execution and withheld from the evaluated agent; the agent's own answer cannot validate itself.
- **Comparable live observation**: Independently acquired read-only views with matching meaning-bearing scope, version and owner heads; changed or unproved comparability is distinct from disagreement on equal evidence.
- **Agent execution trace**: An independently captured sequence of attempted and completed tool interactions and the agent's final answer; an agent-authored transcript or scripted fixture does not prove real model behavior.
- **Real-world E2E coverage**: The extent to which required cases have authentic, verifiable originals and negative controls; successful reasoning about missing originals does not supply that coverage.
- **Read-only evaluation boundary**: Independently constrained capability, filesystem and credential access that makes test observation non-mutating; an operation label alone does not prove safety.
- **Independent answer oracle**: Pre-registered, hidden assessment of required and prohibited evidence-grounded claims, distinct from a model-written answer or an owner status projection.

## Source observation

- **Selected account**: The exact authorized-for-observation source account and perp-market scope; parent and subaccounts are independent selections unless explicitly included.
- **Official position book**: A complete exchange-reported set of positions within one selected account's declared perp scope. It is not equivalent to fills or whole-wallet NAV.
- **Raw source evidence**: The original externally observed message and its provenance. It must not be reconstructed from a normalized representation.
- **Economic position state**: The economic meaning of a valid complete position book; numerically equivalent quantities represent the same exposure even when their raw encodings differ.
- **Evidence identity**: The provenance-bound identity of an actual received message, which can differ between observations even when their economic positions are equal.
- **Position transition**: A demonstrable change in economic exposure within an unchanged, complete selected-account scope, observed with unbroken prospective continuity.
- **First-known time**: When this system first received an observation locally. It is not interchangeable with the exchange event time or the later decision time.
- **Continuity gap**: A break in the ability to prove complete prospective observation. A reconnect baseline can restore a starting reference but is not a new entry signal.
- **Scope generation**: The validity interval for one declared selected-account and market scope. A materially changed scope begins a new generation and cannot inherit past prospective continuity.
- **Observer generation**: The identity and version of the overall observation configuration and its subscriptions, which is not itself proof that any individual selected account changed economic scope.
- **Selected-perp completeness**: Complete, authentic official positions and DEX coverage for one explicitly selected account's perpetual market scope; not the same as all-wallet collateral or related subaccount finance.
- **Whole-wallet financial completeness**: Evidence sufficient to characterize broader leader financial balances and collateral across relevant account types; not a universal requirement for fixed-k mirroring.

- **Canonical five-minute checkpoint**: A globally identified UTC five-minute sampling boundary for one selected source scope and policy version, distinct from an observed trade's first-known time.
- **Sampled position-state change**: A verified difference between admitted complete position snapshots at consecutive eligible checkpoints; intrawindow changes that revert before sampling do not produce a sampled change.
- **Canonical target-state signal**: A durable, provenance-bound desired leader exposure at a valid checkpoint, shared by independent financial consumers; it is neither a broker order nor trading authorization.
- **Checkpoint unavailability**: A scheduled source sample that cannot establish a complete, fresh, authentic state for its declared scope; it is not a flat position or a signal.
- **Checkpoint observation time**: The moment the source state was actually known and verified, separately recorded from the scheduled checkpoint boundary and the provider's earlier underlying state instant.
- **Target-state reconciliation**: A financial consumer's comparison of one verified desired leader exposure with that consumer's independently reconciled holdings and unresolved effects; target identity is not a buy/sell order.
- **Grid-timed source exit**: A verified leader reduction or close that enters the source target at an admitted periodic checkpoint, distinct from immediate independent follower-risk protection.
- **Canonical checkpoint outcome**: One durable, stable disposition for a source-account, scope, policy epoch and scheduled boundary; it exists for changed, unchanged, unavailable and baseline observations without implying a trade.
- **Recovery baseline**: The first independently verified complete source book after a continuity gap; it reestablishes a reference but cannot itself authorize new source-driven exposure.
- **Recovery reduction-only reconciliation**: An independently verified decrease of existing follower risk toward a restored complete source target, without admitting new exposure from a rebaseline.
- **Target-change signal**: A source-authoritative proof of an actual economic difference between successive eligible complete checkpoints in continuous scope, distinct from the checkpoint outcome and consumer execution attempt.
- **Single new-risk opportunity**: At most one independently guarded opening attempt per admissible target-change and per financial consumer, not an instruction to retry unchanged targets.
- **Copy mandate**: A frozen, signed relationship binding a selected leader source and scope to an explicitly identified follower pod/account, sizing and risk policy, and activation/exit behavior; not a second signal authority.
- **Activation baseline**: An authenticated complete initial source state when a copy relationship becomes effective, not an invitation to copy pre-existing leader exposure.
- **Full-target follow-on increase**: A new risk-eligible source increase that may target the leader's full currently verified exposure after a prior missed follower opening, distinct from a retry of the prior signal.
- **Pre-dispatch re-evaluation**: Rechecking a still-valid financial opportunity against fresh evidence while no broker order could yet have been sent; not an execution retry.
- **Mandate pause**: A prohibition on new follower exposure under one copy relationship while pre-existing financial exposure, risk and uncertain orders remain independently owned.
- **Netted follower order**: One broker order representing the net eligible change across individually risk-accounted follower pods, without erasing per-pod ownership or attribution.
- **Verified empty scope**: An explicit authenticated native position response for one declared selected market/DEX scope showing no positions; not an inference from omitted data.
- **Explicit domain transition**: A legal, independently verifiable move between typed states under one owning authority, with an original triggering event, predecessor, guard, journal effect and replay interpretation; not a status inferred from unrelated fields.
- **Source continuity state**: The independently durable per-selected-source-scope condition that determines whether successive complete checkpoint comparisons can produce genuine target changes, distinct from the outcome of any single checkpoint.
- **Mandate generation**: One immutable signed effective interval for a specific follower relationship and frozen policy; separate from CWSA's shared source-scope generation even when both refer to the same leader.
- **Unknown broker obligation**: Possibly dispatched, not-yet-terminal financial effects that retain reservations and require independent broker reconciliation, not a failed or rejected opportunity.
- **Scoped source fault**: A loss of verified complete state within one selected source scope, preventing that source's new risk but not independently valid sources unless shared dependencies/risk are affected.
- **Capability-specific qualification**: Independent engineering, operational-source, prospective economic and protected trading evidence; no single mutable readiness flag grants every capability.
- **Old-mandate residual exposure**: Existing follower financial positions or obligations still attributed to a superseded copy mandate; they remain risk-managed and cannot be silently reassigned or omitted from account exposure.
- **Opportunity expiry**: Immutable latest admissible opening time for one checkpoint-derived new-risk opportunity, no later than the next checkpoint or its earlier signed freshness deadline.
- **Cross-zero reversal**: A follower adjustment changing the sign of a position through flat; admission of the opening side requires distinct native execution and protected-risk proof, unlike a reduce-only close.
- **One effective opening policy**: Exactly one signed mandate policy generation permitted to create new exposure for a specific destination account/pod at a time, despite simultaneous read-only comparisons.
- **Forward-only cutover**: A signed future-effective change in authoritative financial policy that preserves historical journal and signer versions, outstanding broker effects, HALT and financial reservations through rollback.
- **Retired source policy**: An earlier observation or signal-timing policy that may be interpreted for historical evidence but must not create new prospective source opportunities or paper runs; retirement does not erase prior financial liabilities or certify its successor.

## Historical screening and execution proxies

- **Historical oracle clock**: A retrospective exchange/source-event timestamp available from recorded fills; not evidence of when the follower system first learned of that event.
- **Historical execution-price proxy**: A causally selected 1-minute bar price used to approximate, not attest, a later market execution.
- **Wallet robustness screen**: A rapid comparative estimate of potential follower economics across specified execution-price and cost assumptions, separate from complete portfolio-risk replay or scientific qualification.
- **Capacity proxy**: Historical completed-bar trading volume used to screen whether modeled participation is plausible; not an executable order-book depth or guaranteed fill.
- **Scenario sensitivity**: Variation in estimated wallet performance when delayed timing or adverse execution costs change; not a separate strategy or an authorization gate.

## Follower research and authority

- **Desired source exposure**: The selected account's verified economic position vector; not an instruction or proof of follower holdings.
- **Paper intent**: A proposed simulated action derived from verified source evidence and the paper policy; it is not a real order or permit.
- **Terminal modeled attempt**: A completed decision to make at most one modeled entry attempt for a given eligible paper intent; later exit protection remains a separate responsibility.
- **Protective reduction**: An attempted decrease of independently verified follower risk, distinct from admitting new exposure, with unresolved effects remaining financially accountable.
- **Modeled follower inventory**: Outstanding positions and unresolved exposure in the research/shadow financial account. Missing source/market data does not imply flat inventory.
- **Unresolved exposure**: An open, incomplete or uncertain financial effect that must remain accounted for until independently reconciled; it is not erased when an intent becomes terminal.
- **Durable receipt**: An observation or effect whose persistence can be verified after a process interruption; a successful delivery acknowledgement is not itself proof that a financial effect occurred.
- **Wire contract**: The versioned meaning and identity of a record exchanged between independent authorities; historical signed representations retain their original meaning.
- **Validated evidence**: A well-formed observation under its declared contract, distinct from complete/prospective evidence and distinct from permission to act.
- **Transition identity**: The unique provenance-bound occurrence of a state change, which may differ between events that reach the same economic state.
- **Consumer cursor**: One consumer's durable position in a verified evidence stream, separate from the producer's cursor and other consumers' acknowledgements.
- **Durable HALT**: A latched financial risk restriction that cannot disappear through a transient diagnostic update. Any reset requires its own authorized, auditable transition.
- **Operational readiness**: The current evidence of source, market, transport, worker and account-data availability; it does not override a financial risk latch or scientific verdict.
- **Capability-scoped admission**: A decision about one specifically requested operation using only its applicable evidence and authority prerequisites; read-only observation does not imply permission to trade.
- **Evidence availability**: Whether required evidence is valid, complete, fresh, supported and currently accessible; availability does not imply positive scientific or financial authorization.
- **Wallet eligibility**: The current deterministic evidence that a wallet meets configured participation requirements, distinct from evidence that its strategy is economically profitable.
- **Financial authority**: The system that owns financial state transitions and risk admission for its context; PM-03/04 own simulated research finance, while Guardian independently owns protected production finance.
- **Scientific qualification**: A separately evidenced result of a specified prospective economic evaluation; not synonymous with valid input, passing engineering tests or a paper run.
- **Assessment run**: An idempotent transformation of exactly pinned private source/research inputs into an immutable health report. Orchestration retry or completion does not certify the underlying economic evidence or authorize an action.
- **Agent diagnostic evaluation**: A controlled assessment of whether a research agent correctly interprets available evidence and abstains when it cannot; it is not a test of executable follower profitability.
- **Quarantined observation**: Received evidence that cannot support current prospective continuity until its affected scope and cause are resolved; quarantine is not proof of a position close or a financial HALT.
- **Intentional semantic correction**: A declared, independently justified change to previously incorrect future behavior; not permission to rewrite earlier signed historical records.
- **Trading authorization**: Permission from the protected execution authority, not created by research selection, source observation, an AI evaluation or Pydantic validation.

## Invariant and source-effect vocabulary

- **Domain-owned transition**: A state change whose preconditions, permissible successor and postconditions are checked by the existing authority that owns the state; transport delivery alone does not make it valid.
- **Source-notional fixed-k**: Signed selected native source quantity valued using an independently observed source mark, multiplied by frozen k, then converted to follower native quantity using an independent follower quote; not an automatic native-unit multiplier or source-equity weight.
- **Source mark**: Authenticated and time-bounded leader-contract valuation evidence, separate from any follower execution quote even when numerically equal.
- **Follower quote**: Independently observed destination-market price evidence used to translate target notional into native follower quantity; not proof of leader position or source mark.
- **Source packet**: Authenticated transport envelope of individually verifiable source events; not an atomic transaction across all downstream financial consumers.
- **Packet completion**: Proof that every event in a transport envelope reached an accepted terminal processing state; a durable accepted prefix is incomplete delivery.
- **Per-event source effect**: An accepted provenance-bound source occurrence whose owning consumer atomically persists its progress and corresponding local effect; other consumers may be at different stream positions.
- **Admissible source mark**: A provenance-verified, instrument-matched leader valuation known by the relevant decision cutoff and fresh under the declared policy; not a follower quote or silent historical-price fallback.
- **Broker terminality**: Independently evidenced completion of a broker order's economic obligations, requiring status, executed quantity and coherent cutoff history to agree; a status label alone cannot settle unresolved effects.
- **Semantic journal verification**: Checking historical state transitions against the business rules valid for their original contract version, in addition to hash/sequence integrity, without rewriting past records.
- **Recovery evidence verification**: Independent assessment of incident-specific proof under current financial/source authority, separate from authentication of the person requesting clearance.
- **Predecessor chain proof**: Signed linkage between a stream occurrence and its verified prior stream identity, distinct from a signed current-head digest without demonstrable linkage.
- **Consumer effect identity**: Stable, provenance-bound identity of one source occurrence's result for a particular destination portfolio, run, pod and frozen policy, retained across retries and restarts.
- **Missed due opportunity**: A valid previously scheduled entry whose original deadline passed without a verified attempted execution; source replay does not reset its first-known time.
- **Source-mark admissibility window**: The bounded interval during which authenticated leader valuation evidence remains suitable for a particular later decision; validity of the original position transition alone does not extend that interval.
- **Account-scoped financial HALT**: A protected follower account's latched restriction on new risk caused by financial incoherence, distinct from a source-stream continuity gap or a system-wide observer outage.
- **Signed stream-head anchor**: A trusted statement of a particular source stream's selected scope, epoch, cursor, original chain head and cutoff from which future continuity can be independently checked; it does not prove all earlier history.
- **Scoped packet quarantine**: Preservation of one invalid attributable stream without contaminating independently valid streams in an authentic shared envelope; unresolved packet completion remains explicit.
- **Expired new-risk opportunity**: An original time-limited entry that is no longer eligible after its agreed deadline and grace; later replay does not create a new first-known signal.
- **Mark freshness policy**: A versioned rule stating which authenticated leader valuation evidence remains admissible at a later decision time, independently of the continuing validity of its position book.
- **Canonical broker order observation**: A provider-status interpretation retaining original identity, quantities, execution evidence and historical cutoff; not itself a release of follower financial risk.
- **Forward semantic checkpoint**: A new independently reconciled financial starting boundary that preserves and does not rewrite uncertain earlier history; not a permit to resume new risk.
- **Recovery request authority**: An authenticated, revocable role permitted to request verification of one particular HALT remediation, distinct from proof that remediation succeeded.
- **Versioned source cutover**: A reviewed boundary at which successor source evidence adopts a new authenticated wire interpretation without changing prior evidence or creating retrospective first-known events.
- **Resolved-with-quarantine packet**: An original envelope for which one or more invalid events were explicitly quarantined and their continuity separately re-established; distinct from full acceptance of every original event.
- **Causal paper-effect receipt**: An independently durable simulated outcome attributable to one original source occurrence, valuation decision, portfolio/pod and frozen policy without asserting a global multi-ledger transaction.
- **Economic correction revision**: An explicit change in prospective financial interpretation accompanied by separately identified comparison evidence; it does not rewrite historical results or automatically approve a revised risk release.
- **Proof-carrying transition**: A change of owned state justified by immutable original evidence, causal scope, applicable policy and independently verified authority; an observation or delivery alone is not permission to change state.
- **Owned effect**: A durable result, rejection or unresolved obligation recorded by the one context authorized to change that state; other contexts retain independent progress.
- **Capability-scoped acceptance**: Evidence that one named operation is correctly and safely implemented, distinct from broader deployment, scientific qualification or permission to take financial risk.
- **Nonrewinding rollback**: Restoring compatible program behavior without undoing original source evidence, executed economic effects, account risk latches or trusted signing history.
