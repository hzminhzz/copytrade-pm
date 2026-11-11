# Canonical checkpoint implementation — #313

Implementation integration branch: `integration/cwsa-313-20261112`.
Approved design: [Q1–Q24](decisions/2026-11-11-canonical-5m-checkpoint-grill.md).
Current work is nonactivating engineering. Legacy T0+300, installed services,
original journals, HALTs and broker permissions retain their existing contracts.

## #314 — native checkpoint candidate

`pm_checkpoint_source.collect_checkpoint` uses the existing native read-only
Hyperliquid transport and immutable original-wire sidecars. It records the UTC
boundary separately from request, response, provider-state and validation clocks.
Every selected DEX must explicitly return its complete position list, including
a valid empty list. Exact finite Decimal positions retain native DEX namespaces.

The existing sealed SQLite selection reader supplies source identities through
`selected_checkpoint_sources`. Source scope generation depends on the account
and DEX scope, independently of a follower's mandate generation. The candidate
has no signal, order or financial authority.

`SamplingLimits` has no numerical defaults. Missing limits, a late or preboundary
sample, old/future source clocks, cross-DEX skew, timeout/429, catalog drift,
malformed quantities, duplicate positions or conflicting identity produces an
UNAVAILABLE outcome, never an inferred empty book. Fixture limits are synthetic.

TDD evidence: positive native collection failed on the missing entrypoint, then
passed. Completeness and timing negatives failed before their guards were added.
Focused source/legacy regression: **30 passed**. Native capacity and measured
production limits remain separate #317 evidence; passing fixtures do not qualify
them. No service, signing-key provisioning or protected journal was changed.

## #315 — durable source continuity

The existing `PaperJournal` owns additive CWSA source tables in its existing
SQLite database. Typed transitions persist predecessor, event, original-evidence
digest, guard, actor, successor and durable outcome. Registration is explicit.
Every skipped scheduled boundary records UNAVAILABLE at its actual detection
time. The first complete book and first recovery book remain nonopening.

Economic equality uses exact Decimal quantities; outcome and signal IDs are
separate. Same-payload replay is idempotent. Equivocation and reordered samples
append a fenced rejection without overwriting history. Original native bytes
are replayed before entering the journal transaction.

Verification: **39 passed** across checkpoint reader/journal and existing journal
regressions, including actual SIGKILL before and after SQLite commit. Full gates
will be rerun at integration. This is source evidence only; no financial writer
or scheduler has been added.

## #316 — signed source delivery

The existing source exporter, spool, root-mediated file handoff and protected
source receiver have a separately pinned v3 checkpoint path. It binds the full
scope and policy, exact source transition chain, complete quantity vector,
original native bytes/hashes and native request preimages. The receiver replays
native scope/vector/clocks independently, preserves CWSA IDs, and adds no T+300
timer. A subsequent source fence revokes an unconsumed opening candidate.

Synthetic tests cover two independent consumer cursors, tampering, wrong signer,
scope/policy/cursor faults, original-byte omissions, immutable handoff, restart,
and SIGKILL before/after the source-only commit. Focused PM delivery/source and
legacy suite: **44 passed**. Protected delivery/handoff suite: **23 passed**;
strict mypy passed. Legacy wire versions stay supported; active installed wire
remains v1. These results do not authorize a protected deployment or order.

## #317 — native capacity evidence

[Bounded capture report](CANONICAL-5M-CAPACITY-317.md) records three actual
14-parent / 11-DEX runs, exact revision and immutable hashes. Every run returned
all native scopes. Timing policy, long-run tails and shared-IP headroom remain
UNKNOWN; the experiment creates no numerical production defaults.


## #318 — immutable signed Copy Mandates

New `copy_mandate_v1` and `portfolio_release_v2` contracts freeze source scope,
account, pod, generation, k, native markets, timing/risk policy and effective
interval. `FIXED_K_NATIVE_QUANTITY` retains its existing meaning. Activation
waits for the first post-activation complete checkpoint; the baseline has no
financial effect. Pause/retire stop new risk and preserve all prior obligations.
Resume requires a new immutable generation; overlapping active intervals and
rollback are rejected. Source history is independent of follower lifecycle.

Both existing journals persist explicit predecessor/event/evidence/guard/
successor/effect records. Approval signatures and controls are retained and
replayed. Controls must use the originally pinned authority. Guardian rejects
legacy admission for v2 releases. No broker call occurs in lifecycle transitions.

Adversarial TDD found and fixed an unregistered receiver genesis and a foreign
paper-control signer. Receiver restart now revalidates retained signed packets
and requires exact proof coverage for every stored transition. Focused mandate,
source and Guardian verification: PM 18 passed; protected 43 passed; strict mypy
passed. Full integration and prospective evidence remain separate gates.

## #319 — one-portfolio checkpoint paper

`PaperJournal.consume_checkpoint` adds a versioned causal event to the existing
PM03 account journal. Source history and mandate approvals are independently
replayed. No extra financial tables, source timer or broker transport are added.
Typed one-shot opportunities have a fixed deadline, explicit non-dispatch
blocking, terminal misses, and one modeled commitment. Baseline, unchanged and
recovery observations cannot open or fabricate closes.

Frozen-k requested notional uses original native positionValue / abs(szi).
The independent L2 executable side and native lot contract determine follower
quantity. Existing PM03 classification, execution, risk scaling, cash, costs and
allocation conservation own the modeled outcome. Requested targets remain
visible when risk scaling reduces the actual modeled quantity. Other owners'
inventory is preserved; gross and individual pod stress limits remain explicit.

TDD began with the missing public consumer. Focused S1/source/mandate/legacy
regression: **43 passed**, including real SIGKILL before and after the financial
commit, duplicate/restart, deadline equality, unchanged nonretry, genuine later
change, native rounding, reduce/exit/reversal, source gap/recovery, and an
independent HALT between boundaries. Ruff and format passed. These are synthetic
engineering tests; no new prospective campaign or economic qualification is
claimed. Current native timing-policy and real mandate approvals remain blocked.

## Dependency graph

| Ticket | Prerequisites |
| --- | --- |
| #314 | None |
| #315 | #314 |
| #316 | #315 |
| #317 | #314 |
| #318 | #316 |
| #319 | #316, #318 |
| #320 | #319 |
| #321 | #316, #318 |
| #322 | #321 |
| #323 | #322 |
| #324 | #321, #322 |
| #325 | #320, #323, #324 |
| #326 | #317, #320 |
| #327 | #325 |
| #328 | #317, #325, #326, #327 |

The existing sixteen-portfolio campaign loader distinguishes SQLite-approved
historical profiles from unsigned prospective paper scenarios. Do not relabel its digest
as a signed Copy Mandate or a current SQLite portfolio selection. Native source
measurement may use the explicitly requested campaign roster read-only; protected
activation still requires independently verified mandates and authorization.
