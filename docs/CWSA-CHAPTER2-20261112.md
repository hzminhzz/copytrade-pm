# CWSA Chapter 2 — six-portfolio paper runtime and release contract

**Role:** CURRENT CHAPTER 2 OPERATING CONTRACT, with dated deployment locators to recheck. The original repair PR #331 merged as `26554dba965def37b1b1932bbbfb4bd7bcdd7eb3`; stage-gate engineering is present in the reviewed `1c4ac38e76dc7ed31e3421273269750b2f03e086` source. This page does not establish what is running now. Independently verify installed release, application-process identity, source and financial evidence. The [agent system plan](AGENT-SYSTEM-DESIGN.md) preserves this runbook as the stage owner; ANOS-05 introduces the independent process-to-release verifier in the [read-only operations owner](AGENT-NATIVE-OPERATIONS.md#runtime-and-observer-diagnostics); **ANOS-06 (#340) still owns Chapter 2 gate integration**. Until that work is separately merged and verified, the existing postdeploy gate's configured-SHA plus PID check is not independent application proof. Only an exact verified merged/installed revision, not this document, determines which check actually runs.

## Current research identities and existing service

The SQLite sealed registry, not this page, owns the selected membership and versions. Requested research portfolios: `A`, `B`, `C`, `Combo2`, `regime.macro/TriadA`, and `regime.macro/TriadChop`, together using 14 unique source wallet IDs.

- Source: `copytrade-cwsa-5m-source-chapter2.service` — independently owned, official native REST CWSA source authority.
- Paper supervisor: `copytrade-cwsa-5m-paper-chapter2.service` — independent virtual-paper journal owner, **no broker transport**.
- Existing unqualified paper root: `/home/quant/.local/share/copytrade/prospective/cwsa-5m-paper-chapter2-20261112`.
- Canonical source journal: `/home/quant/.local/share/copytrade/prospective/cwsa-5m-source-chapter2-20261112/paper-events.sqlite3`.
- Old V4 paper archive remains immutable and independently replayable. Never clear it to reset Chapter 2.

A six-portfolio SQLite seal is **not** a signed CWSA copy mandate. Source checkpoint collection can operate safely with `BLOCKED_EVIDENCE` financial admission. No modeled fills are claimed merely because journal objects and service processes exist.

## ANOS-09: scoped read-only blocker explanation

Use the native owner facade for one Chapter 2 portfolio, not a global readiness score:

```bash
copytrade-pm cwsa chapter2 explain --portfolio A --inspection metadata
copytrade-pm cwsa chapter2 explain --portfolio A --inspection evidence \\
  --registry-db /private/registry.sqlite \\
  --source-db /private/source/paper-events.sqlite3 \\
  --paper-root /private/paper-root
```

The default `metadata` mode reads only the registry doctor and the requested portfolio's version-2 SQLite seal. It does not open source, market, or PM03 finance journals, inspect systemd, probe Guardian, or dispatch actions. `evidence` mode explicitly requests one source-owner chain verification, one portfolio PM03 replay and optional independently verified L2 quotes and signed release/qualification. All original owner checks retain authority; this read-only explanation never replaces the Chapter 2 stage gate or authorizes financial activation.

The versioned `cwsa_chapter2_task_explanation_v1` output separates physical SQLite integrity, global research-selection provenance, requested seal, source OBSERVE status, signed paper release, independent L2, native modeled finance, protected Guardian risk and account authorization. An unrelated unsigned research priority may be BLOCKED even when the requested SQLite seal is verified. A current source checkpoint can be OBSERVE-ready while paper is evidence-blocked. Financial fields remain JSON `null` unless native PM03 replay has independently verified eligible modeled effects with the required paper-only inputs; an empty journal, fake zero economics, or running PID cannot fill them. Source checkpoint clocks, original heads, portfolio seal SHA and journal cursor/head remain attached to their producing owners. Guardian risk/authorization are UNKNOWN here, and all responses preserve `order_route=NONE`, `trading_authorized=false` and `scientifically_qualified=false`.

