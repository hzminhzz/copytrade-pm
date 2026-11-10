# Track C — Versioned fixed-k research and SHADOW preflight (2026-11-10)

**Scope:** Research-only, nonactivating implementation against #256; #255 fast screening is an optional upstream input. No new k has been deployed, no portfolio seal rewritten, no paper journal modified, and no protected Guardian order authority changed.

## Interfaces

- `copytrade_pm.pm_k_recalibration.KResearchInput`: strict, immutable Pydantic research envelope keyed by sealed portfolio version/definition hash, pod, selected account, sizing policy, UTC as-of, cost/risk policy revisions, trial roster hash, upstream report SHA references, PM03/PM04 economic windows and candidate source/follower market and stress constraints.
- `evaluate_k(input)`: deterministic HOLD/DECREASE/INCREASE/INSUFFICIENT_EVIDENCE *research proposal*. Native fixed-k notional intent uses `target_from_fixed_k`; the optional `PM03FinanceFrame` restores a cloned PM03 account and reuses `classify` plus PM04 independent pod budget validation, rounding and existing inventory. It never changes the original financial ledger. With no independent original-prospective verifier, every proposed increase **abstains** instead of claiming qualification.
- `KProposal`: SHA-bound immutable result with explicit reason codes, OOS sample counts, historical/prospective label, original trial counts, paired-control statistics and nonauthorization fields. `INCREASE` is blocked in v1 even if a supplied JSON calls its evidence authentic; an original verifiable attestation boundary must be built separately. Because frozen Pydantic models may contain mutable nested mappings, candidate construction, preflight and publication revalidate the entire serialized proposal/candidate SHA to detect post-validation tampering.
- `PairedControlBlock`: immutable OOS/forward follower-net comparisons against current-k, cash, matched-wallet and asset controls, with BASE/DELAYED/ADVERSE alignment, seven distinct days, multiplicity-inclusive one-sided normal diagnostic and historical proof abstention. This confidence approximation is **not** certified independently sampled alpha. `#255` remains the owner of its own three-scenario minute-ORACLE screening and historical costs.
- `run_k_job(job, input_root=..., cache_root=...)`: explicit `track_c_k_research_job_v1` manifest, bound `KResearchInput` JSON, optional separately SHA-verified #255 report and established `shortlist_for_pm03` interface. Publishes a content-addressed `track_c_k_research_report_v1` using the existing `ImmutableCache` owner. No historical v1 job/hash mutation.
- `make_candidate` and `offline_preflight`: immutable, unsigned, future-effective **nonactivating** release candidate and read-only SHA/identity/rollback check. The pure `bind_opportunity_k` audit method never switches active k or creates a catch-up action.
- `pm_k_release.verify_cutover`: validates a pinned PM03 account v2 / PM04 single-shot intents v2 paper snapshot and its active policy SHA; explicitly blocks T+180 pending entries, held inventory, unresolved exits, HALT, drift and unversioned runtime cutover. `publish_k_candidate` produces a separately cached, unsigned, noninstallable canary candidate package with repeatable hashes.

## Input manifest example

```json
{
  "schema": "track_c_k_research_job_v1",
  "study_id": "portfolio-pod-k-20261110",
  "research_input": "k-input.json",
  "research_input_sha256": "<sha256 of exact JSON bytes>"
}
```

Optional #255 consumer inputs: `screen_report_path` and `screen_report_sha256`; the pinned input must separately declare `screen_report_sha256` and `screen_cost_policy_version`. These are **never** substituted as PM03 financial evidence or equated with V4 live cost assumptions.

```bash
uv run --frozen --group dev python -m copytrade_pm.pm_k_recalibration_job \
  /private/research/job.json --input-root /private/research \
  --cache-root /private/research-cache
```

`KResearchInput` must include all typed required fields. Ingested windows are explicit **assertions** until their upstream PM03 reports have been independently verified. The import does not validate a purported prospective class merely because the JSON says `PM03_PROSPECTIVE_SHADOW`. The output therefore always carries `finance_report_authenticity_independently_verified=false`, `release_eligible=false`, `scientifically_qualified=false` and `order_route=NONE`. **A positive `INCREASE` cannot be issued under the current v1 proof contract.** Signed/independently attested evidence requires a future compatible evidence-verification integration.

## Operational financial seams and rollback

Actual existing `PaperJournal` uses private `runs`, `events`, `funding_claims`, source/market receipts and hashed event sequences in `paper-events.sqlite3`. The prospective Pydantic V4 paper consumer freezes k in its `PM04_CONFIG` policy profile and reads `profile.k[pod]` when attempting a pending opportunity; its `PaperOpportunity` persists original first-known T0, due, update and terminal identities. A candidate **must not** replace the running profile or historical `PM04_CONFIG` mid-flight. The present release interface intentionally cannot do so.

