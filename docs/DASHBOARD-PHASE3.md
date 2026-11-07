# Phase 3 read-only dashboard: engineering and release runbook

Parent: [#153](https://github.com/hzminhzz/copytrade-pm/issues/153). TD-11/12/13/14: [#164](https://github.com/hzminhzz/copytrade-pm/issues/164), [#165](https://github.com/hzminhzz/copytrade-pm/issues/165), [#166](https://github.com/hzminhzz/copytrade-pm/issues/166), [#167](https://github.com/hzminhzz/copytrade-pm/issues/167).

**Historical Phase 3 source/staging scope, retained for provenance.** The later
operator-authorized `quant` deployment and its live acceptance/limitations are in
[the 2026-11-07 runtime receipt](DASHBOARD-QUANT-DEPLOYMENT-20261107.md).
Guardian remains financial/risk authority; SQLite is canonical registry. No dashboard origin can invoke HALT/RECOVER, orders, registry writes, broker credentials, or privileged capture creation.

## TD-11: independent incident dry-run

`copytrade_pm.dashboard.notifications` consumes existing owner **status** captures using `DashboardReader().guardian("status")`. Only VERIFIED sources with valid binding, timestamps and allowlisted incident codes can create/rearm incidents. Stale/unavailable sources do not clear active incidents. It uses account-bound stable identity, bounded persistence, atomic publication, single-writer lock, controlled retry and restart recovery. State is separate from Guardian. Acknowledgment writes *only* notification delivery status, never Guardian HALT.

To exercise **isolated dry-run** in a disposable, private state directory with a synthetic/non-protected status provider, call `process_once(state_path, source, delivery=DryRunDelivery(), now=...)`. The CLI supports `python -m copytrade_pm.dashboard.notifications --state-file /PRIVATE/STAGING/notifications.json --once`; the directory must already exist, be private and owned by the process. Activation against real owner capture requires current operator authorization and verified producer/reader permissions. Existing authorization still applies; source tests alone do not authorize activation.

No authorized external notification destination or credential has been established. `external_delivery=NOT_CONFIGURED` at all times. `DRY_RUN_DELIVERED` means fake backend only, not email/Telegram/webhook delivery.

Dashboard reads optional `DASHBOARD_NOTIFICATION_STATE_FILE` without a write handle and shows status on Operations and Health. This path is operator-owned configuration, never a browser parameter. A missing or unreadable file is `NOT_CONFIGURED` / `BLOCKED` and cannot make Guardian healthy.

## TD-12: mobile and URL scope

The approved architectural correction uses **one run-only Marimo ASGI app** at `src/copytrade_pm/dashboard/pages/dashboard.py`, not eight independently mounted notebook servers. One authenticated kernel owns `mo.routes()` with hash-based `#/...` routing. Eight existing view modules are embedded as lazy read-only presentation graphs, preserving their reactive refresh/query controls without executing unselected expensive reads. Navigation and route headings are owned by the single app shell; Guardian/SQLite and the bounded Evidence Gateway remain separate authorities.

Canonical links have form `/?utc=7d&portfolio=namespace%2Fid%40version#/health`: only validated `portfolio=<namespace>/<id>@<version>` and `utc=24h|7d|30d|90d` reach the app. They are **navigation context only**, not selection of a running account. Old URLs such as `/health?utc=7d` redirect to `/?utc=7d#/health` after allowlisted sanitization. All other parameters (including account IDs, wallet addresses, secrets, duplicate keys and arbitrary timestamps) are removed before Marimo receives the request. Fragments are browser-only and never used to select owner files, SQL or commands. Critical cards wrap and explicitly label missing account exposure and pod health UNKNOWN.

The regression suite exercises 390x844, 430x932 and 1280x800 Firefox viewports, every one of the eight routes, twenty repeated document sessions against a shared disposable server, URL-secret redaction, and real embedded registry-button reactivity. Missing protected financial evidence is represented as UNAVAILABLE/UNKNOWN; fixture and localhost results do not establish operational acceptance.

## TD-13: integrated acceptance

Tests:
```sh
uv run --frozen --group dev pytest -q
uv run --frozen --all-extras --group dev pytest -q
uv run --frozen --all-extras --group dev ruff format --check src tests
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
The browser-only warning filters address Selenium/Firefox temporary-response teardown noise and **do not** suppress warnings in the full core suite. Captured screenshots must be genuine browser captures, not illustrations. The authenticated ASGI middleware allows only two bounded run-only Marimo JSON POST endpoints, `/api/kernel/function_call` (selected lazy view rendering) and `/api/kernel/set_ui_element_value` (read-only filter/refresh events). Both require a valid signed viewer cookie and exact allowed Origin, plus bounded Content-Length and Content-Type. The middleware also enforces the actual streamed byte count, exact declared length and a five-second total body deadline; a declared short length cannot bypass the limit. Shell/Python execution, arbitrary kernel runs, file writes, broker routes and release changes remain denied; negative transport tests enforce this.

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

## Operational preflight for an authorized release

Record exact installed source/wheel/companion pins and deployed service UID; verify OS permissions, live protected capture owner/publication timestamp/binding/release/sequence, independent Guardian reconciliation cadence, source freshness, private ingress and both HTTP/WS auth. Record baseline Guardian/planner/broker/watchdog PID, uptime, journal sequence and protected release pointers **before** any permitted dashboard installation, then repeat after start/restart/failure/rollback. Use existing production operations runbooks to back up and recover separately; this dashboard release must never restart Guardian or broker. Revert only the isolated dashboard symlink and service (if later authorized); never mutate Guardian financial state. Current operator authorization determines permitted actions. Preserve the six financial services and complete every mandatory permission, isolation and rollback gate before installing the independent dashboard.

## Known blockers and release classification

Mandatory deployment gates are the dedicated service identity and OS permissions, private HTTP/WebSocket ingress, independently observed Guardian cadence/journal continuity, resource limits and actual dashboard-only rollback. Missing mandatory evidence blocks deployment. The final independent audit and exact issue disposition are in [the 2026-11-07 acceptance record](DASHBOARD-FINAL-AUDIT-20261107.md).

Optional limitations include external delivery `NOT_CONFIGURED`, absent signed pod budgets, unavailable broker-executed follower PnL and unsupported source history. Label each affected widget explicitly. These limitations do not block unrelated registry views or require reconstruction of financial evidence.

## Audit-enforced operating bounds

- Cache fills hold a per-key lock, with a 200 ms wait, rather than blocking unrelated cached evidence. Native reads permit two concurrent calls **per Python reader process**, with a 100 ms admission wait. Saturation returns UNKNOWN/STALE. Marimo sessions can use separate Python processes; the systemd service still needs a measured aggregate process/CPU/memory budget.
- Guardian and broker status cards carry their evidence state. Stale values are explicitly last observed; unavailable or blocked values are UNKNOWN. Systemd activity is a separate OS column; an active PID alone leaves financial health UNKNOWN.
- Notification resolution requires the same source account binding. A persistent monotonic incident sequence survives retention and restarts. State older than 120 seconds, missing its update clock or dated in the future is STALE; the normal notifier interval is 30 seconds. The retained incident cannot become a fresh observation merely because the UI refreshes.
- Financial chart reduction retains each bucket minimum/maximum and both sides of gaps/resets. If critical observations exceed the display budget, the chart becomes unavailable rather than discarding an extremum.
- Browser acceptance sets the actual CSS viewport through WebDriver BiDi and asserts `window.innerWidth` and `window.innerHeight`. Firefox outer-window dimensions alone are insufficient. All eight views are checked at each requested viewport. Research query buttons must fit their text in both dimensions; absence of page-level horizontal scrolling alone is insufficient.
- `python3 scripts/dashboard_runtime_probe.py` performs fixed, read-only process/release/heartbeat checks and reads at most 64 journal event identities when permitted. It never obtains credentials. Permission errors remain explicit. Journal metadata is not full hash-chain verification, and unchanged PIDs do not establish reconciliation progress.
- The owner producer verifies the full journal chain before publishing bounded captures. Measure the full read cost before choosing its independent publication cadence. Dashboard polling does not justify repeated full-chain scans.
