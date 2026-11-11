# ADR: Canonical five-minute position checkpoints (design grill)

**Date:** 2026-11-11
**Status:** OWNER-APPROVED TARGET POLICY (Grill Q1=A; Round 2 Q3=A, Q4=A, Q5=A); Q2 PROVIDER AUTHORITY OPEN. Documentation only, not implemented, merged, deployed, scientifically qualified or trading-authorized.
**Scope:** Shared source-signal interpretation for `copytrade-pm` virtual paper and `prop-production` Guardian. Source-provider authority (Q2) and detailed checkpoint contracts are still undecided.
**Related current contract:** [Official selected-position first-known T+300](2026-11-08-position-first-t300.md). That contract and its running services remain unchanged pending a separately authorized, versioned release/cutover.

## Decision

Adopt a new **five-minute position-state sampling policy** as a prospective architecture target. At UTC checkpoint boundaries (00:00, 00:05, 00:10, ...), a single Canonical Wallet Signal Authority (CWSA) compares verified, complete selected-account economic position vectors with the prior admitted checkpoint under its declared scope and policy version. An actionable change produces a shared, durable, proof-carrying target-state signal consumed by all 16 virtual-paper portfolios and the protected Guardian. Unchanged positions do not produce a new trade instruction.

CWSA owns canonical checkpoint/time identity, verified account/scope and position-state interpretation, deduplication and signal provenance. It does **not** own follower financial inventory, broker permission, modeled paper fills, live execution, risk or HALT. Independent paper PM03/PM04 and Guardian retain their respective finance, verification, target application and journals. A shared source checkpoint is not a shared account order or global finance commit.

This **replaces event-triggered first-known T0+300 for the *new policy***; it does **not** preserve five minutes of minimum post-transition delay. A change immediately before a boundary can be acted on soon after that boundary, subject to proof, processing latency, quotes, risk and financial admission. A source round-trip within a five-minute interval may be invisible to the sampled policy. This is a strategy change requiring separately matched costed follower economics and prospective qualification; historical T+300 results are not equivalent.

A canonical checkpoint is not automatically an executable signal. A missing, stale, invalid or incomplete selected-account sample must not be read as a zero/flat position or a valid new-risk opportunity. Restart, reconnect, delayed samples and scope changes must not create retrospective source signals or reset a historical financial action. All **source-driven** increases, reductions, reversals and closes follow the five-minute sampling grid (Q5=A). Independently triggered Guardian risk limits, HALT and emergency protective actions remain active between checkpoints. Held follower inventory is not made flat by a missing sample. Detailed missing-checkpoint recovery and financial intent disposition remain undecided.

## Additional owner-approved Round 2 decisions (2026-11-11)

- **Q3=A — Bounded fresh-as-observed sampling:** At a scheduled UTC five-minute checkpoint, obtain the latest complete, authentic position state within a specified bounded observation/processing window. Record the scheduled boundary, underlying state time if available, actual local receipt, validation and publication separately. A sample obtained at 00:05:04 is not claimed to have been known at 00:05:00. The exact maximum source age and publication grace are **not yet decided**. Missing the window means unavailable, not time-travel recovery.
- **Q4=A — Complete target-state signals:** Publish the full verified desired position vector under the selected account, all declared DEX scope and policy/checkpoint identities, not an executable BUY/SELL delta. Consumers independently derive portfolio targets from frozen signed k and their own account/pod holdings; source state alone does not mint broker permissions. A duplicate target or repeated delivery never itself proves another order is necessary.
- **Q5=A — Source actions only at grid checkpoints:** Source-driven entries, increases, reductions, closes and reversals use the same sampling cadence. Intra-grid source changes may be missed. Guardian/PM03/PM04 independent loss guards and emergency protective actions are not grid-delayed. The later source-exit detection and execution cost are an explicit different economic policy requiring separate scientific and financial qualification.

These choices eliminate consumer-specific source timers but do not eliminate durable consumer effect identities, broker reconciliation, no-blind-retry behavior, source evidence qualification, or native financial risk.

