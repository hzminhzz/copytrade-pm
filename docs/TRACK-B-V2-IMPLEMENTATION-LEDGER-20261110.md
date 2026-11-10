# Track B v2 — implementation / acceptance ledger

Date: 2026-11-10. Parent: https://github.com/hzminhzz/copytrade-pm/issues/273. Tickets: #274–#288. The preserved Q3–Q35 ADR and Q35 audit define the normative acceptance contract.

## Isolation and financial boundaries

Isolated worktree: /home/quant/.devspace/worktrees/copytrade-pm-d6429592.
Branch: feat/track-b-v2-strategy-health-273-20261110.
Verified origin/main base: 5df554dce30a3bc7b6df455754aa0fab8c557295.
Original shared main checkout (nine commits behind and carrying untracked work) and local design branch were never edited. Track B does not write the SQLite registry, official V4 source, original PM03/PM04, Guardian, protected k releases, v1 wallet health or Track C.

## Ticket / test ledger

| Ticket | Owner code and acceptance proof | Status |
| --- | --- | --- |
| #274 | strategy_health.py: Pydantic strict sealed private report, T0/k/scope, 0600 no-clobber. test_strategy_health_v2.py; I01/I14 | Implemented, research-only |
| #275 | strategy_source_verify.py: original Ed25519 V4 packet/book/journal validation; I03/I13/C03 | Implemented, no invented transition |
| #276 | strategy_matched_pm04.py: two independent research runs through ORIGINAL PM03/PM04 on shared-account rules; I12/C07 | Implemented, synthetic only |
| #277 | strategy_census.py, strategy_selection.py: SQLite-selected account/seal and full first-known census with GAP UNKNOWN; I01/I02/I03 | Implemented, real live authenticity pending |
| #278 | strategy_finance.py: original PM04 paper attempt, source history/T+300 and expiry matching; I06–I08/C02 | Implemented, unknown if unjoined |
| #279 | Same PM03 original-finance reducer: mark-to-market open loss, pod R, fees/funding quote veto and global HALT; I05/I09–I11/C01/C04 | Implemented, comparable real net pending |
| #280 | attach_to_strategy: original same-account matched synthetic marginal context; I12/C07 | Implemented, no prospective promotion |
| #281 | strategy_windows.py: 7/30/90 first-known cohorts, source denominator, clustered effective N; I02/I04/I15/C04–C06 | Implemented, descriptive |
| #282 | strategy_health_projection.py and additive Grafana/evidence_plane route: redacted read-only GET; I16/C08 | Implemented, v1 untouched |
| #283 | strategy_incidents.py: selected-source GAP/quote/real PM03 exposure risk, two-cycle owner route, private ACK; C01/C08 | Implemented, owner routing unverified |
| #284 | strategy_advisory.py: predeclared weekly early/persistent provisional thresholds and explicit false-warning uncertainty; I15/C05 | Implemented, not calibrated |
| #285 | Two-look conservative recovery, 8 new causal roots, 7 days, 90% matching, adverse effect <0.25R; C05/C06 | Implemented, missing authentic proof retains warning |
| #286 | strategy_proof.py: immutable private reference rechecked against original source/market full quote chain/PM03; C03 | Implemented, no Track C FinanceWindow admission |
| #287 | test_strategy_acceptance_v2.py: 16 independent / 8 combined injections | Implemented, all named tests required green |
| #288 | strategy_release_candidate.py, separate signed private publication binding and non-writing release attestation, operator rollback runbook | Candidate package, NOT DEPLOYED |

The table denotes engineering scope, not a GitHub closure or authorized release. Preserve #274–#288 issue-closing references in the reviewable PR; they close only after a separately authorized merge.

## Q32 independent cases

| ID | Injection / observable invariant |
| --- | --- |
| I01 | Discovery wallet lacks prospective and incident authority |
| I02 | Genuine unchanged official V4 book after 45 days: one first-known transition; independently retained open follower MTM |
| I03 | Duplicate signed source replay never creates another opportunity |
| I04 | Overlapping causal roots cannot double effective sample size |
| I05 | Negative but unclosed original follower MTM remains open |
| I06 | Pending T+300 expires without quote; no invented fill |
| I07 | GAP at T+299 cancels imminent new-risk attempt |
| I08 | Reconnect baseline cannot resurrect canceled intent |
| I09 | Stale original quote vetoes comparable follower finance |
| I10 | Unknown funding vetoes net inference |
| I11 | PM03 HALT and malformed source preserve held original follower inventory |
| I12 | Shared-account comparison reruns original PM04 netting/risk |
| I13 | Historical fill posed as V4 transition rejected |
| I14 | Frozen per-opportunity k/T0 cannot rebase |
| I15 | 8/7/80 provisional gate is not a scientific acceptance |
| I16 | New GET-only v2 redacted endpoint; authenticated v1 separation |

