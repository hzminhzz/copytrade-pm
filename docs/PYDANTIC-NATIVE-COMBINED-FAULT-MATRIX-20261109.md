# Pydantic-native combined-failure adversarial matrix (pre-implementation)

**Date:** 2026-11-09
**Status:** Q37 **APPROVED COMBINED-FAULT ACCEPTANCE DESIGN**. NOT RUN, NOT VERIFIED, NOT AN IMPLEMENTATION.
**Prerequisites:** [Q3–Q34 approved design ADRs](decisions/2026-11-09-pydantic-native-domain-interfaces.md) and the binding [Q35–Q39 failure/readiness ADR](decisions/2026-11-09-pydantic-native-failure-and-spec-readiness.md). Quarantine by continuity impact and per-portfolio cursor/effect ownership are approved. Exact test harness and installed revisions remain S0/implementation work. [Single-family 28-row matrix](PYDANTIC-NATIVE-ACCEPTANCE-MATRIX-20261109.md) remains the canonical individual acceptance inventory.

## Why cross-family tests matter

Most implicit states are benign in isolation. A harmful effect can arise only when different lifecycle owners act in a particular order: a producer sees a source gap while a paper entry becomes due, a quote goes stale while a finance HALT persists, or a source file is published while a consumer transaction is uncertain. Pydantic validation does not serialize these transitions or make unrelated databases atomic.

Build deterministic fault scripts around **real existing public interfaces**, a controllable clock, durable temporary private SQLite fixtures, source-capture shape samples when available, optional event-bus scheduling, and explicit crash points. No broker route or real orders.

## Combined fault scenarios (APPROVED DESIGN, NOT RUN)

| Case | Related 28-family IDs | Fault/interleaving | Required invariant / negative oracle |
|---|---|---|---|
| **CF01** | 01,06,07,20 | Source changes at T0, paper entry pending; malformed *economic* frame at T+180; reconnect at T+310 shows same position | No due new-risk attempt from stale T0, no invented fresh transition or retroactively known frame; preserve first-known receipt and source gap evidence; do not close actual follower inventory |
| **CF02** | 02,03,15,19 | PM03 HALT for loss breach, then missing funding, stale follower quote, process restart and source reduction | HALT remains durable; no new risk; separately valid risk reduction can proceed only with current independent quote/inventory and no unknown dispatch; failed exit stays unresolved |
| **CF03** | 05,11,26 | Cancel acknowledgment arrives, late partial fill occurs, writer is canceled while commit may be in progress, restart receives duplicated snapshot | Preserve unresolved reservation until a later authoritative post-event snapshot; idempotent replay; never count cash/fill twice |
| **CF04** | 04,11,26 | Signed spool writer killed before fsync/rename, after rename but before cursor, and after cursor but before consumer ACK | No visible partially written final packet; no cursor advance beyond durable published packet; duplicate packet may be seen but no duplicate consumer financial effect |
| **CF05** | 06,17,26 | Selected account A changes relevant HIP-3 scope; shared A supplies two portfolios; B unchanged; one fanout consumer offline | Fence new-risk admission for A dependents only; B unaffected if evidence independently valid; A's held simulated inventory stays; recovering consumer has no skipped receipt |
| **CF06** | 08,09,10,21,22,27 | Legacy CCXT/Vike/public fill recovery records past trades during an official-source GAP, alongside historical PM02 fallback | Recovered/estimated data remains retrospective; does not prove official complete position or start T+300; old unqualified PM02 path cannot admit live paper |
| **CF07** | 12,24,25 | Acquisition generation swap concurrent with UTC bucket late correction and cache artifact partial write | Mismatched file/data generation rejected; sealed historic bucket remains immutable or explicitly version-corrected; no research qualification from corrupt cache |
| **CF08** | 13,16,28 | Grafana container still up but publisher dead, notification ACK recorded, CDP browser loses target | Health reads DEGRADED with authentic freshness, incident still active despite ACK, browser session invalidation cannot affect finance |
| **CF09** | 14,17,18 | Crash after registry native data file write but before metadata release pointer update; another process reads signed selection and maturity proof | No mixed authoritative generation; either prior coherent signed release or blocked; scientific maturity and raw receipt authenticity independently verified |
| **CF10** | 21,22,23 | Partial fills reconstruct closed episode; challenge had past payout but is now inactive; summary attempts to label portfolio current funded/positive | Historical approximation clearly marked; current funded false; no forward qualified follower return |
| **CF11** | 03,05,19,20 | Previously routed target survives terminal flat; legacy DUE bit and FROZEN status disagree; follower quote expires | No phantom new-risk or stale-mark requirement after independently verified full flat; still unresolved actual exposure remains blocked/protected and is not assumed flat |
| **CF12** | 01,07,09,10 | Equivalent raw position representation, source same-clock conflict, delayed trade correction, and out-of-order native clock | Equal numeric quantities not a new opportunity; source native clock conflict/gap handled explicitly; trade corrections and fill cursors cannot override official prospective observation |
| **CF13** | 04,14,15,26 | Source producer publishes packet, selection release is repinned, independent consumer restarts while Guardian remains HALTed | Pinned trust/selected identity must match before protected admission; no source packet or observer success can reset Guardian HALT or replay as a new entry |

