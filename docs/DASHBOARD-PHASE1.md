# Phase 1 read-only trading oversight dashboard

**Scope:** Issues #154–#158, parent #153. Source-code implementation and local verification only. No production installation, brokerage execution or protected service changes.

## Authority

- Overview: Guardian status/risk/broker/portfolio only from separately owned restricted captures of the existing operator projection. No capture means UNAVAILABLE, not zero. Independent native operator commands are not an atomic account snapshot. Require matching release SHA and journal sequence before displaying finance. There is no dashboard journal reader.
- Wallets: native private SQLite read-only facade, bounded limit 1–100, offset 0–10000, alias/cohort/exclusion/as-of, independent SQLite doctor/inventory SHA. The underlying native view redacts addresses and reasons. Stale index age does not imply corrupt SQLite.
- Health: Guardian-reported observations, read-only public observer tapes and systemd process state. Active PID does not attest broker certainty or Guardian finance. There is no new alert service or detector.
- Research-selected portfolios are not deployed; neither a page load nor an observer receipt authorizes trading.

Financial fields retain exact Decimal text. Zero differs from missing. Source UTC, capture UTC, fetch UTC, release revision, inventory SHA and journal sequence are separately displayed. A UI refresh never creates fresh source evidence.

## Local-only verification

Run from a clean isolated checkout on Python 3.14:

1. uv sync --frozen --extra dashboard --group dev
2. uv run --frozen --extra dashboard --group dev pytest -q tests/test_dashboard_adapter.py tests/test_dashboard_security.py
3. uv run --frozen --extra dashboard --group dev marimo check src/copytrade_pm/dashboard/pages/overview.py src/copytrade_pm/dashboard/pages/registry.py src/copytrade_pm/dashboard/pages/health.py
4. uv run --frozen --extra dashboard --group dev ruff check src/copytrade_pm/dashboard tests/test_dashboard_adapter.py tests/test_dashboard_security.py

The optional ASGI entrypoint is copytrade_pm.dashboard.server:app. DASHBOARD_ACCESS_SECRET must be an externally supplied random string of 32–512 non-space characters. Bind uvicorn exclusively to 127.0.0.1, behind a trusted local TLS proxy; do not run editor/reload mode. Cookies are Secure, HttpOnly, SameSite=Strict, one-hour HMAC credentials. Loopback Host and Origin restrictions cover HTTP and WebSockets. Remote/Tailscale/Cloudflare reverse-proxy Host and Origin policy requires a separate security review. No listener was installed or launched by this work.

## Guardian capture preflight and explicit missing authority

The dashboard accepts fixed names status.json, risk.json, broker.json, portfolio.json and intent.json only. Capture directory and files must be owned by an identity different from the dashboard, have no group/world write bits, and reject symlinks. Captures must be regular files no larger than 128 KiB. The wrapper must declare schema dashboard_guardian_capture_v1, command, UTC source_observed_at, UTC captured_at and native. Native response must carry operator_COMMAND_v1 schema, nonnegative journal_sequence, account_binding_sha, release_sha and trading_authorized=false.

When an observation is older than 15s or capture older than 60s, status is STALE. Malformed, future, regressed, mismatched schema or inconsistent release/sequence is BLOCKED. Missing protected access is UNAVAILABLE. The dashboard does not create snapshots or weaken protected finance permissions to supply them. A separate authorized owner-provided capture producer is a future integration dependency; the current VPS protected Guardian journal must not be polled by each UI session.

## Future installation boundaries

Any future installed application needs a dedicated unprivileged OS user with read-only SQLite permissions; no protected journal, registry mutation, trading credentials, broker transport, sudo, deployment or signer access; CPU and memory limits; session and connection caps; independent authenticated private ingress; signed release pins; fresh broker and source evidence; a reversible rollback plan; Guardian no-degradation and dashboard kill/restart evidence. These controls are not claimed implemented or deployed.

The Phase 1 app has three views: account Overview, canonical Wallet Registry and System Health. Execution Monitor, full Risk Status, Portfolio Explorer, Performance and Research Lab execution remain later phases. No stop, continue, flatten, HALT/RECOVER or broker order actions exist in the application.
