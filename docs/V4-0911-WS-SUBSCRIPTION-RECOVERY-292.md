# 0911 official-source WebSocket budget recovery (#292)

> **RETIRED / NON-EXECUTABLE HISTORICAL RECORD (2026-11-14):** The V4 first-known T0+300 operational policy, sixteen-portfolio paper executors (`pm_v4_selected_positions`, `pm_v4_sixteen_paper`), and `scripts/v4_native_budget_release_292.py` were retired and removed from the repository per [the V4 retirement ADR](decisions/2026-11-14-retire-v4-t300-source-policy.md). Do not execute commands in this document; use CWSA (`copytrade-cwsa-5m-source-chapter2.service` / `copytrade-cwsa-5m-paper-chapter2.service`, see [CWSA Chapter 2](CWSA-CHAPTER2-20261112.md)).

**2026-11-11 supersession boundary:** This remains the accurate **existing official transport recovery and original GAP evidence**, not the preferred future scaling architecture. For new wallet-source transport use the [Vike-first ADR](decisions/2026-11-11-vike-first-wallet-source.md); it does not implement a replacement or remove the official complete-position source authority. This 7-at-a-time rotation cannot qualify simultaneous 14/14 continuous coverage and must not be described as such.

**2026-11-11 decision:** Recover the existing 16-portfolio SHADOW 0911 campaign without new broker permissions, campaign identity changes, journal reset or k/T+300 changes.

## Provider boundary

Hyperliquid documents a limit of **10 unique user-specific WebSocket users per IP**. The running 0811 observer reserves three user slots. The new 0911 V4 source therefore admits a maximum of **seven users at once**, reusing one socket and opening the next only after the previous session closes. Its 14 selected parents form two deterministic seven-user cohorts.

The official selected registry seals and SHA-pinned 0911 campaign stay unchanged. This is *not 14-account simultaneous continuity*. A process restart records GAP for all 14 parents, active cohort accounts require genuine fresh non-actionable BASELINE, off-cohort parents stay in durable GAP, and a cohort switch appends NATIVE_BUDGET_ROTATION_GAP. A rejoin creates a new source epoch; no missed historical transition or earlier first-known time is manufactured. The initial observation cannot generate new-risk paper intent. Paper may consider genuinely continuously observed subsequent changes only under the existing T+300, valid native market, pending/inventory and Guardian-independent research guards. Off-cohort coverage is UNKNOWN and loses potential signals.

Native source flags: --native-user-budget 7 --native-rotation-seconds 420. The allowed rotation window is 330..3600 seconds so genuine T+300 due decisions may occur while an account remains subscribed. A rejection or missing ACK stops the source with explicit BLOCKED status instead of rapidly restarting and growing journal WAL. The default 0811 source has only three users and requires no rotation.

## Runtime sequence and gates

1. Preserve existing 0811 services. Reconfirm original 0911 backup receipts and zero active 0911 readers/writers, source tail, original private metadata registry seal, 32/32 financial ledger replays, root free space, unit pins and unchanged frozen campaign SHA.
2. Stage a new exact-SHA isolated release including merged PR #303 offsetting-pod marks. Review the original 90-v4-sqlite-292 overrides and create *additive reversible* 95-v4-native-budget-292 overrides only for the three 0911 units. Do not use compact-evidence or any broker.
3. Start 0911 source only. Verify the original cumulative new BASELINE on all 14 parents after both cohorts rotate, with no more than seven simultaneous 0911 user-specific subscriptions. Only the currently subscribed cohort can be current; all off-cohort accounts must be GAP. Record bounded write latency, source/main/WAL growth, provider rejects, timestamps and 0811 unchanged PID/health.
4. Rerun 32 financial ledgers, verify original heads and unresolved positions. Start the 0911 V4 paper reader from the same compatible SHA only if the source and ledger gates pass. Start the separate Pydantic paper reader only if independent account and source-gap controls pass. Never infer flat or clear unresolved exposures to force a startup.
5. Roll back by first stopping the two 0911 paper consumers and then the source, preserving heads and paper ledgers; remove only the additive 95 override and reload systemd. Existing 90 overrides and previous release remain preserved. Do not restore older SQLite data or truncate active WAL.

