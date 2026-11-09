# Track C — Versioned fixed-k research and SHADOW preflight (2026-11-10)

**Scope:** Research-only, nonactivating implementation against #256; #255 fast screening is an optional upstream input. No new k has been deployed, no portfolio seal rewritten, no paper journal modified, and no protected Guardian order authority changed.

## Interfaces

- `copytrade_pm.pm_k_recalibration.KResearchInput`: strict, immutable Pydantic research envelope keyed by sealed portfolio version/definition hash, pod, selected account, sizing policy, UTC as-of, cost/risk policy revisions, trial roster hash, upstream report SHA references, PM03/PM04 economic windows and candidate source/follower market and stress constraints.
- `evaluate_k(input)`: deterministic HOLD/DECREASE/INCREASE/INSUFFICIENT_EVIDENCE *research proposal*. Native fixed-k notional intent uses `target_from_fixed_k`; worst-case price shocks reuse PM03 `loss_under_shock`. This is **not** a PM03 account replay, broker margin engine or proven portfolio profit.
- `KProposal`: SHA-bound immutable result with explicit reason codes, OOS sample counts, historical/prospective label, original trial counts, and nonauthorization fields.
- `run_k_job(job, input_root=..., cache_root=...)`: explicit `track_c_k_research_job_v1` manifest, bound `KResearchInput` JSON, optional separately SHA-verified #255 report and established `shortlist_for_pm03` interface. Publishes a content-addressed `track_c_k_research_report_v1` using the existing `ImmutableCache` owner. No historical v1 job/hash mutation.
- `make_candidate` and `offline_preflight`: immutable, unsigned, future-effective **nonactivating** release candidate and read-only SHA/identity/rollback check. The pure `bind_opportunity_k` audit method never switches active k or creates a catch-up action.

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

`KResearchInput` must include all typed required fields. Ingested windows are explicit **assertions** until their upstream PM03 reports have been independently verified. The import does not validate a purported prospective class merely because the JSON says `PM03_PROSPECTIVE_SHADOW`. The output therefore always carries `finance_report_authenticity_independently_verified=false`, `release_eligible=false`, `scientifically_qualified=false` and `order_route=NONE`. Even a conditional `INCREASE` proposal is never an approved or installable release.

## Operational financial seams and rollback

Actual existing `PaperJournal` uses private `runs`, `events`, `funding_claims`, source/market receipts and hashed event sequences in `paper-events.sqlite3`. The prospective Pydantic V4 paper consumer freezes k in its `PM04_CONFIG` policy profile and reads `profile.k[pod]` when attempting a pending opportunity; its `PaperOpportunity` persists original first-known T0, due, update and terminal identities. A candidate **must not** replace the running profile or historical `PM04_CONFIG` mid-flight. The present release interface intentionally cannot do so.

For a later *separately approved* SHADOW canary:

1. Verify exact origin/main and feature-wheel content hash, private SQLite sealed definition, signed portfolio/selection, existing policy hash, snapshot source/quote freshness, trial/economic evidence and independent financial report verification. Rerun PM03/PM04 risk and inventory checks with actual current journal facts. No automatic approval from contract validation.
2. Pin a new profile/release identity and strictly future effective time. Stop or fence the target worker under separate operator authorization, back up sealed financial journals, verify active and pending intent identities and cutover ownership; preserve pending T+300 k/T0 and existing inventory/exit responsibilities. Do not reinterpret an old journal by reloading a different profile.k; use a separately compatible execution boundary if required.
3. Run read-only preview and fail-injected restart against the actual original journal format, including duplicate intent, T+180 pending, overlapping pods and wallet reused across portfolios, unmatched funding, min lot, insufficient source scope, stale quote, mismatched policy and drawdown HALT. Require no new-risk catch-up, no duplicate entry and no broker path.
4. Separately authorized rollback must restore pinned *prior release* for **new** opportunities without rewriting existing journal rows, open exposure or previous k. Observe original source/market receipts and independent PM03/04 health before any operational acceptance.

**Current blockers:** no independently reconciled prospective entry/exit economic tape for these candidate portfolio/pod combinations; imported PM03 economic windows require independent authentic source, funding and quote verification; no runtime cutover seam for applying a newly signed k while preserving prior opportunity profiles has been implemented or activated. Track A authentic source continuity, Track B health interface, independent OOS controls, genuine capacity/latency economics and exact contract terms remain distinct future acceptance gates.

## Evidence statuses

- Engineering: focused contract, journal noninterference and immutable-cache checks can be tested locally.
- Economic: no proof of positive executable follower alpha from model fixtures or historical screen.
- SHADOW deployed: **NO**; candidate is deliberately noninstalling.
- Trading authorized: **NO**; Guardian and broker interfaces untouched.

Use this documentation with the versioned release candidate, not as an operator cutover instruction or authorization.
