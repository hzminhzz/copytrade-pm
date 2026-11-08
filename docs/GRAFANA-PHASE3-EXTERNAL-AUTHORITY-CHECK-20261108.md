# Phase 3 external authority verification (2026-11-08)

## Read-only runtime observations

- The actual root/system `prop-production-guardian`, `planner`, `broker`, `watchdog`, `observer`, and `bybit-observer` services are active. This corrects the earlier erroneous inference based on unrelated `copytrade-*` system units. Guardian PID 2518410, Planner 2518411, Broker 2518409, Watchdog 1924920 at observation; broker reports `NRestarts=1`, others 0. These are liveness observations, **not financial proof**.
- `systemctl --user` confirms `copytrade-dashboard.service` is active and running under quant, PID 3439459. Marimo is retained.
- `/var/lib/prop-production/guardian/account.sqlite` cannot be inspected as the quant identity (`Permission denied`). No privileged read, journal mutation, or Guardian restart was attempted. Guardian journal continuity, reconciliation cadence, and authentic financial provenance remain UNKNOWN.
- Tailscale peers visible to the host all show `hzminhzz@` owner identity; there is no demonstrated independently authenticated non-owner identity. The negative authorization test remains UNKNOWN, not PASS. An invented header or second device belonging to the same owner is not an independent negative principal.
- Existing Grafana staging at HTTPS 8444 was removed after the previous verification. The existing Marimo HTTPS 8443 route was preserved.

## Acceptance controller defect fixed

A red test showed that the prior verifier admitted all gates with `PASS` even when every receipt omitted its issuer. The verifier now requires a non-empty issuer and rejects `dashboard_under_test` issuer; missing issuer yields UNKNOWN and HOLD. This is still a consistency guard, **not a cryptographic proof of independent issuer identity**. A forged issuer string remains possible, so do not automatically promote based solely on this controller.

## Required remaining proof

Use an independently authenticated non-owner Tailscale principal for a real negative; use the protected owner-approved read-only Guardian status surface or privileged evidence export for journal continuity and financial provenance; run genuine alert NoData/Error/recovery, representative browser performance, visual inspection and installed rollback tests. Keep #190 open and #191 cutover blocked until all mandatory checks are evidenced. Do not substitute public PIDs, self-asserted JSON receipts or dashboard fixtures for protected evidence.
