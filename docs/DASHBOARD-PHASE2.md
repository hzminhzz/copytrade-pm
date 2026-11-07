# Phase 2 — eight-view read-only dashboard (source-only)

Scope: parent #153, issues #159–#163. Base: merged Phase 1 PR #169
(`8495bf6c50082f9f1a5fd8267aaa08c75ad86ea5`).
No production installation, service restart, broker mutation or trading authority.

## Routes

Operations: `/` Overview; `/execution` Execution Monitor; `/risk` Guardian
Risk Status; `/health` System Health.

Research: `/research` Wallet Registry; `/portfolios` Portfolio Explorer;
`/performance` Financial Performance; `/lab` Immutable Research Lab.

Every page uses the Phase 1 authenticated run-only Marimo ASGI mount. The
existing localhost HTTP/WebSocket guard remains mandatory. Each UI table is
non-selecting, non-exporting; data queries accept fixed bounded scalars only.

## Native authority and missing evidence

- Guardian risk: the existing restricted producer-owned `operator_risk_v1`
  capture exposes exact decimal text for equity, daily/internal/trailing
  floors, risk_floor and headroom when cross-command release, account binding,
  journal sequence and clock parity hold. Missing capture or parity suppresses
  financial values. `pod_loss_used` is visible when available; the operator
  does **not** export the signed pod-budget limit, so utilization and percent
  remain UNKNOWN, not inferred from the familiar $200 example. Full exposure
  is likewise unavailable without an owner projection.
- Execution: `operator_portfolio_v1`, `operator_intent_v1`,
  `operator_broker_v1` expose bounded decision IDs, intent IDs, reported
  statuses, quantity, partial fill accumulator, broker epoch and reconciliation
  certainty. An exact ID/release join is accepted only on fully consistent
  restricted captures; duplicate decision IDs, stale sequence or missing
  release yield UNKNOWN. The operator does not expose verified source event,
  first-known, batch, broker-fill clock or coherent target/actual book. Those
  are **not** inferred. Timeout is not a confirmed failed order.
- Portfolio: `copytrade-pm portfolios list/current` query canonical SQLite.
  Version, namespace, membership, source seal, known-at and research-selected
  state remain distinct from UNKNOWN deployment and runtime states. Neither a
  process PID nor a research seal proves RUNNING_OBSERVED. As-of input requires
  UTC. The app does not mutate SQLite or fixed-k definitions.
- Research Lab: `copytrade-pm research list/show` reuse the immutable native
  `pm_offline_job` SHA-verified catalog. An admin must configure
  `DASHBOARD_RESEARCH_CACHE_ROOT`; there is no UI path input, job launcher or
  arbitrary filesystem scanner. Missing root -> UNAVAILABLE; report integrity
  failure -> BLOCKED. Contract-EV scenarios are not certified follower economics;
  their native offline tool is not executed on a dashboard refresh.
- Performance: the current operator schema has **no authoritative historical**
  account/pod equity tape; therefore the page displays its absence explicitly
  and shows only currently available Guardian metrics. The isolated
  `chart_data.prepare_series` + `linked_chart` utility handles **already
  authenticated** owner-supplied UTC, provenance-graded series. It uses Polars
  for bounded exact-Decimal-extrema sampling, retaining reset/gap boundaries;
  Altair interval brushing is browser-side and cannot trigger a Guardian read.
  There is deliberately no new history acquisition endpoint or synthetic chart.
  Historical source, modeled follower, paper, Demo and executed evidence cannot
  be combined under one identity. This is an outstanding real-series integration
  limitation, not scientific qualification.

**No production financial process is a dashboard dependency.** No dashboard
route may grant broker commands, alter HALTs, issue orders, change portfolio
allocation, execute research jobs or open a protected journal. A separate
owner-approved, unprivileged bounded capture producer is still required before
live Guardian finance can appear.

## Local verification

```bash
uv run --frozen --extra dashboard --group dev pytest -q
uv run --frozen --extra dashboard --group dev ruff check src/copytrade_pm/dashboard tests/test_dashboard_adapter.py tests/test_dashboard_security.py tests/test_dashboard_phase2.py
uv run --frozen --extra dashboard --group dev marimo check src/copytrade_pm/dashboard/pages/*.py
uv run --frozen --extra dashboard --group dev copytrade-pm capabilities validate
uv build
```

The eight mounted routes are covered by authenticated ASGI HTTP access tests,
and the HTTP/WebSocket authentication and local Host/Origin boundaries retain
Phase 1's negative regressions. The Phase 2 fixtures also exercise zero finance,
pod-budget unknown, release/sequence mismatch, duplicate decisions, partial/unknown
intents, canonical research selection, bounded report filters, chart extrema/gaps,
and forbidden read-to-write dependencies.

## Release and scientific gates

This phase is source-only. Pending: independent review; pinned companion tests;
restricted Guardian capture producer/release parity; authentic history and
execution tapes if those views are to become operationally informative; browser
mobile/load tests; private ingress/OS sandbox; no-degradation test against
running Guardian; signed install/rollback. No external evidence is promoted
by a passing unit or ASGI test. Leave parent #153 open until final release
phase and explicit separate authorizations.