Each result names a task-specific reason, affected portfolio and next *catalogued* read-only operation with effect class. It does not execute the recommendation. Inspect metadata before requesting broader native evidence. The output is a reusable owner projection for later CLI/Site consumption; the Site must not recalculate finance or permission.

## Durable source-wave projection

The paper supervisor reads the canonical source database read-only. Each portfolio stores its own `chapter2_wave_receipts` chain, including original outcome IDs, source clocks, wave membership, evidence hashes and missing-wallet disposition.

- A complete portfolio wave may close independently of unrelated portfolios.
- An incomplete wave waits until the source's **original pinned publication grace**; then it closes with a missing-source record, never a fabricated flat position.
- Same-checkpoint late results cannot retroactively replace a closed wave.
- A crash after a durable receipt but before a JSON status publication is recovered from the ledger; status files are replaceable projections.
- The source journal is never imported as an alternative state authority. The signed finance adapter verifies/mirrors the original source chain and original native evidence into the existing PM03 `PaperJournal` before consuming it.

`cwsa_chapter2_status.json` and each `<portfolio>/status.json` are read-only operator projections, not financial stores.

## Optional signed **paper-only** finance release

This is **not enabled** merely because the six registry seals exist. The current historical registry contracts identify research or virtual-paper selection, including non-executable Triad seals. They do not supply approved fixed-k values for CWSA.

A qualified paper release requires all of the following, separately provided and verified before activation:

