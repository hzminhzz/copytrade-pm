# ADR: Vike-first wallet transport with reconciled position authority

**Date:** 2026-11-11
**Status:** APPROVED TARGET ARCHITECTURE; opt-in dual-channel observation, original-byte verified complete-perp REST census and isolated **candidate-only** crash-safe SQLite projection IMPLEMENTED/TESTED. V4-admissible reconciled source proof, live 14/14 continuity and canonical paper cutover remain PENDING. See [dated evidence](../V4-VIKE-FIRST-MIGRATION-PROGRESS-20261111.md).
**Supersedes:** the *transport scaling preference* of [2026-11-08 position-first T+300](2026-11-08-position-first-t300.md), **not** its complete-position, timing, paper-finance or risk semantics.
**Evidence:** [V4 canonical paper campaign](../V4-CANONICAL-FRESH-PAPER-20261111.md), [0911 official WebSocket budget recovery](../V4-0911-WS-SUBSCRIPTION-RECOVERY-292.md), [isolated Vike observer](../FORWARD-PAPER-VIKE-MIGRATION-20261108.md), and the live Vike stream registry checked 2026-11-11.

## Decision and current state

**New wallet-ingestion designs use Vike as the preferred scalable transport** instead of scaling direct Hyperliquid user-specific WebSocket subscriptions across every source wallet. Direct Hyperliquid APIs remain a bounded fallback and an independent source of complete-book baseline/reconciliation proof. This is a transport decision, **not** permission for raw vendor fills or position-change notifications to become trading signals.

**Observed current state when this ADR was prepared:** `copytrade-v4-sixteen-source-0911` still uses the official complete-position observer and the shared-IP 7-of-14 selected-parent cohort; seven other parents are explicit GAP. `copytrade-v4-selected-positions-0811`, `copytrade-v4-minute-0811` and `copytrade-v4-canonical-sixteen-1111` were running. The canonical paper service was pinned to Git `1a005e47155f157ad2326fdf1ff3186b2e3b90d3`, while 0911 source was pinned to `0c696a61f7ad`; these are **dated observations**, not timeless deployment facts. Inspect the live OS, service PID, real release checkout, SQLite and original journals afresh on every task. PR #308 merged the canonical paper implementation; it did **not** implement or activate a Vike-derived complete-position source.

The previously approved [official-position-first ADR](2026-11-08-position-first-t300.md) remains the **binding current implementation contract** until a versioned, independently verified replacement is accepted. No Vike position reconstruction, 14/14 continuity or paper/Guardian source cutover is asserted here.

## Single authority seam

```text
Vike provider transport (wallet-filtered live events, cursor, REST)
 + bounded official Hyperliquid independent baseline and verification
       |
       v
immutable source observations (provider, account, DEX, event ID,
event time, first-local receipt time, payload hash, stream epoch, gap)
       |
       v
reconciled complete selected-account position book
(baseline + signed native quantities + complete changes + official parity)
       |
       v
versioned causal position transitions (BASELINE / OBSERVED_STATE_CHANGE /
UNCHANGED / GAP / STALE / RECONCILIATION_MISMATCH)
       |
       v
existing first-known T+300 paper source / PM03 / PM04 / Guardian boundaries
```

A **transport event is not an account state**. A Vike `hl.positions` notification describes a filtered position event; it is **not** proof of the full selected-account open-position set. A Vike `hl.fills` row is one fill; even `position_after` fields do not establish complete account coverage. Only a verified full selected-account baseline followed by gap-free, idempotent, deterministically ordered changes and periodic independent reconciliation may emit a complete derived SourceBook. Make the baseline identity, scope and provenance explicit. On mismatch, stale data, unknown DEX/market, unselected account, missed fill or reconnect, mark source ineligible and emit `NO_TRADE` for **new risk**; do not silently flatten existing follower inventory. The independent Guardian owns financial protection.

Source scope is the sealed SQLite-selected parent and only explicitly selected subaccounts, across every selected perp DEX/HIP-3 market. Preserve contract native signed quantities, size precision, leverage/margin mode as applicable, and position reductions/hedges; do not infer source equity or combine unrelated child-account NAV. Fixed-k uses native quantity and independent follower price, not mandatory leader whole-wallet NAV. The existing [sizing policy](../RISK-BUDGETED-K-SIZING-20261106.md) and [source authority](2026-11-08-position-first-t300.md) own these invariants.

## Vike transport contracts to validate during implementation

Live Vike stream registry, checked 2026-11-11:

