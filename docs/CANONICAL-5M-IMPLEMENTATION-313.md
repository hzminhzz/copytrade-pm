# Canonical checkpoint implementation — #313

**Role:** DATED IMPLEMENTATION LEDGER for the original `integration/cwsa-313-20261112` program. Preserve the individual evidence and acceptance scope below. [Parent #313](https://github.com/hzminhzz/copytrade-pm/issues/313) and the [versioned dossier](evidence/CWSA-313-DOSSIER-v1-20261112.md) distinguish completed engineering from prospective/economic/release blockers; recheck live issue state. [Chapter 2](CWSA-CHAPTER2-20261112.md) owns its separate current operating procedure. The [agent system plan](AGENT-SYSTEM-DESIGN.md) deepens existing diagnostics/discovery and does not reopen completed domain implementation or replace the original sixteen-portfolio acceptance.

Approved design: [Q1–Q24](decisions/2026-11-11-canonical-5m-checkpoint-grill.md). Engineering evidence below does not independently establish installed policy, financial admission, scientific qualification or broker permission.

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

## #320 — shared-source sixteen-portfolio paper

The existing `PaperCampaign` now accepts caller-scheduled checkpoint waves and
exposes per-account coverage, dispositions, quantities, costs, P&L and journal
heads. No second source timer exists. The selected-campaign entrypoint checks
the existing SQLite-backed campaign definition, complete member coverage,
source account hashes, frozen k, approved run/mandate ownership and pod risk
ceilings before consumption. Missing approvals are UNRESOLVED, never implicit
activation.

A reproducible synthetic sixteen-account wave shares exactly one CWSA history
and signal ID, uses independent k/finance, isolates one HALT, and survives replay.
A two-source account test proves unavailable B preserves its inventory while
healthy A can act only after full existing risk checks; coverage stays incomplete.
Selected-campaign missing-approval and changed frozen-k negatives are explicit. Focused paper/source/
existing observed-paper regression: **40 passed**; Ruff/format passed.

The actual campaign was re-read without mutation: 16 scenarios, 14 deduplicated
parents, and the unchanged manifest SHA
`7c0b2a021a449c06f818cacf2f757a4d40b89e77669316107dc08ca659237e6f`.
P1/P14/P16 are historical SQLite-approved profiles; the other 13 remain unsigned
prospective paper scenarios. Existing exclusions and k-conflict flags remain.
No real signed checkpoint mandates or qualified native timing policy have been
established; these block prospective acceptance, not the synthetic engineering
implementation. No current T0+300 result is relabeled.

## #321–#325 — protected boundary and cross-repository proof

The existing Guardian owns checkpoint opportunities, market/checkpoint claims,
exact pod allocation, average-cost fixture basis, independent account evidence,
one-shot reservation/outbox dispatch and broker reconciliation. Source, mandate,
financial and broker transitions remain separately owned. Same-account gross
risk is assessed before offsetting pods; zero external netting creates no
fictitious execution costs or profits. Native cross-zero capability is UNKNOWN
unless independently established; the synthetic reference proves safe-net and
reduce-only/MISSED cases without a real route.

Old mandate generations retain fills, costs, positions, HALT and UNKNOWN
obligations. A successor cannot reset shared source continuity or erase retained
owner risk. Actual SIGKILL tests establish before/after-commit behavior and
independent fill adoption after restart without resubmission.

The clean #325 matrix at research `a18c8c0f7af9851cfec2f9588a92e501331d1fff`,
application `3337dd2db8c6c8c8df4cb1e66a151a2b244a1b1e` and connector
`ea95f9bf9661bcda41685d6ba939aa349628f8f5` passed: application Python 3.13/3.14
each 321/1 skipped, connector 399/1 skipped, mocked native adapter groups 2 and
15 passed, research all-extras 2127/6 skipped. Exact producer vectors, 16
independent paper accounts and the Guardian consumer were compared across clean
pinned checkouts. Later review corrections receive their own final gate receipt.
See prop-production `docs/CHECKPOINT-INTEGRATION-325.md` for the owner contract.

## #326 — reproducible matched follower economics

[The evaluator contract](CANONICAL-5M-ECONOMICS-326.md) requires exact clean code,
original immutable ledger/manifest heads, matched scope/frozen k, independent
causal quotes, original source proofs and a predeclared signed criterion.
It replays the existing financial owners rather than introducing a simulator.
Missing legs, coverage gaps and incomplete provenance remain missing; fixture
fills or shared marks do not become native executable P&L. The actual new
prospective cohort and approved study criterion do not yet exist.

## #327 — nonactivating release and compatible rollback

The application verifies a signed candidate's exact code/schema/trust/scope and
strictly future boundary without advancing its signer floor. Its existing
isolated Guardian worker rehearses baseline, source GAP, scope rejection,
restart and intact HALT with zero broker submissions. Compatible code recovery
changes code/units only; an incompatible older contract keeps services stopped
and preserves new durable state. See prop-production
`docs/CHECKPOINT-SHADOW-RELEASE-327.md`.

A real operational candidate still requires approved measured source limits,
real new mandate signatures and a future effective boundary. Publication of the
engineering artifacts is not deployment or authorization.

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
