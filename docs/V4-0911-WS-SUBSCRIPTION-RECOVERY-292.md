# 0911 official-source WebSocket budget recovery (#292)

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

## Acceptance interpretation

Tests verify fixture cohort rotation, original signed/stream journal BASELINE/GAP and bounded read/finance contracts. Real deployment requires two cohorts' provider-accepted source books, preserved 0811 health and independent financial replay. Historical full-chain certification, continuous 14-account simultaneity, market-cost economics, scientific qualification and trading authorization remain separate and are NOT implied by these checks.