| Contract | Verified provider behavior | Required consumer behavior |
| --- | --- | --- |
| Endpoint | `wss://stream.vike.io/v1/stream/hl` | Dedicated key in a private environment file; keep secrets out of Git/logs/query strings |
| Channels | `hl.fills`, `hl.positions` | Verify exact normalized event schema and actual selected-account coverage in a real canary |
| Wallet filters | `wallet` list accepts at most **1,000** addresses per subscription filter | Resolve SQLite identities first; constrain scope to selected accounts |
| Small fills | `hl.fills` default `min_usd=1000` | Explicit `min_usd: 0` when full small-fill evidence is required; independently prove WS-vs-REST parity; historical filter acceptance alone is insufficient |
| Limits | One connection per API key per stream path; three per account/path; 100 subscriptions per connection | Reuse a single stream and avoid concurrent reconnect/replacement storms; close 4410 means newer connection displaced this one |
| Cursor | Provider cursor retention **3 days**; HL REST catch-up `/v1/hyperliquid/stream-events` | Persist cursor atomically with evidence; detect gap/expiry, recover history only as retrospective observations |
| Reconnect | Provider documents close codes and server ping cadence (15s) | Verify slow-consumer, restart, lost-frame, duplicated-frame and cursor-exhaustion handling under actual load |

The provider registry establishes **capability**, not guaranteed full selected-account delivery, parent/subaccount mapping, completeness of `hl.positions` snapshots, exact at-least-once replay semantics, clock SLA or live stream latency. Validate event identifiers, `event_id` deduplication, signed native quantities, out-of-order timestamps, retention, and unsupported/invisible markets against raw captured frames **before implementing assumptions**. Preserve the raw immutable event and mapping versions.

## First-known, journal and risk invariants

1. Preserve *provider event time*, *actual local receive time*, *journal commit time*, *consumer decision time* and *modeled/executed order time* as separate facts. Never backdate a local first-known clock using an exchange timestamp or REST catch-up.
2. Initial baseline and reconnect baseline are **non-actionable**. Only a genuine, independently reconciled post-baseline position change may start the existing first-known entry clock.
3. First eligible new risk is attempted at **T0+300 seconds** (existing bounded grace); coalesced updates do not reset T0. Exactly one terminal modeled entry attempt per intent. A due check uses the latest complete valid position book, independent fresh quote, frozen original k, market constraints and PM03/PM04.
4. A valid source reduction, close or independent protective risk latch requests an immediate risk-reducing exit: no extra 300-second delay. Unpriceable/rejected exit leaves real modeled follower exposure unresolved.
5. A gap, stale/mismatched source, invalid identity or incomplete baseline cancels pending *new-risk* admission. It cannot retroactively create entries, infer an exit or erase original financial risk.
6. Preserve the current Pydantic contracts, original immutable stream/source/finance journals, PM03/PM04 risk, pod budgets, k-release identity, Guardian authority, and signed evidence. No migration by replaying historical vendor data as live events.

## Engineering backlog and admission gates

This ADR by itself did not implement the following. The [2026-11-11 evidence](../V4-VIKE-FIRST-MIGRATION-PROGRESS-20261111.md) records **partial** implementation: 14-wallet dual-channel read-only transport, original Vike notification journal, 14/14 SHA-archived independent official REST census, a bounded durable **candidate-only** account-state projection, and a live short canary with a position-channel GAP. No versioned causal complete-position source or paper cutover is proven:

- **Transport:** an isolated, bounded Vike-to-observation adapter with one durable cursor, raw event SHA, observed local timestamps, idempotent `event_id` handling, true `min_usd:0` parity, reconnect/fault coverage and source lag metrics.
- **Account authority:** initial independent official selected-account full position baseline; parent/subaccount and DEX census; signed native quantity transition reconstruction; periodic or event-triggered official reconciliation; fail-closed GAP/STALE/MISMATCH.
- **Compatibility:** versioned SourceBook-to-`OBSERVED_STATE_CHANGE` adapter retaining the current immutable paper proof/receipt contract, no change in first-known T+300, immediate exits, frozen-k, PM03/PM04 or Guardian.
- **Qualification:** prove **14/14 simultaneously continuous selected-account coverage**, per-account and per-DEX baseline/reconciliation, complete small fills (if fill-derived), bounded stream-to-local latency distributions, outages and after-recovery clock honesty, independent quote availability and adverse reconnect/restart tests. Cumulative baselines across rotating cohorts **do not qualify**.
- **Canary/cutover:** run parallel read-only observation against official proof, measure divergence and outages, validate exact installed release and rollback. Promote only with separately approved engineering, operational and research gates. Do not alter running 0811/0911 services, existing paper journals, official-source transport or funded execution by changing this ADR.

**Rollback:** retain the official transport as verified fallback, fence new-risk admissions during any provider switch, open a *new* observation epoch with a fresh non-actionable baseline, and preserve old source and finance journals unchanged. A fallback is not retroactive gap repair.

## Which document wins?

This ADR is authoritative for **future Vike-first transport preference and migration gates**. The [2026-11-08 position-first ADR](2026-11-08-position-first-t300.md) remains authoritative for **currently implemented source authority and T+300 behavior**. The [V4 canonical paper runbook](../V4-CANONICAL-FRESH-PAPER-20261111.md) governs the **current read-only paper campaign**; [qualification](../QUALIFICATION.md) and actual Guardian releases govern evidence and trading permissions. Dated experiments, incident reports and PR bodies provide history, not current run-state.