For a later *separately approved* SHADOW canary:

1. Verify exact origin/main and feature-wheel content hash, private SQLite sealed definition, signed portfolio/selection, existing policy hash, snapshot source/quote freshness, trial/economic evidence and independent financial report verification. Rerun PM03/PM04 risk and inventory checks with actual current journal facts. No automatic approval from contract validation.
2. Pin a new profile/release identity and strictly future effective time. Stop or fence the target worker under separate operator authorization, back up sealed financial journals, verify active and pending intent identities and cutover ownership; preserve pending T+300 k/T0 and existing inventory/exit responsibilities. Do not reinterpret an old journal by reloading a different profile.k; use a separately compatible execution boundary if required.
3. Run read-only preview and fail-injected restart against the actual original journal format, including duplicate intent, T+180 pending, overlapping pods and wallet reused across portfolios, unmatched funding, min lot, insufficient source scope, stale quote, mismatched policy and drawdown HALT. Require no new-risk catch-up, no duplicate entry and no broker path.
4. Separately authorized rollback must restore pinned *prior release* for **new** opportunities without rewriting existing journal rows, open exposure or previous k. Observe original source/market receipts and independent PM03/04 health before any operational acceptance.

**Current blockers:** no independently reconciled prospective entry/exit economic tape for these candidate portfolio/pod combinations; imported PM03 economic windows require independent authentic source, funding and quote verification; no runtime cutover seam for applying a newly signed k while preserving prior opportunity profiles has been implemented or activated. Track A authentic source continuity, Track B health interface, independent OOS controls, genuine capacity/latency economics and exact contract terms remain distinct future acceptance gates.

## Parallel implementation reconciliation

The local independent branch `feat/track-c-k-256-20261110` at `1e12e40` was inspected without modifying its committed files. Relevant stronger design elements were manually reconciled into PR #259: original PM03 snapshot cloning, PM04 risk/budget reuse, paired follower controls and multiplicity, actual v2 journal cutover refusal, and immutable unsigned candidate packaging. The original branch and worktree remain preserved for review. The overlapping `pm_k_recalibration.py` variants were not blindly cherry-picked or mixed into two competing authorities. The canonical integration branch remains `feat/track-c-k-recalibration-256-20261110-v2`.

## Evidence statuses

- Engineering: focused contract, journal noninterference and immutable-cache checks can be tested locally.
- Economic: no proof of positive executable follower alpha from model fixtures or historical screen.
- SHADOW deployed: **NO**; candidate is deliberately noninstalling.
- Trading authorized: **NO**; Guardian and broker interfaces untouched.

Use this documentation with the versioned release candidate, not as an operator cutover instruction or authorization.

## Follow-up #268: original T+300 k freeze (engineering only)

An independently isolated follow-up branch adds nonactivating opportunity-level
`frozen_k` and `release_sha256` to the original `PM04_PAPER_SOURCE` event and
`pm04_single_shot_intents_v2` opportunity history. At genuine first-known T0,
the original frozen PM04 policy and its SHA are bound to the immutable pending
opportunity. Coalesced source changes preserve this k and release identity;
restarts replay the same original event. An eventual T+300 attempt sizes from
the persisted original k instead of re-reading the mutable profile reference.
The PM04 reducer rejects mismatched execution k/release receipts before any
modeled fills. Older journals remain readable as legacy unversioned intent
records; they **must not** be promoted into a new k release and the separate
cutover verifier remains `BLOCKED_NONACTIVATING` for such exposures.

The merged-policy independent read-only cutover auditor now distinguishes
strictly validated `frozen_k` and `release_sha256` pending intents from legacy,
corrupt, source-sequence-drifted, wrong-pod or wrongly scheduled T+300 intents.
`track_c_pending_t300_k_audit_v1` returns exact pending/pinned/legacy counts,
original policy SHA, and blockers without mutating PM03/PM04. A valid original
pending intent is *preserved*, not converted into a new-k release. Original
policy hash provenance is NOT a signed risk-release attestation.

This fixes only the missing original opportunity k identity and improves
read-only cutover auditing. A signed and independently approved future-effective
SHADOW release loader, grandfathered held-inventory identity, authentic
original FinanceWindow verification, rollback/crash/restart release cutover
and a live verified canary remain blocked. In all cases
`verify_cutover.status=BLOCKED_NONACTIVATING`; neither positive Pydantic
validation nor a commit grants release or trading authority.
Do not claim #268 completed, financial qualification, k activation or broker
permission from this engineering subset.
