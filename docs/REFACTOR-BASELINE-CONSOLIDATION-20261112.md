# Three-repository refactor baseline consolidation — execution plan

**As of:** 2026-11-12 UTC. **Scope:** `hzminhzz/copytrade-pm`, `hzminhzz/prop-production`, and `hzminhzz/trading-connector`; read-only VPS deployment inventory. **Status:** PLAN / PARTIAL PRESERVATION COMPLETE; not a refactor approval or a protected release.

## Objective and decision rule

Create one independently reproducible, source- and contract-pinned baseline for major architectural review. A clean *isolated* review checkout is sufficient; do **not** require the long-lived primary development directories or historical archives to be clean. A source commit, a GitHub merge, a passing CI suite, and a running deployed process are different assertions.

**Allow architecture review now.** Allow large refactor implementation **only after** gates G0–G5 pass for the chosen triple and its scope. Missing scientific follower P&L, prospective trading qualification, or brokerage permission are **not** blockers for read-only architectural review, but must never be silently promoted.

## Observed initial state (revalidate before actions)

| Repository | GitHub baseline ref (observed) | Primary VPS checkout | Open PRs | Notes |
| --- | --- | --- | ---: | --- |
| copytrade-pm | `main@1c4ac38e76dc7ed31e3421273269750b2f03e086` | `main@6c07cc6d36099135881be27a072c426a52a24f24` | 19 | Primary checkout behind and dirty; CWSA #333 merged, Reservoir #332 remains open |
| prop-production | `feat/account-guardian-program@22861edd5e42bed4e5bf8eb286423928afdcf937` (GitHub default) | same branch `00073496e0a3e4dc59b8d1cac4d3533c37c275ce` | 0 | Primary checkout clean but behind |
| trading-connector | `main@1a9cc6b39e78dc7745e3b5675df8abc838a9bd9a` | `main@5f7664b51988e9f48b3ff3a07876a136c2d97de8` | 0 | Primary checkout behind with mixed Bybit/provider drafts |

A prior exhaustive worktree scan found **200 registered worktrees** (158/23/19), **20 dirty** (16/1/3) and **one inaccessible** `/tmp/ctpm-fix`. The old copytrade-pm primary checkout had approximately 2,242 untracked files, predominantly `.agents/` and other local tool assets. Do not run `git clean`, `git reset --hard`, `git stash --all`, `git worktree prune` or an indiscriminate `git add -A`.

**Actual protected deployed revision:** `/opt/prop-production/current -> /opt/prop-production/releases/22861edd5e42bed4e5bf8eb286423928afdcf937` (Guardian/Planner/broker SHADOW), with installed `compatibility.json` pinning `copytrade-pm@9fa86ed32f8679f8ec5487e5cbfa2ef8e37bce10` and `trading-connector@ea95f9bf9661bcda41685d6ba939aa349628f8f5`. These pins are intentional runtime dependencies, **not** the proposed latest-source comparison triple. CWSA Chapter 2 observation services run from `copytrade-pm@26554dba965def37b1b1932bbbfb4bd7bcdd7eb3`; the Ops Control Center serves a separately pinned historical tree.

### Already preserved in this mission

- Original live Ops Control Center source differences at deployed `49731332ea24803a7141a48d07e74c3ee490ca30` were copied **byte-for-byte** into isolated Git commit `aeaed40d0d894d3be38445db13d30bb2459a1fa4`, without modifying the deployed checkout or restarting the service.
- Follow-up isolated fix `375a3361bbd3b1e4ae3ee314458bb5832860c1a0`: no invented pod counts; no cross-registry historical tracking injection; close SQLite read-only connections. Published branch: `preserve/ops-control-center-runtime-20261112`.
- That branch's pre-push CI passed **1,795 core / 48 skipped**, **1,963 market / 19 skipped**, Ruff and builds. Frontend TypeScript/Vite build passed and targeted server tests passed **4/4**. The **running service has not been upgraded to the fixed branch**; its advertised revision is still not the actual modified source tree. Never conflate the preserved original snapshot commit with a verified repaired live deployment.
- CWSA PR #333 merged as `1c4ac38e76dc7ed31e3421273269750b2f03e086` during this plan's preparation. It is engineering code on GitHub main, **not** an installed financial paper release. Reservoir PR #332 remains open and separately owned. Do not duplicate that work or silently force-push/rebase its branch.
- The canonical wallet-store package, migration/inspection scripts, documentation and synthetic golden fixtures were preserved on `preserve/canonical-wallet-store-20261112`: original isolated commit `efe2fae9ab7e659a48273ba9555014a320f1cba5`, optional market-import fix `b71c99e81d92f82abdae1fd8e2696f5b9fcc8f98`. Full exact-commit CI passed (core **1,910 passed / 49 skipped**, market **2,085 passed / 20 skipped**, Ruff, frontend build and wheel/sdist). It is research source preservation, not canonical-store ingest or paper admission.

