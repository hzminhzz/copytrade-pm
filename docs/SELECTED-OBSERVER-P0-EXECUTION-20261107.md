# Selected-scope observer P0 execution evidence — 2026-11-07

This is a **dated read-only VPS checkpoint**, not deployment approval or a live selected-portfolio canary. Recheck current SQLite, releases, service PIDs and provider quotas before acting. No private wallet addresses or keys are copied here.

## Verified live state

- Source checkout: clean isolated worktree based on reviewed `copytrade-pm/main` `bea8b7c09527266adfa0a6ab450b4cc50886c36f`. The main checkout contains extensive unrelated staged/unstaged work and was untouched.
- Registry physical health: `database_integrity=VERIFIED`; inventory SHA `b2e5ea14fc3f1b71778bc78f4a568b0e7ee711802e2ab3ebfd72ef282cbdb855`. The unrelated current research selection remains `BLOCKED_MISSING_EXTERNAL_PROOF`; no signature was invented or imported. Legacy importer was reported as `UNLOCKED_LEGACY_WRITER` and is not modified by this work.
- The running `copytrade-public-observer-p1p14.service` uses **old** release `27b7a6912c18f50eadb1e3fe08010dd0b42fce9a` (PID observed: 438441); the registry-control `current` symlink points to a different `b1dc9fd` release. Those are different authorities: do **not** claim that merging code changed the running PID.
- Independent legacy observer health: `DEGRADED_OBSERVER_ONLY`, process identity verified, five source aliases with receipts, 29 market quote tapes verified, multiple BTC/ENA/other quote-stale reasons, `order_route=NONE`, `paper_observed=false`.
- `copytrade-tracker`, `copytrade-source-abc`, `copytrade-ensemble` and the six protected `prop-production` services were running at the initial inventory and were **not** restarted or reconfigured.

## Measured provider constraints

- A live `source-abc` A-window at `2026-11-07T00:54:37.343387+00:00` had **10 distinct subjects**, **50 subscription ACKs**, **4 recorded connections**, 211 frames received and 147 stored. Session frame coverage is not proof of historical completeness. Later windows and other processes vary.
- A separate process TCP observation found **9 established TLS connections to Hyperliquid edge addresses** at one instant. This is only a TCP count, **not proof** that every socket was upgraded to a WebSocket or that the count remains constant.
- Official Hyperliquid limits currently document at most **10 WebSocket connections**, **10 distinct users across user-specific subscriptions**, and **1,000 subscriptions per IP**: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits
- Adding P1's three *non-overlapping* user identities to the 10-user A-window would demand **at least 13 distinct users**, before discovered children. Moving users among sockets does **not** reset the per-IP user allowance. A 3-socket P1 candidate at the observed 9-TCP reservation also lacks demonstrated connection headroom.
- The conservative ignored `.workspace/selected-p1-diagnostic-20261107.json` and P14 counterpart each pin the reviewed source revision and inventory SHA, reserve **9 connections**, **10 external users**, and **100 external subscriptions**, and require distinct private state roots. These are bounded conservative diagnostic reservations; they are **not** proof of actual independent quota reservation.

## Read-only strict/diagnostic preflight

- **P1**: SQLite, selected sealed portfolio, current as-of eligible watchlist, inventory stability, old journal integrity and protected-path checks passed; selected census was 3. Configuration reported candidate 3 sockets / 3 users / 12 subscriptions. `subscription_budget=BLOCKED(STREAM_CONNECTION_BUDGET_EXCEEDED)`. `safe_to_start=false`.
- **P14**: Same structural checks passed, but its 5-member selected watchlist reported `PUBLIC_TRADE_WALLET_PROPFIRM_EXCLUDED`; 5 users / candidate 3 sockets / 17 subscriptions were *capacity estimates only*. Budget also blocked. `safe_to_start=false`.
- Separate original historical-portfolio audits: **all 3 P1 and 5 P14 alias bindings were first evidenced after the original frozen selection timestamp**. The original historical as-of portfolio identities remain `BLOCKED_POST_SEAL_BINDING` and must not be silently backdated. A valid *current* as-of P1 watchlist can support **new read-only observations only**, not historical replay, follower PnL or signing retroactively.
- Both preflight invocations exited 2; the candidate state directories were **not created**. No additional market/account WebSocket was opened, and no broker, demo, registry or financial journal mutation was performed.

## Disposition and safe continuation

1. **P0 engineering:** Correct the diagnostic `signed_selection` result so it is contingent on requested sealed-portfolio verification. Include original frozen PIT audit status in the content-addressed prospective observer manifest, explicitly marked new-observation-only. Verify with focused/full tests, no historical/backdated promotion.
2. **P0 live blocker:** To run P1 on this IP concurrently, independently arrange **at least three distinct user slots**, plus all discovered child-account slots and adequate socket/rate headroom. A separately reviewed reversible source-ABC configuration (smaller window, stronger socket pooling) or independent egress host is possible; neither was deployed. Preserve current source-ABC operation and data until an independently safe change is accepted.
3. **P0 genuine canary (#141):** Once resource reservations and eligible identity scope are verified, install an isolated private read-only observer+watchdog with pinned release and measured quote/source freshness, real baseline/new-event checks, restart/rollback, resource metrics and independent reconciliation. Missing real wallet events must remain UNKNOWN.
4. **P1 public cutover (#142):** Do not mutate the active public observer until the selected-scope canary, operator authorization, pinned release/reader compatibility and rollback checks actually pass. A 72-hour soak can be optional post-cutover evidence; it is not the only admission condition.

This record leaves #135, #141 and #142 **OPEN**. Source NAV, unrelated regime signatures, fabricated alpha, and mandatory elapsed 72 hours are not universal OBSERVE gates. Selected identity, provider quotas, provenance, and financial order authorization remain strict.
