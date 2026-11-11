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

The existing sixteen-portfolio campaign loader distinguishes historical signed
profiles from unsigned prospective paper scenarios. Do not relabel its digest
as a signed Copy Mandate or a current SQLite portfolio selection. Native source
measurement may use the explicitly requested campaign roster read-only; protected
activation still requires independently verified mandates and authorization.
