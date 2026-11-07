# Phase 3 read-only dashboard: engineering and release runbook

Parent: [#153](https://github.com/hzminhzz/copytrade-pm/issues/153). TD-11/12/13/14: [#164](https://github.com/hzminhzz/copytrade-pm/issues/164), [#165](https://github.com/hzminhzz/copytrade-pm/issues/165), [#166](https://github.com/hzminhzz/copytrade-pm/issues/166), [#167](https://github.com/hzminhzz/copytrade-pm/issues/167).

**Authority: source implementation and disposable staging only. Not production deployed; no trading authorization.** Guardian remains financial/risk authority; SQLite is canonical registry. No dashboard origin can invoke HALT/RECOVER, orders, registry writes, broker credentials, or privileged capture creation.

## TD-11: independent incident dry-run

`copytrade_pm.dashboard.notifications` consumes existing owner **status** captures using `DashboardReader().guardian("status")`. Only VERIFIED sources with valid binding, timestamps and allowlisted incident codes can create/rearm incidents. Stale/unavailable sources do not clear active incidents. It uses account-bound stable identity, bounded persistence, atomic publication, single-writer lock, controlled retry and restart recovery. State is separate from Guardian. Acknowledgment writes *only* notification delivery status, never Guardian HALT.

To exercise **isolated dry-run** in a disposable, private state directory with a synthetic/non-protected status provider, call `process_once(state_path, source, delivery=DryRunDelivery(), now=...)`. The CLI supports `python -m copytrade_pm.dashboard.notifications --state-file /PRIVATE/STAGING/notifications.json --once`; the directory must already exist, be private and owned by the process. Running the CLI against real owner capture is **not** authorized by this phase. Never start a production daemon with it by inference.

No authorized external notification destination or credential has been established. `external_delivery=NOT_CONFIGURED` at all times. `DRY_RUN_DELIVERED` means fake backend only, not email/Telegram/webhook delivery.

Dashboard reads optional `DASHBOARD_NOTIFICATION_STATE_FILE` without a write handle and shows status on Operations and Health. This path is operator-owned configuration, never a browser parameter. A missing or unreadable file is `NOT_CONFIGURED` / `BLOCKED` and cannot make Guardian healthy.

## TD-12: mobile and URL scope

All eight run-only Marimo views share visible compact responsive navigation. Query strings preserve strictly validated `portfolio=<namespace>/<id>@<version>` and `utc=24h|7d|30d|90d`. They are **navigation context only**; no new financial query or roster selection is performed from the URL. Other query parameters (including account IDs, wallet addresses, tokens, arbitrary UTC timestamps and duplicate scope keys) are dropped at the authenticated HTTP boundary. Routes canonicalize with trailing slashes; redirect does not pass unsafe query strings to Marimo. Critical cards wrap and explicitly label missing account exposure and pod health UNKNOWN.

Private Firefox smoke suite checks 390x844, 430x932 and 1280x800 viewport, actual sign-in/session, source-state labels, critical top-level overflow, navigation redaction and scope propagation. Desktop/mobile economic correctness is established only for available fixture/UNAVAILABLE states, not live protected finance.

## TD-13: integrated acceptance

Tests:
```sh
uv run --frozen --extra dashboard --group dev pytest -q
uv run --frozen --extra dashboard --group dev ruff check .
uv run --frozen --extra dashboard --group dev marimo check src/copytrade_pm/dashboard/pages/*.py
uv run --frozen --extra dashboard --group dev copytrade-pm capabilities validate
uv build
DASHBOARD_BROWSER_ARTIFACT_DIR=/tmp/dashboard-phase3-browser \
  uv run --with selenium --extra dashboard --group dev pytest -q \
    -W ignore::ResourceWarning \
    -W ignore::pytest.PytestUnraisableExceptionWarning \
    tests/test_dashboard_browser.py
```
The browser-only warning filters address Selenium/Firefox temporary-response teardown noise and **do not** suppress warnings in the full core suite. Captured screenshots must be genuine browser captures, not illustrations.

Source/fixture tests are distinct from an authenticated private-network acceptance, real financial capture, real broker PnL and owner-worker cadence tests. Missing permissions, release agreement or fresh financial evidence must stay UNKNOWN/BLOCKED. Protected services must never be stopped or restarted to generate a dashboard test.

Performance targets are overview p95 below 2 s, bounded SQLite wallet search p95 below 500 ms, and no degraded Guardian cadence. Only measured result sets may count as pass; synthetic timings are labeled synthetic. Genuine Guardian reconciliation cadence, private source access and browser-proxy topology remain unverified unless separately observed.

## TD-14: stage-only reproducible release

`copytrade_pm.dashboard.release.prepare` requires SHA40-pinned copytrade-pm, prop-production and trading-connector commits, SHA256-pinned wheel, an explicitly marked owner-private staging directory and 0700 permissions. It creates candidate files without installing or running a service. `verify` checks the artifact hash and contract. `select_staging` changes only the explicitly marked *disposable staging* pointer and returns its previous target for rollback. Failed selection leaves the previously chosen candidate intact. This is **not** a production installer.

Example staging workflow (operator substitutes exact Git commit IDs from reviewed GitHub and a throwaway wheel built with `uv build`):

```sh
mkdir -m 700 /tmp/dashboard-stage-private
touch /tmp/dashboard-stage-private/.dashboard-staging-only
# In Python, call prepare(Path('/tmp/dashboard-stage-private'), Path('<wheel>'),
# source_sha='<40-char>', guardian_sha='<40-char>', connector_sha='<40-char>').
# Select and verify only disposable candidates; reverse by selecting prior candidate ID.
```

Use `docs/dashboard-private.service.example` **only** as a reviewed configuration template. It is not installed or enabled. Run-only Marimo means `uvicorn copytrade_pm.dashboard.server:app`, no `marimo edit`, dev server or reload. An independent unprivileged `copytrade-dashboard` OS identity, immutable release root, read-only source/capture permissions, and **no** broker/Guardian/journal credentials are required. Dashboard and Guardian must not share restart dependencies, user/group privilege or writable paths. Dedicated notifier requires separate review, not bundling with dashboard.

Private access:
- Tailscale is preferred, but Tailscale process liveness **does not attest** policy, tailnet ACLs or HTTP/WS auth.
- App binds only `127.0.0.1`. An independently authenticated, approved local TLS reverse proxy must publish an exact allowed Host/Origin pair.
- `DASHBOARD_ACCESS_SECRET` must be private and at least 32 characters. `DASHBOARD_ALLOWED_HOSTS` and `DASHBOARD_ALLOWED_ORIGINS` must be configured together: e.g. DNS Host and HTTPS Origin with no wildcard. **Never store secrets in Git**. HTTP and WebSocket are both guarded by signed short-lived strict/secure/httponly cookies, Host allowlist and WebSocket Origin checks.
- Reverse proxy trust is not automatic; no blanket trust for forwarded headers or an unauthenticated Cloudflare ingress. Inspect actual Tailscale Serve/ACL/HTTPS configuration before deciding the host/origin allowlist.
- Do not activate `systemd`, point live symlinks, touch protected file ACLs or change installed Guardian revisions until an independent production deployment authorization and full rollback preflight.

## Operational preflight for a *future* separately authorized release

Record exact installed source/wheel/companion pins and deployed service UID; verify OS permissions, live protected capture owner/publication timestamp/binding/release/sequence, independent Guardian reconciliation cadence, source freshness, private ingress and both HTTP/WS auth. Record baseline Guardian/planner/broker/watchdog PID, uptime, journal sequence and protected release pointers **before** any permitted dashboard installation, then repeat after start/restart/failure/rollback. Use existing production operations runbooks to back up and recover separately; this dashboard release must never restart Guardian or broker. Revert only the isolated dashboard symlink and service (if later authorized); never mutate Guardian financial state. In this phase all protected operations are forbidden.

## Known blockers and release classification

External notifications are NOT_CONFIGURED; genuine Guardian capture exporter has not been installed; signed pod risk budgets and matched broker-position/fill economics are not supplied by dashboard source; independent Guardian p95/cadence under real load is NOT_VERIFIED; live ingress/ACL/private service UID are NOT_VERIFIED; production dashboard is NOT_DEPLOYED. None is a reason to grant the dashboard financial write permission or promote evidence grades.