1. One **new empty paper epoch root** and unique `--run-label`, with its own six independent PM03 journals. Never upgrade the provisional unsigned paper root in place.
2. Externally authorized Ed25519-signed Copy Mandates for every selected member of each admitted portfolio, with immutable generation, native market scope, frozen decimal k, policy epoch, source account and scope generation, and future activation window.
3. A SHA-256-pinned `cwsa_chapter2_paper_release_v1` bundle containing the exact six-portfolio seal hashes, independently defined risk policy and market catalog, and the signed mandate envelopes. Approval is **per portfolio**: partial portfolio membership is never admitted.
4. A separately provisioned trusted release **public** key (never infer trust from a signature's self-supplied key), and an independently verified, existing read-only L2 quote journal. Vike bars and midpoints cannot be presented as executable follower L2.
5. Risk limits, costs, source proofs, first non-actionable baseline, clocks and all PM03 one-shot protection verified. This adapter cannot sign mandates, discover trading keys, submit orders, or authorize a broker.

CLI:

```bash
python -m copytrade_pm.pm_cwsa_six_paper \
  --state-root /private/new-epoch-root \
  --source-db /private/canonical-source/paper-events.sqlite3 \
  --registry-db /private/registry/wallet_registry.sqlite \
  --run-label cwsa_chapter2_paper_epoch2 \
  --approved-paper-bundle /private/approved-paper-release.json \
  --approved-paper-sha256 '<independently-verified-sha256>' \
  --trusted-paper-authority-public '<independently-trusted-public-key-hex>' \
  --quote-db /private/verified-l2/paper-events.sqlite3 \
  --poll-seconds 5
```

No default signer, default k, synthetic receipt or automatic research-to-production promotion exists. Starting a new epoch does not make the economic qualification calendar retroactive. An approved paper consumer records immutable modeled P&L and costs; it does not create a protected execution permit.

## Verification and rollback

For targeted tests from the exact source checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_cwsa_chapter2_ingestion.py tests/test_cwsa_chapter2_release.py tests/test_cwsa_chapter2_mirror.py tests/test_cwsa_six_paper.py tests/test_checkpoint_source.py tests/test_checkpoint_journal.py tests/test_checkpoint_paper.py tests/test_checkpoint_campaign.py tests/test_copy_mandates.py
.venv/bin/ruff check src/copytrade_pm/pm_cwsa_*.py tests/test_cwsa_*.py
.venv/bin/ruff format --check src/copytrade_pm/pm_cwsa_*.py tests/test_cwsa_*.py
```

Before any deployment: record service PIDs/sha, journal heads, source cadence, WAL/disk budget, all old service consumers, provider limits, and a pinned rollback release. Test isolated `--once`, restart, same-checkpoint late arrival and original source replay; verify service after restart. Do not change protected Guardian/connector/broker services or the old immutable V4 archive.

The current operator frontend source is `/home/quant/dev/copytrade-pm/dashboard/`; new Chapter 2 evidence should be projected through its existing privacy-safe read-only data flow. **Do not confuse a local JSON status file or a running legacy Grafana process with verified dashboard deployment.**

**Qualification:** A functioning source collector, clean paper journal and passing synthetic tests are engineering evidence. Count prospective economic holdout only after legitimate signed paper admissions, complete source coverage, real independent quotes, paper-financial receipts and risk/cost observations. Tickets #319/#320/#326/#327 retain their original required evidence and acceptance criteria.


## Chapter 2 retrospective — mandatory stage separation

**Owner:** this page. For actual operator requests, invoke the existing `copytrade-pm` CLI, not a second service or paper engine. A successful CI run is only engineering verification; a live process is only service liveness. Neither proves admitted finance or scientific qualification.

### Deterministic acceptance

The verifier emits `cwsa_chapter2_gate_verdict_v1` JSON with an explicit top-level `verdict`: `PASS` (exit 0), `BLOCKED_EVIDENCE` (exit 2), or `FAIL` (exit 1). FAIL dominates missing-evidence blockers, which dominate PASS. Always retain the entire returned check array and exact candidate SHA.

From the checked-out release, use:

```bash
copytrade-pm cwsa chapter2 verify --stage premerge --receipt /private/sha-bound-local-ci.json
copytrade-pm cwsa chapter2 verify --stage predeploy --receipt /private/sha-bound-local-ci.json \
  --expected-sha EXACT_CANDIDATE_SHA --rollback-sha EXACT_OLD_RELEASE_SHA \
  --rollback-path /private/actual-pinned-rollback-release \
  --paper-root /private/new-empty-financial-epoch \
  --quote-db /private/verified-independent-l2/paper-events.sqlite3 \
  --qualification /private/independently-signed-k-qualification.json \
  --research-public-key INDEPENDENT_RESEARCH_KEY_HEX \
  --approved-paper-bundle /private/paper-only-release.json \
  --approved-paper-sha256 EXACT_APPROVAL_SHA256 \
  --trusted-paper-public-key INDEPENDENT_PAPER_TRUST_ROOT_HEX
copytrade-pm cwsa chapter2 verify --stage postdeploy \
  --expected-sha EXACT_VERIFIER_RELEASE_SHA \
  --expected-source-sha EXACT_SOURCE_RELEASE_SHA \
  --expected-paper-sha EXACT_PAPER_RELEASE_SHA \
  --dashboard-url https://PRIVATE_SITE/chapter2/evidence.json \
  --dashboard-revision EXACT_DASHBOARD_RELEASE_SHA
```

Postdeploy gathers systemd PID/configured executable checkout, SQLite-backed source policy and roster, all six read-only PM03 replayed journals, immutable receipt chains, resource headroom, financial consumer progress and deployed authenticated dashboard lineage. **ANOS T05/T06 process evidence contract:** the postdeploy stage consumes `pm_runtime_readonly.verify_unit_release` for each allowlisted Chapter 2 user unit and separately observes the paper worker's actual OS process with `observe_unit_liveness`; configured Git SHA or a systemd PID alone never verifies its running application. A proven `VERIFIED` launch binds configured, installed and observed process identity at its inspection time, while `UNKNOWN` (unreadable OS, mutable release, race or missing expected revision) maps to gate `BLOCKED_EVIDENCE`; `NOT_RUNNING` and `MISMATCH` map to `FAIL`. Paper process liveness is a separate check: independently observed running process does not imply its release is verified, and an unproved release does not mean `PAPER_SERVICE_NOT_RUNNING`. Missing liveness blocks finance rather than fabricating a stopped worker; a proven stopped/incorrect worker or due changed-event consumer failure remains FAIL. `financially_active` requires the complete postdeploy verdict PASS, not merely a cursor or one successful finance check. All evidence remains bounded to the original process snapshot, not loaded Python bytes, finance, or authorization. An active service under an unpinned mutable worktree must **not** be treated as an immutable release. A healthy observer with zero signed mandates remains blocked; a signed financial consumer that fails to process an eligible due change is FAIL. No eligible trades means no verified modeled financial effect.

The predeploy gate is a *financial-epoch* acceptance check. It must reject retroactive use of the existing provisional observation root. Nonfinancial source observation may stay running under its separately reviewed reversible observer deployment; that does **not** make the financial predeploy gate PASS. Do not fill absent qualified k or L2 evidence with illustrative estimates.

### Frozen k and paper mandate authority

The existing Track C KResearchInput / KReleaseCandidate and native Copy Mandate/PM03 abstractions are the owners. The research-attestation verifier accepts only independently Ed25519-signed `cwsa-paper-k-research-only` envelopes with six SQLite-matching seals, member-by-member PIT/OOS and original-cost/market receipt hashes, risk-approved k limits, recorded negative findings, future effective start, and explicit `PAPER_ONLY` scope. These signed research attestations are *not* themselves executable Copy Mandates. The separately signed `cwsa_chapter2_paper_release_v1` must bind every member, the original account and scope, fixed-k risk policy, allowed markets and fresh independent L2 evidence. Never use a paper signing key for protected Guardian/broker authority.

The code can produce unsigned `UNQUALIFIED_K` paper candidate structure for review; no actual qualified six-portfolio research evidence or signing key may be manufactured by a code agent. Signed-paper activation requires a **new empty** financial epoch and future-effective mandates. A provisional journal can never be upgraded retrospectively.

### Permanent local CI and provenance

Run `scripts/ci.sh all` from the exact **committed clean** checkout; the existing pre-push hook calls it. Core, market, the mandatory CWSA/PM03 adversarial roster, frontend typecheck/build, Ruff lint/format and Python build are independently logged. The full run writes a non-overwritten receipt in the current worktree Git-dir under `local-ci/`, with commit/tree SHAs, Python and uv versions, source/contract/lockfile hashes, skipped tests, and the SHA of each original log. Recheck with `python -m copytrade_pm.pm_ci_receipt verify --root REPO --receipt PATH --sha COMMIT`. Publish the receipt path/hash and exact counts to the follow-up PR. An absent receipt is BLOCKED_EVIDENCE, not a claim that GitGuardian/hosted checks ran unit tests.

### Dashboard evidence contract

The privacy-safe v1 CWSA evidence projection is distinct from historical V4 and native broker outcomes. It shows exactly A, B, C, Combo2, regime.macro/TriadA and regime.macro/TriadChop; wallet aliases, causal source provenance, checkpoint/wave heads, signed admission blockers, k qualification, replayed financial status, and *nullable* modeled P&L/cost/position fields. Never synthesize a zero P&L for blocked financial journals. The deployed Site endpoint must be authenticated and carry the actual publisher revision, source-head hash and fresh generated timestamp. HTTP 200, a build, or a public registry snapshot alone cannot pass the Site smoke gate.

The intended Site source is currently untracked in the main checkout; preserve its owner/work. The independent source/finance projection library does not by itself publish, authenticate, or deploy the hosted Site. Keep the dashboard gate BLOCKED_EVIDENCE until a real publish/endpoint smoke check passes.

### Deployment / rollback / retention

Read the actual systemd unit files, configured ExecStart, independently observable application process/start identity, installed immutable release and journal heads immediately before acting; these may change concurrently. Confirm disk, RAM/swap, writer leases and a runnable previous release. Preserve all six current observation journals, historical 16-portfolio archive, original source records, protected Guardian/broker services and other sessions' dirty work. A rollback restores the previously pinned unit file/release; it must not rewind immutable financial/source journals. Report implementation, tests, GitHub merge, installed service, actual financial effects, economic qualification and protected trading authorization separately. Do not close #320 unless its **original 16-portfolio** requirement is independently proven.