## Provider refusal after rotating two seven-user cohorts — degraded recovery

The first real 0911 SHA-pinned release (`2598b25f55b7d542e351ed6fbcd4b5c233657a30`) produced **14/14 cumulative** genuine baselines over two serial seven-user official WS cohorts. On the third cycle, Hyperliquid accepted three renewed baselines but rejected the remaining four with `STREAM_NATIVE_SUBSCRIPTION_REJECTED`. The source exited `STOPPED_NATIVE_SUBSCRIPTION_BLOCKED` with no restart and the WAL returned to 0 bytes. **Serial disconnection did not sustainably evade the IP-wide quota.** The provider's exact release or TTL window is unknown; do not substitute an inferred timer or a retry storm.

The degraded recovery keeps all 14 parents in the original source campaign and original SQLite/GAP journals but maintains a fixed seven-parent official WS cohort:

`S035, S051, S053, S064, Whale_0x5f94, ACT04, ACT08`

The five P1/P14/P16 original parents take priority, with two additional research sources ACT04 and ACT08. Seven other selected parents remain in durable `GAP`, with no new-risk admission. The mode is `DEGRADED_PARTIAL_OFFICIAL_SOURCE`, **not 14/14 continuous coverage**. One persistent socket subscribes this fixed cohort with no intentional rotation. Every reconnect requires a new non-actionable baseline. Another provider rejection stops the source without restarting.

To deploy, stage the updated, tested commit. Then run `scripts/v4_native_budget_release_292.py --phase stable-apply --expected-sha NEW_COMMIT_SHA --apply`. The source and both paper units must be stopped, while 0811 is active. Three additive exact-SHA overrides are created: one `96-v4-stable-source-292.conf` and two `96-v4-paper-cursor-292.conf`; old 90/95 source and paper overrides and all original source/PM03 financial journal bytes are preserved. Start source alone; accept 7/7 new official baselines and seven GAPs. Replay 32/32 financial ledgers and inspect original heads/WAL before starting V4 paper. Start Pydnative paper only after V4 admission and health. Roll back with `--phase stable-rollback --expected-sha NEW_COMMIT_SHA --apply` only when all 0911 units are stopped, preserving all prior 90/95 pins.

Only source-covered portfolio pods can become candidates for paper decisions. Source-uncovered pods remain blocked under the existing complete-book, source gap, market quote, T+300, frozen k, risk budget and unresolved-exposure controls. A healthy subset is not a full 16-portfolio source-continuity claim, and no broker/scientific/trading permission is created.

## Bounded paper-reader startup follow-up (2026-11-11)

The source release at Git SHA `2598b25f55b7d542e351ed6fbcd4b5c233657a30` passed 14/14 cumulative official baseline acceptance (7 current, 7 explicitly GAP). The initial 0911 V4 paper restart was conservatively stopped **before 16-ledger admission** because the paper reader's prestart cutoff used an unindexed `julianday(json_extract(payload, '$.first_known_at'))` predicate over the original 12.65 GB SQLite and its 400k+ source rows. It held a read connection for minutes, accumulated source WAL, and approached the paper unit's 1 GiB cgroup memory limit. No broker or real trade was involved.

The corrected **live-service-only** reader mode (`source_startup_policy=NO_DOWNTIME_REPLAY`) uses the original `(source_id, seq)` indexed head with `ORDER BY seq DESC LIMIT 1`. It explicitly fences every original receipt already persisted at this paper process start: skipped downtime transitions are **not** replayed as fresh paper risk, while future source receipts still pass original `first_known_at`, source proof, T+300 and PM03/PM04 guards. Historical and backtest users retain the prior `AS_OF_RUN_START` semantics by default; they can legitimately construct a reader after an original source event with a declared earlier run start. The service explicitly opts into the conservative mode, so no historical contract is silently changed. A durable ledger cursor ahead of the original source head fails closed. This does not change original source bytes, PM03 financial heads, manifest `started_at` or historical signed proofs.