## Dependency-aware phases

### G0 — Freeze and prove the starting evidence (P0)

1. Refresh `git ls-remote` and GitHub PR details; record full 40-character refs, merge-bases, dirty/untracked paths, pending pushes, branch ownership, and source timestamps in a **private redacted** baseline manifest. Pin the GitHub API response timestamp.
2. Identify all active user/system service PIDs, `/proc/PID/exe`, `/proc/PID/cwd`, systemd unit file hashes, release symlinks, immutable installed source/lockfile hashes and compatibility versions. Do not assume the symlink names what an already-running process executed.
3. Record worktree inventory including `/tmp/ctpm-fix`, disk headroom and excluded/private data roots. Do not delete or prune to make the inventory appear clean.
4. Create one clean isolated checkout per repository at the three **chosen** GitHub SHAs. Verify `HEAD`, branch/detached state, `git status --porcelain` empty, and that the exact GitHub commit exists. Do not `pull` into the dirty primary checkouts.

**Gate:** a versioned, content-hashed manifest describes **both** source review triple and protected runtime triple, with checked independent clean worktrees. Re-run if any upstream or active PR SHA changes.

### G1 — Preserve and classify unfinished work (P0)

1. Inventory dirty paths across all 200 registered worktrees and the installed Ops checkout. Classify each cluster as `ALREADY_COMMITTED`, `VERIFIED_READY_TO_COMMIT`, `ACTIVE_WIP`, `GENERATED_OR_VENDOR`, `SENSITIVE_EXCLUDE`, or `SUPERSEDED`. Record original path, owner, test evidence, base SHA, and intended review action. A registered worktree is not inherently stale.
2. Check whether untracked work is already represented by open #332, merged #333, the wallet-store preservation branch, or another GitHub branch **before** copying or committing it. Remaining candidates include the root's Reservoir docs/backtests, untracked Site source, and the connector's Bybit/Vanta/Vest/MFP drafts. Neither optional provider code nor agent-generated assets are automatic baseline content.
3. Commit only **coherent completed clusters**, after specific tests and checks, in *independent* topic/preservation branches. Keep the original dirty checkout unchanged. For a deployed dirty checkout, first preserve exact bytes as a separate historical commit, then fix/verify on a descendant; do not edit active release files in place. Push commits using the repository's normal local gate.
4. Leave active in-progress or unverified work owned by other sessions intact; preserve its SHA/path inventory rather than manufacturing a `DONE` commit. Exclude generated caches, private Parquet, raw wallet addresses/secrets, credentials and local skill/vendor directories.

**Gate:** each dirty path has an explicit disposition and surviving location; every `VERIFIED_READY_TO_COMMIT` cluster has a Git SHA and passing relevant checks; no file loss and no runtime mutation.

### G2 — Triage open copytrade-pm PRs (P1; after G0/G1)

