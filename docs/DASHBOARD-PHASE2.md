# Phase 2 — eight-view read-only Marimo dashboard (source implementation)

Parent #153; tickets #159–#163. Phase 1 reviewed and merged via PR #169
(base `8495bf6c50082f9f1a5fd8267aaa08c75ad86ea5`).
**Source/testing only. No production installation, service restart, broker mutation,
HALT control or trading authority.**

## Routes and security

Operations: `/` Account Overview, `/execution` Execution Monitor,
`/risk` Guardian Risk, `/health` System Health.

Research: `/research` Wallet Registry, `/portfolios` Portfolio Explorer,
`/performance` Financial Performance, `/lab` Immutable Research Lab.

All eight routes share the Phase 1 authenticated run-only Marimo ASGI host.
Local HTTP/WebSocket Host/Origin and signed-cookie denial remain mandatory.
No broker, Guardian or research-job mutation control is in any page.
All tables are no-selection, no-download; server inputs are capped scalars.

## Native owner contracts and evidence limitations

**Risk (#159).** Owner-supplied `operator_risk_v1` reports exact Decimal
equity, contractual daily/internal/trailing floors, headroom, HALT and
pod-loss usage. Cross-command account-binding/release/sequence and freshness
parity must pass. Missing values remain UNKNOWN and zero stays zero.
Optional companion `prop-production` owner projection reports gross/net
mark exposure only if its broker snapshots are coherent with complete
positions/marks; no chart-defined risk. Signed pod-loss budget is **not**
present in the current financial journal: do not infer $200 from fixtures or
claim loss-budget utilization. A trigger does not guarantee a maximum loss.

**Execution (#160).** Owner `operator_portfolio_v1`, `operator_intent_v1`
and `operator_broker_v1` provide bounded durable ID links. The optional
companion owner projection adds hashed original source receipt IDs, distinct
source event/source-known/first-local timestamps, true 300-second due clocks,
Guardian decision and intent clocks, sent clock, and broker fill-known events.
The dashboard only joins on stable decision/intent IDs, matching active
release and coherent account sequence. Contradictory causal clocks,
duplicate fills or mismatched captures stay UNKNOWN. Broker acceptance and
verified target-vs-actual books remain unavailable; a timeout is not failed
order proof. No orders can be routed from these views.

**Portfolio (#161).** Canonical SQLite `copytrade-pm portfolios list/current`
own namespace-qualified frozen identities, versions, as-of membership and
saved/research-selected distinctions. The dashboard never treats research
selection, observed service PID or source receipt as DEPLOYED or
RUNNING_OBSERVED. Explicit signed installed-release-to-portfolio membership
and runtime heartbeats are required to promote those states; in their
absence both remain UNKNOWN. No fixed-k mutation occurs.

**Performance (#162).** The companion `prop-production.dashboard_capture`
can export **at most 256 recent** hash-chain-verified Guardian RECONCILE
finance snapshots. Source finance time, journal sequence, release, equity,
unrealized, floor, headroom and contractual UTC day are preserved. These
are owner **SHADOW** observations, *not* authenticated broker-executed
follower history, complete source-wallet performance or fabricated pod
equity curves. Only owner capture with coherent binding produces a chart;
otherwise UNAVAILABLE/BLOCKED is shown. Polars exact Decimal sample
selection keeps extrema, explicit gaps and reset boundaries; Altair interval
brushing is browser-only. Risk authority never uses plotted floats.
Older releases are plotted under independent source IDs.

**Research Lab (#163).** `copytrade-pm research list/show` reads only the
native immutable SHA-verified `pm_offline_job` cache selected by owner
`DASHBOARD_RESEARCH_CACHE_ROOT`; no user-provided paths, file scanner, job
execution or simulation. Shows report/job hashes, input/market binding
hashes and available source fingerprints. If UTC scope, sealed portfolio
identity or full tape economics are absent from the verified report, show
UNKNOWN rather than manufacture them. The read-only native contract-rules
catalog is displayed with explicit **SCENARIO_ONLY** terms and unknown
provider conditions; the expensive native EV comparator is not invoked
by a page.

## Companion capture and permissions

The optional read-only owner-side producer is proposed in
[prop-production companion PR #43](https://github.com/hzminhzz/prop-production/pull/43),
implemented at `prop-production/src/prop_production/dashboard_capture.py`
and documented in `prop-production/docs/DASHBOARD-READ-PROJECTION.md`. It uses a
**single** hash-verified financial journal generation to produce six
fixed bounded files (`status/risk/broker/portfolio/intent/history.json`)
with capture/release/sequence/account SHA evidence. Owner-only writer
permissions and atomic outputs are checked. It is **not installed** and
has not been run against live protected financial data.

The Marimo process accepts the externally configured
`DASHBOARD_GUARDIAN_CAPTURE_ROOT` and opens only restricted, non-symlink,
owner-created captures. No dashboard process gets journal, broker
credentials, portfolio writer, HALT or sudo access.

## Source verification

```bash
uv run --frozen --extra dashboard --group dev pytest -q
uv run --frozen --extra dashboard --group dev ruff check .
uv run --frozen --extra dashboard --group dev marimo check src/copytrade_pm/dashboard/pages/*.py
uv run --frozen --extra dashboard --group dev copytrade-pm capabilities validate
uv build
```

Companion owning tests: `prop-production/tests/test_operator.py`,
`tests/test_guardian.py`, `tests/test_dashboard_capture.py`. Both
repository suites must be verified from their exact reviewed commits.
Synthetic fixtures prove source engineering, not installed finance or
scientific outcomes.

## Remaining independent release gates

Source PR review; reviewed pin compatibility; explicit authorization
to install a protected *read-only* producer; actual OS/group/ACL/path proof;
capture freshness and CPU/IO budget; immutable journal chain non-degradation;
real financial source/release/account evidence; authenticated browser/mobile
rendering and load/fault tests; signed service installation/rollback.
Missing verified real financial data stays UNKNOWN/UNAVAILABLE and does
not block independent source-only code tests.

Do not merge or deploy this phase without separate authorization.
Parent #153 and any incomplete issue acceptance remain open.
