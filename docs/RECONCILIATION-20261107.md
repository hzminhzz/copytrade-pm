# Reconciliation record — 7 November 2026 (Asia/Ho_Chi_Minh)

This is a dated engineering disposition, not runtime or scientific authority.
Read the current GitHub PR state, private registry diagnostics and real deployment
metadata before claiming a current state. The containing Git commit identifies
this record; the application's compatibility manifest owns companion release pins.

## Canonical development branches

| Repository | Default branch at inspection | Starting remote commit |
| --- | --- | --- |
| copytrade-pm | main | 4a256ea5cf70b0de93a4369872935da9bd190c36 |
| trading-connector | main | d8a1905a07cab6103f2a7ce31bf7072fddb586ad |
| prop-production | feat/account-guardian-program | 1d7a530df06f2dad753f1615ff2c22af64879d41 |

All three GitHub repositories were public at inspection. Private source records,
wallet addresses, credentials, SQLite databases and account journals remain private.
GitHub Actions is optional; independently enforced protections still apply.

## All 22 initially open copytrade PRs

MERGE means accepted through the reconciliation integration and its named local
merge below. Verify the resulting target ancestry and PR link after publication.
Research branches remain open and preserved; their status is an explicit
research disposition, not a pending default-policy merge instruction.

| PR | Reviewed head | Disposition | Integration/replacement | Reason and scope |
| --- | --- | --- | --- | --- |
| [#7](https://github.com/hzminhzz/copytrade-pm/pull/7) | `f931376ac288` | RETAIN AS RESEARCH | f931376 | PM-36 retrospective study and three-pod replay; in-sample choice and first-known gaps remain. |
| [#15](https://github.com/hzminhzz/copytrade-pm/pull/15) | `6f4138d7c649` | RETAIN AS RESEARCH | 6f4138d | Explicit legacy whole-wallet proportional fidelity; not the new fixed-k default. |
| [#24](https://github.com/hzminhzz/copytrade-pm/pull/24) | `256d37a58a31` | RETAIN AS RESEARCH | 256d37a | Historical handbook/Gemini/Nansen evidence. Its old operational and universal NAV wording must not replace canonical guides. |
| [#25](https://github.com/hzminhzz/copytrade-pm/pull/25) | `dd426aca4f17` | RETAIN AS RESEARCH | dd426ac | HL94 retrospective replay and stress; preserve historical sizing and data assumptions. |
| [#26](https://github.com/hzminhzz/copytrade-pm/pull/26) | `986a233e68c1` | RETAIN AS RESEARCH | 986a233 | The read-only verified_paper_decisions projection is backported in this reconciliation for connector compatibility. Prospective capture/delta experiments remain isolated. |
| [#43](https://github.com/hzminhzz/copytrade-pm/pull/43) | `29dd3502e22e` | SUPERSEDED | existing main | Adoption plan has identical Git blob 7117f6ba1141e82fd4c484a532df4a5d9bf3bc5f; SQLite ownership is implemented. |
| [#74](https://github.com/hzminhzz/copytrade-pm/pull/74) | `995d2accae38` | RETAIN AS RESEARCH | 995d2ac | Phase6 recovery and reconciliation evidence; no automatic qualification. |
| [#98](https://github.com/hzminhzz/copytrade-pm/pull/98) | `3fd100991229` | RETAIN AS RESEARCH | 3fd1009 | Conditional native-minute decision report; preserve retrospective constraints. |
| [#107](https://github.com/hzminhzz/copytrade-pm/pull/107) | `4707df977b17` | RETAIN AS RESEARCH | 4707df9 | Five-pod prospective source observations; no qualified follower economics or worker admission. |
| [#112](https://github.com/hzminhzz/copytrade-pm/pull/112) | `bd6ae6ecf051` | SUPERSEDED | 8ba1047 / #115 | Native write implementation is included via #115. The separate empty CI-trigger head adds no behavior. |
| [#115](https://github.com/hzminhzz/copytrade-pm/pull/115) | `c493c0680ae3` | MERGE | 8ba1047 | Native lock, cohort and append-only exclusion controls; repaired complete archive membership/time verification. |
| [#119](https://github.com/hzminhzz/copytrade-pm/pull/119) | `6497e6972d61` | MERGE | 84a68c6 | Dated independent-science audit retained; current fixed-k policy explicitly supersedes universal NAV wording. |
| [#120](https://github.com/hzminhzz/copytrade-pm/pull/120) | `72710d3f0471` | RETAIN AS RESEARCH | 72710d3 | Bounded ML4T-66 research recovery; historical data completeness is not first-known follower evidence. |
| [#121](https://github.com/hzminhzz/copytrade-pm/pull/121) | `3abaa7a497b0` | MERGE | 1605f56 | Included through #126; staged standby does not authorize financial execution. |
| [#122](https://github.com/hzminhzz/copytrade-pm/pull/122) | `49f5dab06617` | RETAIN AS RESEARCH | 49f5dab | Barbell screens and forensic sizing evidence; dependent on #120, no financial promotion. |
| [#123](https://github.com/hzminhzz/copytrade-pm/pull/123) | `8787a7aedc19` | MERGE | 1605f56 | Included through #126; unsigned reseal preview is diagnostic only. |
| [#124](https://github.com/hzminhzz/copytrade-pm/pull/124) | `cb26e1ce7f19` | MERGE | 1605f56 / d51990c | Included through #126; kept future-source/quote censoring while integrating fixed-k. |
| [#125](https://github.com/hzminhzz/copytrade-pm/pull/125) | `c99c42f00cf2` | MERGE | 1605f56 | Included through #126; real admission cannot claim a synthetic fixture exemption. |
| [#126](https://github.com/hzminhzz/copytrade-pm/pull/126) | `c8b5ccc9d390` | MERGE | 1605f56 | P0 consolidation; preserved causal source/quote checks and protected standby boundary. |
| [#127](https://github.com/hzminhzz/copytrade-pm/pull/127) | `fcf79b8e4d80` | MERGE | c830ce8 | Signed SQLite handoff; reconciled fixed-k/no-NAV payloads and old signed legacy envelopes; corrected stage-reset MADE. |
| [#128](https://github.com/hzminhzz/copytrade-pm/pull/128) | `c0c701558c3d` | MERGE | fd35bf8 | Research-only Vike recovery; repaired payload parity, replayed gaps and archive-copy verification. |
| [#143](https://github.com/hzminhzz/copytrade-pm/pull/143) | `e0f7b6b0521f` | MERGE | d51990c | Signed fixed-k default; legacy NAV mode remains explicit. |

## Preservation and local-only work

Before integration, all 90 original worktrees (79 / 8 / 3) were checkpointed in
owner-only VPS storage. Verified Git bundles include every worktree HEAD;
restored mirrors checked those objects. Each worktree has its raw index,
staged/unstaged binary patches, status and a meaningful dirty/untracked evidence
archive. A SQLite online backup passed integrity and foreign-key checks.
No original dirty checkout was reset, stashed, cleaned or overwritten.

The private recovery index is under
`~/.local/share/copytrade/reconciliation/20261107-baseline`.
Its manifests identify exact recovery paths and archive hashes. Do not publish them.

| Local work | Disposition |
| --- | --- |
| copytrade primary checkout and dirty research worktrees | Preserved in place and checkpointed. Active or uncertain ownership prevents cleanup; new work uses the clean integration checkout. |
| Offline integration 4ca424a and synthetic integrations 64de083 / 1c92f776 | Preserved ancestry; native offline/forward implementations are already in current main. Retain historical test and doc snapshots. |
| Dynamic portfolio branch 7841562 | Behavior already in main; reconciliation replaces its fixture-prefix bypass and duplicate seal logic with the authoritative registry verifier. |
| Local documentation 85c336a / 67df7dc | Current canonical guides contain the relevant ownership/recovery behavior; preserve original dated commits. |
| PM-36/E123 and portfolio-B research branches | Preserve exploratory code, tests and private evidence. They do not change default financial behavior or establish alpha. |
| trading-connector 6175a94 and ad982e6 | Integrated durable rejection/idempotency boundaries, with actual installed ML4T protocol inspection and native tests. |
| Uncommitted Backed/cTrader/MatchTrader/MT5 provider work and other primary-checkout edits | Private checkpoint and original work retained. Separate unfinished provider scope; not silently promoted into the reviewed three-provider baseline. |
| Older deployed release checkouts | Retain while a service, rollback path or protected private artifact depends on them. A differing SHA alone is not obsolescence. |

## Repairs and remaining authority boundaries

Default new copying is signed `FIXED_K_NATIVE_QUANTITY`. Source mark converts
leader native quantity into notional; an independent follower quote determines
follower quantity. Only explicit `ALLOCATION_OVER_LIVE_NAV` requires leader NAV.
Follower equity, source/account scope, causal clocks, reconciliation, risk and
separate order permission remain mandatory.

Registry physical integrity and unsigned selection provenance are separate.
A metadata-reader release may report a verified database together with
`BLOCKED_MISSING_EXTERNAL_PROOF`; it must preserve that negative selection result,
false scientific qualification and false trading authorization. Frozen identities
are checked against independently pinned or signed sources. No historical seal,
membership or source receipt was rewritten to obtain a passing diagnostic.

The persistent observer cutover retains #135/#141/#142 evidence gates. Protected
P1/P14 standby definitions do not establish installed financial workers. The
separate Guardian services require their own release verification and root authority.
No broker-writing behavior is enabled by this reconciliation.

## Verification and navigation

Use [AGENTS](../AGENTS.md), [the handbook](INDEX.md),
[the registry workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md),
[registry release/rollback](WALLET-REGISTRY-RELEASE-RUNBOOK.md),
and [the continuous observer runbook](FORWARD-PAPER-CONTINUOUS-OBSERVER.md).
Exact command results belong to the consolidation PR and the application's
commit-bound `scripts/verify-local.sh all` receipt. Do not copy transient counts
into evergreen policy or treat unit tests as scientific or trading approval.