Recheck the list before triage (19 open after #333 merged). Required disposition for **every** PR: `MERGE_CANDIDATE`, `KEEP_ACTIVE`, `SUPERSEDED_CLOSE_CANDIDATE`, `ARCHIVE_HISTORICAL`, or `BLOCKED`, with exact base/head/merge-base, replacement commit if applicable, owner, test status, and contract/deployment consequence.

| PRs | Initial triage queue, not a preapproved merge/close |
| --- | --- |
| #332 | `KEEP_ACTIVE`: six-portfolio Reservoir acquisition. CWSA acceptance gates #333 already merged, **not deployed**; do not equate a merge or CI with admitted paper finance. |
| #301 | `REVIEW_MERGE_CANDIDATE`: Track B original-evidence/Prefect integration; compare to current main and installed evidence. |
| #291 | `CHECK_SUPERSEDED`: frozen-k follow-up; compare with merged Track C contracts and pending status. |
| #289 | `CHECK_ALREADY_DEPLOYED`: Site registry sync; determine if source is in main and if actual installed release is tracked. |
| #210 | `REVIEW_MERGE_CANDIDATE`: AGENTS documentation condensation; must preserve latest safety gates. |
| #172 | `REVIEW_MERGE_CANDIDATE`: pre-fetch provider budget/exclusion gate; may have been integrated elsewhere. |
| #194, #179 | `CHECK_SUPERSEDED`: stacked pre-CWSA CCXT quote/single-shot source work on non-main bases. Preserve historical semantics. |
| #196 | `KEEP_HISTORICAL_OR_ARCHIVE`: Vike estimated-minute draft; not the active 5m source release. |
| #122, #120, #107, #98, #74, #26, #25, #24, #15, #7 | `ARCHIVE_HISTORICAL_CANDIDATE`: older research/draft branches; verify unique evidence and dependent branches before closing. |

A PR can be excluded from the refactor baseline without closing it. Merge only reviewed, target-relevant changes whose latest head passes exact-SHA gates. Never mass-merge legacy drafts or close active tickets merely to reduce the count.

**Gate:** each PR has a durable linked disposition and inclusion/exclusion rationale; no unresolved refactor-critical patch set is silently omitted.

### G3 — Reconcile mutable deployed dashboard (P1; after G1)

1. Retain original deployment commit `49731332...`, exact deployed modified-source snapshot `aeaed40...`, and tested fixed candidate `375a336...` as **three different identities**.
2. Audit the source diff and deployed HTTP read-only response; confirm the Site's identity/freshness fields, CWSA paper `BLOCKED_EVIDENCE` semantics, stable 404/403 behavior, null/unverified risk fields, and no connector, Guardian or hidden broker route.
3. Rebase/cherry-pick **reviewed** changes onto a current main-derived branch if required; resolve conflicts by targeted tests. Publish clean source and reproducible frontend build with lockfile, typechecks, Python tests, browser checks and hash attestations.
4. **Separate authorized maintenance operation**: stage new immutable release directory, backup unit/config/symlink, test isolated canary, switch only `copytrade-ops-center.service`, independently verify PID/source SHA/runtime body and named rollback. This plan and snapshot commits alone are not deployment authorization.

**Gate:** live source bytes, built assets, unit and process identity agree on one published immutable revision. Until then, mark dashboard runtime provenance `UNRECONCILED`.

### G4 — Cross-repository compatibility (P1; after G0/G2)

1. Verify the protected installed `prop-production@22861edd...` manifest and its **actual** pinned `copytrade-pm@9fa86ed...` / `trading-connector@ea95f9...` source and schema compatibility. Do **not** change protected services.
2. Separately check candidate review triple `copytrade-pm@1c4ac38e...`, `prop-production@22861edd...`, `trading-connector@1a9cc6b...` (or replacement reviewed SHAs). Validate `portfolio_release_v1/v2`, `cwsa_checkpoint_packet_v3`, `copy_mandate_v1`, account/market evidence, immutable source-wire version, and signed release semantics with the real cross-tree test interfaces.
3. Any incompatibility creates an explicit `BLOCKED_CONTRACT` result with owning repo and exact diff; do not silently repin `compatibility.json` or broaden provider permissions.

**Gate:** protected runtime pins remain independently verified, and chosen refactor triple passes an explicit cross-tree compatibility matrix; both are named separately.

### G5 — Exact-SHA local CI and review freeze (P1; after G0–G4)

1. From *clean, detached or dedicated* review worktrees run the pinned native local suites: `copytrade-pm: bash scripts/ci.sh all` (including merged #333 requirements), `prop-production: bash scripts/verify-local.sh all`, and the connector's own relevant provider tests + Ruff/type/build.
2. Run cross-repository checkpoint/Guardian/connector tests and no-order-readonly smoke tests, including restart, HALT, stale evidence, reversal, duplicate/unknown order, historical journal compatibility and source/market causality. Do not need real broker credentials.
3. Publish a content-hashed **private** verification receipt per SHA: exact commands, Python and lockfile versions, test/skip counts, failures, exit codes, hash of logs, and independently readable acceptance report.
4. Recheck GitHub heads, PR dispositions, `git status --porcelain`, deployed process identities, disk/WAL and no unintended service/release changes before declaring freeze.

**Gate:** all relevant local CI and cross-tree tests pass at the committed source-review SHAs; no important unclassified dirty diff or contract drift; protected services remain operating unchanged.

## Completion / stop rule

`REFACTOR_REVIEW_READY` requires G0 and a stable scope-labelled read-only manifest. `REFACTOR_IMPLEMENTATION_READY` requires G0–G5, documented PR inclusion/exclusion, published preserved commits, replayable verification receipts, and immutable deployed-code provenance if a live dashboard is part of the refactor target.

Fail closed on ambiguous authorship, dirty protected release, unproven companion upgrade, missing audit logs or conflicting active sessions. Do not block the review on scientifically qualified alpha, funded challenges or a paper release that is legitimately `BLOCKED_EVIDENCE`.

**Explicit exclusions:** no trading authorization, broker mutation, live Guardian/Planner upgrade, CWSA financial epoch activation, portfolio reselection, private raw data publication, wholesale worktree deletion, or old journal rewrites.