## Q32 combined cases

| ID | Coinjected adversarial faults |
| --- | --- |
| C01 | GAP + stale quote + genuinely open original PM03 risk: critical incident, no order |
| C02 | Duplicate + reconnect baseline + T+300 pending: no recreation |
| C03 | Forged original T0 + valid-looking private SHA + Track C import: reject |
| C04 | Negative open MTM + clustered sample + missing funding: abstain |
| C05 | Adverse 7d + insufficient 30d + favorable 90d: no unsupported persistent inference or time-only clearance |
| C06 | Frozen k rollover + overlapping pods + replayed outcome: reject/do not inflate N |
| C07 | Shared-account marginal + pod risk latch + separate PM03 HALT: no bypass |
| C08 | Original v1 + stale v2 + actual open-risk incident: v2 503, v1 intact |

All cases are parameterized with these exact IDs under tests/test_strategy_acceptance_v2.py. The tests are deterministic isolated fixtures, never independent live follower-dollar proof.

## Reproducibility

From the feature worktree, run (captured exact status and log belong in the PR):

    uv run --frozen --group dev ruff check .
    uv run --frozen --group dev ruff format --check src/copytrade_pm/strategy*.py tests/test_strategy*.py src/copytrade_pm/dashboard/evidence_plane.py src/copytrade_pm/dashboard/grafana_projection.py
    uv run --frozen --extra dashboard --group dev python -m pytest -q tests
    uv run --frozen --extra dashboard --group dev python -m pytest -vv tests/test_strategy_acceptance_v2.py
    uv run --frozen --group dev copytrade-pm capabilities validate
    uv build
    git diff --check

Record exact head SHA, build wheel/sdist SHA256, 24/24 adversarial receipt and skipped cases from the final run. Source-and-finance authentication cannot be established by passing these tests.

## Evidence / release statuses

IMPLEMENTED: all 15 additive program slices are present in the feature branch.
ENGINEERING VERIFIED: only when the recorded final full suite, lint, formatting, build and adversarial checks pass.
SOURCE/FINANCE AUTHENTICATED: NO for live wallets/portfolios; real selected-parent SQLite seal, first-known V4 source, original matched PM03, quote/fee/funding/exit completeness have not been externally qualified.
SCIENTIFICALLY QUALIFIED: NO. Thresholds 8/7/80, 20/14/90 and 10% intended false warning fraction are provisional, not independently calibrated.
DEPLOYED: NO. TRADING AUTHORIZED: NO. Owner paging: NO.
Unknown/missing inputs stay UNKNOWN or INSUFFICIENT_EVIDENCE. No k activation, no second financial ledger, no broker/Guardian commands.

## Post-merge optional orchestration follow-up

On 2026-11-10, Prefect 3 was adopted as an **optional research-only adapter**
for content-addressed private assessment jobs. This does not change the status
or original proofs of #274–#288; see
[the separate Prefect runbook](TRACK-B-PREFECT-ORCHESTRATION-20261110.md).
No persistent Prefect service, live V4/PM03 worker mutation or scientific
promotion is included in this follow-up.

## Pending operational/scientific gates

- Independently prove real source and PM03/market/fee/funding/selected SQLite original evidence for each prospective campaign. Do not reuse historical retrospective k or self-authenticated report hash as proof.
- Track C independent original FinanceWindow proof and version-aware release consumer (#267/#268) remain blocked; no automatic k changes or release activation.
- Measure actual selected-source expected cycle cadence and verify owner/notification route + 10-minute acknowledgment with real evidence before operational SLA is claimed.
- A separate authorized shadow deployment must pin the real release revision, verify Grafana ingress/permissions, v1 rollback checkpoint and original journal-state invariance. The package below is read-only and nonactivating.
