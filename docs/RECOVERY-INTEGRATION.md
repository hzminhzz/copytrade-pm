# PR17 recovery: E0/E4 integration and source operations

## Authority and lineage

Recovery starts from remote main `d3e0ce916c2f0b64ad36593f55b261607ec0cbdd`.
The dirty primary checkout, its six local commits, and the independent Portfolio B
worktree are preserved. This integration selects complementary modules, rather than
merging the historical research branches wholesale.

| Source | Reused here | Deliberately retained on original branch |
| --- | --- | --- |
| PR16, `ee25379c7f5e473dcc33c6c1c808624bb886bf0c` | Whole-wallet E0 intent, A/B/C rosters, readiness gates and tests | WaveC and other local-main dependencies; historical replay results |
| PR15, `6f4138d7c649fda445b24d7974abd9942e607475` | Public read-only source capture, historical ledger acquisition, reconciliation diagnostics and tests | PM36/Portfolio C research runners and their inherited financial-engine versions |
| PR7, `f931376ac2882a7e365fdc7576519b81b5024bcc` | Historical provenance/reference only | Parallel PM36 simulator and historical artifacts; no automatic scientific promotion |
| Merged PR13, `8dd0c97971b41cd8d1c0e177050ed4cb059f30ec` | Existing PM03/PM04 account, risk, attribution, batching, replay and reconciliation authority | No replacement account or weakening of HALT |

The frozen 36-wallet cohort and `pm01_fill_only_replay_v2` contract remain unchanged.
Original research artifacts are never rewritten.

## Whole-wallet intent

`prepare_portfolio` requires the exact A/B/C roster and a complete, independently
attested source account book for every pod. Strings such as `"false"` and integers
cannot substitute for boolean attestations. Source state must be causal and no more
than 300 seconds old at the decision; receiving an old snapshot now does not refresh
its source clock.

One scale factor, pod capital / verified source equity, multiplies every signed
source position. Independently known leverage and margin remain explicit metadata;
unknown values remain unknown. DEX-prefixed instruments cannot collapse into default
markets. Source, risk-approved and executed books remain separate in fidelity metrics.

`pm_wallet_handoff.record_wallet_signal` feeds a prepared book into an existing
`ShadowRun`. It obtains budget references and revision counters from PM04 and emits
explicit zero targets for removed legs. It persists the complete source/scale lineage
with the event, supports identical replay, and rejects changed evidence under an
existing event ID. Unsupported hedges reject the whole event atomically. PM04 still
owns financial accounting, restrictions, loss budgets, pending exposure and execution.

An auditor must establish account/subaccount scope, equity, collateral, funding and
transfers before claiming that a raw collection is an eligible E0 book. The collector
does not supply those attestations merely because a WebSocket was healthy.

## Bounded source capture

The installed `source` extra pins `websockets==15.0.1` in `uv.lock`.
The v2 stream captures first application receipt before parsing or storage, saves
native leverage/margin fields, binds discovery bytes and clocks, and preserves
snapshot/backfill flags. Files are private and created exclusively. Existing evidence
is never migrated in place.

Hyperliquid's [current provider limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)
state a maximum of ten unique users across user-specific subscriptions per IP.
Subaccounts are separate users. Sharding connections does not increase this allowance.
The [subscription contract](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions)
also distinguishes initial snapshots from streaming updates.

The nine frozen masters currently discover 24 accounts in total: A=10, B=3, C=11.
One observer visits A, B, then two C windows, closing each window before starting the
next. No window exceeds ten unique accounts. A shared process lock prevents competing
instances of these collectors. The service's 60-second windows and two-second cooldowns
are deliberate sampling; every excluded account and inter-session gap is explicit.
Other software on the same public IP also consumes the provider's shared limits.

This is durable **bounded prospective observation**, not continuous full-book evidence.
Higher authorized provider capacity or another independently verified observation
interface is required before continuous coverage can be asserted. No network rotation,
proxy-based limit evasion, trading credentials or order route is used.

## Independent audit and readiness

`copytrade-pm-source-audit --store PATH --portfolio A|B|C` independently checks:

- Raw frame hashes, safe filenames, private permissions and receipt bounds.
- Source clocks, native market namespace and all-DEX catalog parity.
- Raw subaccount census identity, request/receipt clocks and hashes.
- Subscription acknowledgments and reported snapshots against actual frames.
- Each window's observed and unobserved accounts, plus inter-session gaps.

Missing, malformed, interrupted, over-limit or fabricated reports cannot pass.
Historical v1 captures remain available but cannot pass the stronger v2 contract.
The audit distinguishes a healthy recent completed window, recent coverage of the
discovered accounts, and continuity. An in-progress generation is not a completed
evidence artifact. Every scientific and trading authorization flag remains false.

Historical funding/collateral pagination is separately bounded and rate paced.
A full final-timestamp page does not establish exhaustion; tied events remain
unproven. Retrospective receipt times never become historical follower knowledge.

## Durable service and rollback

The tracked unit is `ops/systemd/copytrade-source-abc.service`. Its release directory
must be a detached, locked worktree at a verified recovery commit, with dependencies
installed using `uv sync --frozen --group dev --extra source`. The unit executes that
environment directly, rather than resolving packages on every restart.

Install with `systemctl --user link ABSOLUTE_RELEASE/ops/systemd/copytrade-source-abc.service`,
then `daemon-reload`. Stop and disable the legacy
`copytrade-e4-source-capture.service` before enabling the replacement, so the old
eleven-account observer cannot overlap the new windows. Retain its release and all
old evidence. Use `enable --now copytrade-source-abc.service`.

Verify enablement, active PID, restart count, journal outcomes, directory permissions,
all three portfolio audits and a controlled restart. A restart must create a new
generation and preserve the interruption/gap. If the replacement fails, stop it,
retain the evidence, and diagnose. Do not resume the over-limit legacy stream as an
automatic rollback; the safe rollback is stopped collection plus preserved artifacts.

## Verification at integration

Before release, the core and market-enabled suites each passed 363 tests; Ruff lint,
Ruff format, build and diff checks passed. The regression suite includes boolean
attestations, stale source/fresh receipt, decimal inputs, namespace collisions, zero
duplicate positions, missing/forged capture reports, tampered raw/census/receipt data,
permissions, symlinks, removed hedges, full-book replay and final-page saturation.

A bounded A smoke capture independently verified 115 frames across 10 accounts:
`41ad645754a884390b6847952bd196ac2da79ce9271b1de1c83cae0c18da775d`.
A B smoke captured all three accounts with no provider errors:
`991fb117480c1680f2d0870e2269040512a1ec5ab410fcd6f72f3a6739cebe77`.
These pre-rollout smoke results do not prove continuous or economic qualification.

The PM04 comparison replay reproduced
`f17d3048875b57b6e99ce452cd1ce3f54200c548247d74d36feed8291555bb42`
twice before integration. PR13's previous independent review applies to its original
offline acceptance scope. A new external judge is unavailable (`JUDGE_UNAVAILABLE`);
this document does not invent an independent verdict.

Status remains: IMPLEMENTED and ENGINEERING VERIFIED as tested; zero scientifically
qualified wallets, no broker authorization, no live deployment.