To deploy this reader without restarting the healthy 0911 source, stage the **new** committed exact SHA and use the source-preserving paper-only action of `scripts/v4_native_budget_release_292.py`:

```sh
uv run --frozen --group dev python scripts/v4_native_budget_release_292.py \\
  --phase stage --expected-sha NEW_COMMIT_SHA --apply
uv run --frozen --group dev python scripts/v4_native_budget_release_292.py \\
  --phase paper-apply --expected-sha NEW_COMMIT_SHA --apply
```

This writes only two additive `96-v4-paper-cursor-292.conf` 0600 overrides for the stopped 0911 V4 and Pydnative paper readers. The live source stays pinned to `2598b25`, both paper readers get the new tested SHA, original source `95` and three original `90` overrides remain unchanged, and systemd daemon-reloads without starting a service. Review source/paper compatibility and 32-ledger financial replay before any start. Roll back while both paper units are stopped with `--phase paper-rollback --expected-sha NEW_COMMIT_SHA --apply`: remove only the two `96` overrides, preserve all source and financial evidence. **No live source restart, WAL checkpoint, journal pruning or trading authorization.**

## 0911 paper tick historical-proof hot path (further observation)

After the stable seven-parent source reached genuine baseline for all seven original parents, the optimized V4 paper reader **admitted all 16 virtual financial ledgers**, but the first paper tick again pinned the large original SQLite read and approached its 1 GiB memory limit. The existing original v1 `verify_official_position_transition` could execute an unbounded `json_each(e.receipt_refs)` fallback to locate a stale old receipt for a pending T+300 intent, even though the currently committed stream head already proved that the source was disconnected, in a new epoch or had a newer first-known completed state. The paper reader was stopped before a sustained OOM/restart loop; the source remained active with 0 restarts and WAL returned to zero.

The corrected proof verifier rejects these **definitively invalid** old pending intents from the indexed current stream head before trying the v1 full-history locator. It compares complete fresh baseline validity, connected transport, actual current stream epoch, latest completed source-state clock and (when requested) current selected native positions. Only positive candidates are passed to the unchanged original complete source receipt/reference/native-wire verifier; missing locator proof is never manufactured. Historical v1 verification and valid same-epoch proofs remain available. Two adversarial tests strip the locator indexes from synthetic original journals and prove that disconnected and same-epoch re-baselined stale pending receipts fail without invoking `json_each`.

To deploy **without restarting the healthy stable source**, stage the new exact Git SHA, then apply the owner-only paper-only `--phase proof-fast-apply --expected-sha NEW_COMMIT_SHA --apply`. This verifies that the real active source PID is still pinned to stable source SHA `0c696a61f7ada0a3857f69a0bfa4e9bc20d07d21`, requires both paper units stopped, preserves all original 90/95/96 overrides and creates only two additive `97-v4-paper-proof-fast-292.conf` overrides. It does not start a service or change financial source data. Rollback removes only the two 97 overrides with `proof-fast-rollback` after stopping paper units.

Paper acceptance requires `ADMITTED_VIRTUAL_PAPER_ONLY` and an actual completed `V4_SIXTEEN_PAPER` tick without prolonged source-reader/OOM pressure; verify 16 ledgers, source-gap policy, 32/32 independent finance replays and 0811 isolation before starting separate Pydnative. If this still fails, **stop paper** and preserve source/GAP and financial evidence; do not infer recovered paper economics.

## Acceptance interpretation

Tests verify fixture cohort rotation, original signed/stream journal BASELINE/GAP and bounded read/finance contracts. Real deployment requires two cohorts' provider-accepted source books, preserved 0811 health and independent financial replay. Historical full-chain certification, continuous 14-account simultaneity, market-cost economics, scientific qualification and trading authorization remain separate and are NOT implied by these checks.
