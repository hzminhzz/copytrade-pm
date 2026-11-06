# Observer resource remediation checkpoint — 2026-11-06

Status: **ENGINEERING DIAGNOSTICS ONLY**. This does **not** qualify the 157-market
portfolio shadow (#141) or authorize the public-observer cutover (#142).

## Current production constraints (read-only audit)

The VPS public observer still uses its original pinned release; tracker,
source-ABC, ensemble and all existing financial services were left unchanged.
The canonical SQLite is structurally valid: `PRAGMA integrity_check=ok`,
`PRAGMA foreign_key_check` empty, inventory generation
`b2e5ea14fc3f1b71778bc78f4a568b0e7ee711802e2ab3ebfd72ef282cbdb855`.

The most recent research selection source
`a899f0f6a4331c246307189f3ab75d87e1a515b84a2e926073ce33ff994ce9eb`
still has **no accepted Ed25519 proof**. The new reader now truthfully emits
`database_integrity=VERIFIED` and
`research_selection_integrity=BLOCKED_MISSING_EXTERNAL_PROOF`, exiting 2.
`portfolio --current` remains strict and rejects the unsigned source.
The continuous observer still rejects the missing proof; no waiver or
fabricated signature was introduced.

P1 has three current address matches, but all three alias bindings first
became known **after** its original selection seal. P14's equivalent PIT
identity audit is also `BLOCKED`, and one of its five members remains
excluded by existing prop-firm policy. Neither original seal was rewritten.
A fresh, separately evidenced prospective watchlist is required before
qualification of newly captured wallet signals.

## Actual native shared-IP budget

Official Hyperliquid documentation specifies 10 concurrent WebSockets,
10 unique subscribed users, 1000 subscriptions, and 30 new connections/minute
**per IP**. Provider documentation does not establish an independent
per-socket unique-user reset.

The existing source-ABC receiver has default per-window user limit **10**
and **15 subscriptions per physical socket**, with five subscription
channels per account. Its stored active A-window evidence reports **10 unique
subscribed user accounts across four WebSockets**; B and C windows vary.
Across the most recently inspected A/B/C session reports there are 24 distinct
hashed subject identities, and the prospective P1/P14 source identities
have **zero overlap** with those observed source-ABC subject hashes.

Consequently, adding three P1 users when source-ABC is on the 10-user A
window would require **13 unique user subscriptions**. Even perfect socket
consolidation would NOT make that configuration safe. A complete concurrent
P1/P14 full-market candidate remains **BLOCKED**.

The conservative 157-market candidate plan needs five additional physical
sockets at existing CCXT/native sharding limits and 476 subscriptions for
five parent accounts **before** discovered children/hedges. A safe future
allocation must account for account-window rotation, held children, current
protected consumers, rate headroom, and measured peak counts; it must not
infer 157-market coverage from this report.

## Implemented configuration — not deployed

The existing `pm_e4_stream` and `pm_source_rotation` owners now accept
optional resource settings, with **old defaults unchanged**:

- `--max-accounts-per-window 7`: seven or fewer unique accounts per rotating
  source-ABC observation window; remaining accounts rotate into later windows
  with honest gap reports, not silent disappearance.
- `--max-subscriptions-per-connection 64`: up to 64 independent subscriptions
  per socket for that bounded source-ABC receiver. Seven accounts times five
  account channels = 35 subscriptions; arithmetic fits one socket.
- All values are validated, fail closed on invalid limits and are written to
  prospective generation reports. This is **configuration availability**,
  not evidence that the target user-account stream has been live-benchmarked
  at 35 subscriptions or that the shared IP can admit a new portfolio.
- No existing `copytrade-source-abc.service` configuration/release, PID,
  journal, or subscription was changed. A separately reviewed source-ABC
  deployment/canary and rollback are prerequisites to using these knobs.

A P1-only new observer at three unique users plus a source-ABC A-window of
seven would consume the provider's **entire ten-user allowance** before
other wallet-specific subscriptions. A positive budget requires explicit
reserve headroom or another independent egress host. P14 cannot be substituted
without first resolving excluded membership and fresh provenance.

## Two actual public-only Hyperliquid market canaries

These were **sequential, bounded, one-WebSocket, no-user, no-order** probes
using the exact pinned Propr 157-symbol market manifest and native `trades`
subscriptions. Each subscribed 50 distinct instruments on one socket.

| Measured item | Default perp subset | `xyz:` HIP-3 subset |
| --- | ---: | ---: |
| WebSocket subscriptions requested | 50 | 50 |
| Subscription ACKs | 50 | 50 |
| Markets receiving live trade frames | 50 | 50 |
| Native trade frames observed | 1,893 | 2,437 |
| Elapsed wall-clock seconds | 24.309 | 24.247 |
| Provider error frames | 0 | 0 |
| New user-specific subscriptions | 0 | 0 |
| Remote order mutations | 0 | 0 |
| Established provider-TLS process sockets before dial | 5 | 8 |

The source artifacts are owner-private ignored local JSON summaries under
`dist/public_market_50_probe_20261106.json` and
`dist/public_market_50_xyz_probe_20261106.json` in the isolated
worktree. SHA-256 of the two JSON summaries: default-perp
`3ebfe8862d3236120d0f5575cab86fcc0f89e4d41ec0c5078decd6602d884fb0`;
HIP-3 `864ec4f9a76ddecc1f9d91e2c342f86014ff07a0b90acf99680a68420d704210`.
The bounded probes used only native `subscribe` and `ping` messages.
These are finite socket/ACK/frame observations, not persistent tapes,
quote freshness, executable prices, portfolio matches or 72-hour coverage.
The TLS counts are **upper-bound process observations**, not proof that all
those TLS sockets were upgraded to WebSockets.

## Qualification status and safe next action

1. The newly correct registry doctor now distinguishes **valid SQLite**
   from **unsigned current research-selection provenance**. Strict observer
   preflight remains blocked. Do not import an unsigned source as approved.
2. An independently authenticated, versioned *prospective* portfolio
   selection must choose non-excluded wallets and establish first-known
   identities from its new effective timestamp. Older P1/P14 PIT cannot be
   rewritten. The existing 75 prop-firm exclusions remain binding.
3. The source-ABC socket grouping and user-window options are available in
   code but require provider account-stream canary, controlled independent
   deployment approval, headroom and rollback. The active source-ABC is
   unchanged; this report does not authorize a restart.
4. Then remeasure all shared-IP users/sockets and resource throughput on the
   full 157 required markets, including dynamically held hedges, and rerun the
   original **strict** read-only candidate preflight.
5. Start the independent real 72-hour shadow **only after those gates pass**.
   Cutover #142 remains separately gated on accepted 72h evidence, reader/journal
   compatibility and explicit authorization; no 72-hour passage is presumed.

## Commit-pinned local engineering acceptance

On the isolated candidate branch, the exact frozen dependency matrix passed:
**1,241 all-extras tests**, **1,122 core passed / 15 skipped**, and
**1,240 market passed / 1 skipped**. Ruff lint and formatting passed, native
capabilities validated **94** entries with zero errors, and the offline sdist
and wheel built successfully. The canonical documentation auditor checked
**13 files / 212 links / 0 broken links**, with dated legacy source SHA matched
despite stale age. The *live* native doctor returned
`database_integrity=VERIFIED`,
`research_selection_integrity=BLOCKED_MISSING_EXTERNAL_PROOF`,
exit code 2 as designed, and made no registry mutation.

**No 72-hour qualifying shadow hours accrued in this work. No actual observer,
source-ABC or broker service cutover was performed.** No source NAV requirement
was added to read-only capture or trading permission inferred.
