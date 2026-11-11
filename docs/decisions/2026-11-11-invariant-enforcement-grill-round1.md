# ADR: Invariant-enforcement grill, Round 1

Date: 2026-11-11
Status: Owner-approved design (Q1=B, Q2=A, Q4=B). Documentation only; NOT implemented, deployed, merged, scientifically qualified or trading-authorized.

## Context
The November 11 cross-repository implicit-state-machine audit found eight residual contract concerns despite the earlier 28-family Pydantic-native acceptance. The observed-paper execution path currently supplies follower mid-quotes to both source_marks and follower_marks, while the fixed-k calculator explicitly requires independently observed marks. Protected Guardian and research PM03/PM04 must retain separate financial authorities.

This ADR extends the approved November 9 domain partition, source-effect decision and November 8 T+300 policy without rewriting those historical records.

## Q1: Domain-owned transition enforcement (APPROVED, option B)

Each existing state authority validates its own transition preconditions, allowed successor states, immutable identity, and domain-specific postconditions before making a durable commit. On replay validate semantic state under the version that governed the original event where feasible; preserve old signed bytes and SHA chains.

ObservedAccount controls complete selected-account source and continuity; PaperOpportunity controls eligibility and original T0+300; PM03/PM04 control research financial accounting and unresolved effects; Guardian alone controls protected financial admission.

Prefer narrow, versioned Pydantic boundary contracts and pure transition functions. Reuse existing authoritative SQLite journals; no central state framework, second financial ledger, global WalletState, or blanket full-state checks on every heartbeat. Invalid transitions fail closed with scoped diagnostic/quarantine; never silently infer a flat position or clear HALT.

Rejected: globally centralized state engine; monitoring-only invariant enforcement.

## Q2: Fixed k replicates source notional (APPROVED, option A)

For each native selected contract:
- source_notional_usd = leader_signed_native_qty * independently_observed_source_mark
- follower_target_notional_usd = frozen_k * source_notional_usd
- follower_target_native_qty = follower_target_notional_usd / independently_observed_follower_quote
- Then apply native lot rounding, follower risk and budget controls.

Source mark and follower quote are separate evidence roles with independently validated identity, provenance, freshness and timestamp semantics, even when their numerical prices are equal. A missing or stale required price blocks new-risk admission, but does not force an existing holding flat.

Preserve the existing policy identifier FIXED_K_NATIVE_QUANTITY with its established source-notional meaning, including signed release compatibility. Leader whole-wallet NAV remains optional; ALLOCATION_OVER_LIVE_NAV is an explicit legacy opt-in. Fixed k is not a claim of leader-equity fidelity.

Known discrepancy: the V4 observed-paper path in src/copytrade_pm/pm_forward_observed_paper.py supplies one set of follower quote midpoints to both mark parameters of target_from_fixed_k in pm_exposure_sizing.py. This requires implementation remediation and causal comparison using authentic independent marks, including divergent-price, stale/missing-price, native-step and limit test cases. No historical result may be silently rewritten.

Rejected: redefining k as a naive native-unit multiplier.

## Q4: Per-event atomic source processing (APPROVED, option B)

A signed packet is a transport envelope, not a global financial transaction. For each accepted event, verify immutable source identity, signed bytes, scope, epoch, cursor and predecessor-chain linkage. Commit that consumer's accepted cursor and local effect atomically. Expected predecessor must be checked inside the transaction (or protected by a provable exclusive writer), never only from a stale pre-transaction read.

Consumers have separate durable cursors. Exact duplicates replay idempotently; identity collisions with different content fail closed. A crash after a valid prefix but before packet completion must resume without skipped events or duplicate effects. Packet completion means all contained events reached an accepted terminal processing state; partial progress is explicitly inspectable.

Preserve separate PM03/PM04 and Guardian financial authorities. No cross-database two-phase commit, global consumed flag, or global exactly-once claim. For the distinct V4 ObservedPaper.run.record route, require a deterministic source-to-effect identity and crash/replay acceptance before asserting equivalence with the existing PaperJournal.consume_source_effect pathway.

Signed wire predecessor proof may need a versioned contract extension; do not reinterpret old signatures or mutate historical hashes.

Rejected: globally atomic packets and cross-portfolio transaction coordination.

## Consequences / next frontier
Round 2 must settle admissible leader mark evidence and missing-price policy, broker terminal state and reservations, Guardian journal/replay semantic validators, scoped recovery receipt authenticity, cursor fencing and partial packet crash semantics. This ADR does not approve code changes, protected source activation or broker orders.

Relevant prior ADRs: docs/decisions/2026-11-09-pydantic-native-domain-interfaces.md; docs/decisions/2026-11-09-pydantic-native-failure-and-spec-readiness.md; docs/decisions/2026-11-08-position-first-t300.md.
