# ADR: Official selected-position authority with exact first-known T+300

**2026-11-11 clarification:** [Vike-first source transport](2026-11-11-vike-first-wallet-source.md) is the approved *future scalable transport preference*. This ADR remains the binding **currently implemented complete-position authority, first-known T+300 and exit contract** until independently verified migration/cutover. The earlier decision to avoid mandatory fill-derived completeness remains current for live paper; any future fill-derived alternative must prove full selected-account baseline, gap-free reconstruction, official parity and its own release gates.

**Date:** 2026-11-08
**Status:** APPROVED FOR ENGINEERING; **NOT** approved for deployment or funded/broker trading.
**Parent:** [#197](https://github.com/hzminhzz/copytrade-pm/issues/197), implementation [#198–#203](https://github.com/hzminhzz/copytrade-pm/issues/200), PR [#206](https://github.com/hzminhzz/copytrade-pm/pull/206).

## Decision

For new forward-paper fixed-k research, the source of desired portfolio exposure is each **official Hyperliquid complete selected-account position book**, not a sum of Vike fills. Reuse `PersistentAccount.observe`, the E4 all-DEX parser, `pm_forward_source_observation` and the existing `PaperJournal` transaction. Within deliberately selected perp account scope, require exact default/HIP-3 identity, native quantities, DEX census, first-local receive time and continuity. Selected parent only is valid when explicitly frozen; selected children require separate complete observations. Leader whole-wallet NAV, unrelated child NAV, spot/vault and collateral diagnostics are not mandatory under `FIXED_K_NATIVE_QUANTITY`.

A new risk opportunity arises only from an actual **OBSERVED_STATE_CHANGE** in a continuous official stream after a baseline. An initial or reconnect BASELINE, unchanged frame, retrospective source event, fill recovery, gap or unverified flat is not an entry. Preserve the source event, local receipt, intent decision and simulated order clocks separately. Any eligible new risk enters **exactly T+300s from first known position transition**, subject to the existing grace, fresh quote, fixed k and PM03/04 risk limits. Updates within the delay coalesce without resetting T. A valid source reduction, close, pod stop or HALT attempts an immediate risk-reducing modeled order; rejected exits retain unresolved exposure.

Keep Vike for shared, first-known 1m market-price evidence and optional fill-research/consistency audit. Vike `hl.positions` changes or fill `position_after` fields are not independently complete account states. No mandatory fill parity or sub-$1k completeness certification is required for the position-primary decision. Historical PM-01 fill replay and immutable source tapes remain unchanged.

## Implementation seam

- **Selected position projection:** Existing official `PersistentAccount` classifies `BASELINE`, `OBSERVED_STATE_CHANGE`, `UNCHANGED_STATE`, `GAP` and duplicates. Its receipt is SHA-bound to the original frame and committed atomically alongside `observer_stream_events` in `PaperJournal`.
- **Paper acceptance:** V4 native path verifies the source receipt against its `observer_stream_events` record, raw-source SHA, epoch, event classification, position-change payload and checkpoint. New entries are blocked without the linked official proof. An epoch/gap discontinuity or changed latest source book before due cancels unexecuted new risk; it **does not** fabricate a close of held follower inventory.
- **Market identity:** A frozen Propr-display catalog is independent of quote availability. Official Hyperliquid `/info meta` per native DEX resolves current contracts and size precision; the configured minimum-notional value is explicitly an **estimated paper policy assumption**, not an exchange order-permission attestation. Silent native market mapping or CCXT fallback is forbidden for new V4 CLI launches.
- **Finance:** Reuse `PM04_PAPER_SOURCE`, PM-04 one-shot intent accounting, PM-03/04 native attribution/risk, and separate P1/P14/P16 virtual ledgers. Vike minute volumes cannot prove executable depth; no real/demo/funded broker route.
- **Restart:** Preserve versioned rulebook and market-contract SHA. Unrelated new listings do not change a selected contract's semantic identity; selected contract size, minimum assumption or native metadata changes fail closed. Preserve original v3 journals and service rollback.

## Timing and failure semantics

1. First complete official frame after connecting/reconnecting is a baseline. No T+300 starts.
2. First genuinely observed change at local T0 creates the pending source intent; later source changes update quantities, not T0.
3. At T0+300, evaluate the most recent eligible complete official book, independent fresh follower quote and PM03/04 risk; consume at most one market attempt for that intent. No five-minute heartbeat substitution or target chasing.
4. A source gap cancels pending **new-risk** entry and fences new admissions until a fresh baseline followed by a new real change. Pending/held follower inventory remains financially real and separately risk-managed; unverified flat is never an exit.
5. A verified source reduction or protective risk latch attempts a prompt modeled reduction, even between entry decision cycles. Unpriceable/rejected attempts remain explicit; no fictitious financial mutation.

## Evidence and explicit limitations

This is an **engineering design**, not evidence of positive net follower alpha, brokerage execution, exact market impact, complete contemporary Propr order permissions or deployed V4. Synthetic/recorded official-shaped test frames prove deterministic interface behavior, not independent prospective provider parity. Actual production-side chosen-wallet source freshness, connection budgets, current Propr catalog membership, and independently observed modeled execution economics require subsequent live shadow evidence. Separate operator permission is mandatory before installation, cutover, merge, retirement of CCXT market collector, Guardian changes or actual broker orders.

## Rejected alternatives

- **Mandatory fill-derived complete SourceBook:** Additional reconstruction and missing-fill/cursor complexity when an authoritative full selected-position observer already exists. Keep fills optional research evidence.
- **Pure five-minute snapshot replication:** Variable 0–300s entry age, intrainterval blind spots, delayed source exits and a different strategy policy.
- **Five-minute execution grid after aging:** Adds up to five minutes beyond the first-known T+300 policy. Treat it as a separately versioned economic experiment if ever desired.