**Coverage audit:** all **01–28** are referenced by at least one combined-fault scenario, but this is a **design mapping only** and does not satisfy any of the 28 individual closure tests. Combined cases must be independently executed and reviewed during separately authorized implementation.

## Source-to-effect trace expectation (proposed)

For each test, retain the original source event/receipt identity and first-known clock, a deterministic local stream cursor, the selected scope generation, any portfolio-consumer cursor, deterministic intent/effect key, journal commit evidence, simulated holdings/HALT snapshot and the final admission result. A failed/disconnected source cannot create a fresh T0 or an inferred position close. At-least-once duplicate delivery is permissible only when repeated financial effects are impossible.

### Actual code seams that must not be bypassed

- `pm_forward_continuous_transport.SerialWriter.submit()` shields an admitted in-flight commit from immediate caller cancellation. Test cancellation before enqueue vs after enqueue and after durable commit; no blanket assumption about an uncommitted job.
- `pm_forward_source_stream.PersistentAccount.observe()` currently raises for malformed replacement semantics, native clock regression and same-clock conflicting position. Approved Q35 requires an explicit **continuity fence** for affected critical official frames, rather than silently skipping one model-validation error.
- `PaperJournal.append_source_receipt()` commits source receipt and stream checkpoint in the **same database transaction**; retain this property.
- `PaperJournal.consume_source_effect()` atomically commits the source cursor and simulated effect **within one portfolio's journal** for its supported v1 event kinds; do not conflate that with `pm_forward_observed_paper`'s separate V4 event route, which needs its own idempotency acceptance.
- `pm_forward_source_fanout` imports verified receipts into separate portfolio journals and may partially complete fanout: no cross-DB exactly-once claim and no global cursor promotion from one successful consumer.
- `v4_source_spool.capture_once()` publishes independently signed packets and cursor files. Current newly created packet output uses its final filename before a full fsync, so CF04 is a **known targeted design repair**, not a verified atomic-publication guarantee.

## Approved stage-risk priority (not permission to run)

1. S0 archival replay/original wire SHA verification and deterministic fault harness, with no new live service.
2. S1 official source → typed transition → durable journal and spool crash cases; independent source/consumer continuation.
3. S2 PM03/04 HALT, protective reduction, cancel/fill and due/cancel interleaving cases.
4. S3 metadata, history and cache generation cases; S4 monitoring; S5 retirement reachability.
5. Bounded signed source/paper SHADOW canary after separately authorized installation; never substitute a simulated case for authentic first-known provider observations.

**No implementation or results** are asserted by this file. Q37 approves 13 combined-fault obligations across all 28 families, not their runtime success. See [design closure and readiness](PYDANTIC-NATIVE-DESIGN-CLOSURE-20261109.md).