## Q2 provider audit — Vike snapshot API (UNDECIDED)

**Direct provider verification, 2026-11-12:** Vike MCP `hl_market(view=positions, wallet=..., resolution=5m, start=..., end=...)` exposes five-minute historical position rows (48-hour maximum per wallet query); current positions can be wallet-filtered and are paginated by key. `hl_archive(view=datasets)` advertises a `date=latest` positions Parquet (all wallets/assets; sampled provider reply: 419,780 rows, `snapshot_ts=2026-11-11T17:04:00Z`, `generated_at=2026-11-11T17:07:19Z`), replaced around every five minutes. A sampled wallet's past rows ran at minute `:04`, `:09`, `:14`, not exactly UTC `:00`, `:05`, `:10`. The API showed an example wallet with multiple DEXs (HL, IO, XYZ and PARA). These facts make Vike strong for retrospective checkpoint modeling, not automatically an admissible low-latency live checkpoint feed.

**Provider schema caveats:** Vike `snapshot_ts` denotes ingestion write cycle and its `state_ts` typically describes source state **5–10 minutes earlier**. Cycles are irregular, often 5–7 minutes apart; a gap lasts longer. `latest` rows can retain closed positions from an older cycle for up to 15 minutes; only rows at the file's newest snapshot cycle are candidate current rows. Historical days can have missing snapshots and reconstructed hours from fills; archive positions use `Float64` size, not inherently exact native Decimal quantity. A per-wallet positions API that returns open rows alone does not authenticate a complete zero/flat account, all selected DEX coverage, or a coherent common cutoff. Per-row freshness, completeness and correct native precision must be established independently. Vike streams `hl.positions` / `hl.fills` are different event feeds and cannot be treated as full account-position books.

**Q2 remains OPEN.** Candidate B: native Hyperliquid complete selected-account REST snapshots at each checkpoint, independently compared to Vike historical/live observations. Unlike an official user WebSocket, REST polling need not consume user-specific WS slots, but rate/budget and all-DEX cross-call coherence remain to be measured. Candidate A: Vike-first snapshots only after measured freshness, exact-position and 14/14 scope coverage, provider gap/zero-book handling, and acceptable follower economics. Candidate C: explicit epoch-fenced qualified hybrid; never unverified automatic failover. No source authority or service is changed by this audit.

## Why this abstraction

The existing source-to-paper path schedules per-observed-transition T+300; `prop-production.v4_timing.V4ShadowProjection` separately schedules market-level T+300 eligibility. These implementations can diverge on local first-known time, coalescing and recovery. One checkpoint-state authority removes the *need for duplicated source timing*, not the need for independent Guardian verification and durable uncertain-broker-outcome recovery.

The alternative rejected for this *new policy* is to keep independent first-transition clocks for each consumer. The existing T+300 system remains a supported historical/current version until deliberately retired through a new contract and reversible release.

## Explicitly unresolved: next design frontier

- **Settled Q3:** UTC checkpoint identity plus bounded, actually verified source observation time; **unsettled:** numerical freshness/grace limits, cross-DEX consistency and late-sample discard rules.
- Missing checkpoint/gap semantics: rebaseline, resumed changes, restrictions on inferred exits and new risk.
- Target-state signal identity and deduplication across source generations, portfolios, delayed/replayed observations.
- **Settled Q4/Q5:** complete target-state signal and grid-timed source reductions/entries; **unsettled:** account-target convergence, pending/unknown broker outcomes, flip/partial-fill treatment and financial safety semantics.
- Provider evidence: official complete-position primary versus independently qualified Vike/hybrid (Q2 remains **OPEN**).
- Financial proof and release cutover: Guardian verifies signatures, complete scope, market/account finance and signed k; no execution permit from a source signal.

## Safety and migration constraints

No code, service, wire, source/financial journal, existing policy, signed release, tests or authorization is changed by this ADR. Do not reinterpret v1/v2 source receipts or old financial events under the new strategy; use a new policy/wire identity and explicit forward-only cutover. No retroactive alpha claim from historical fill timestamps. Missing external provider proof continues to block affected actions.
