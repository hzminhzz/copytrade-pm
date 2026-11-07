# Grafana-first Risk Command: Phase 1 staging evidence (2026-11-07)

## Scope and authority

This worktree implements a read-only, **non-production** Grafana staging slice of
#180 / #181–184. No broker/order/HALT/RECOVER operations or protected journal
paths are exposed. Existing `DashboardReader.overview()` continues to determine
finance coherence and evidence grades. A new fixed GET-only HTTP projection
serializes only the seven approved account-risk fields and redacted provenance;
the transport is not a new finance authority.

The projection reports `UNAVAILABLE` for owner finance when restricted captures
are absent; the POC does not mount protected records or reconstruct balances.
The example dashboard is not a trading monitor with independently qualified
account finance.

## Staging topology

- `grafana/grafana:13.3.0` (OSS; official image manifest confirmed) + pinned
  Infinity datasource `yesoreyeram-infinity-datasource` v4.1.6.
- Internal-only Docker `projection:17800` with no host published listener.
- Grafana is published only at `127.0.0.1:13070`; separate browser-facing
  Docker bridge is necessary for localhost forwarding. Its **outbound egress
  remains an unresolved #184 security boundary**.
- Infinity datasource has the explicit `http://projection:17800` allowed host,
  separate bearer credential, and read-only projection transport.
- Source code and Grafana config are versioned in `ops/grafana-phase1/`.
- No new PostgreSQL, Prometheus, Loki, React or frontend application.

## Verified staging observations

- Grafana OSS 13.3.0 / Infinity 4.1.6 images built and containers booted.
- Provisioned UID `copytrade-risk-command-v1` contains seven native panels (two status Stat panels, three evidence tables and two explanatory text panels).
- Real `/api/ds/query` returned seven source rows, with missing finance
  explicitly `UNAVAILABLE` and portfolio membership `UNKNOWN`.
- Unauthorized direct projection GET without the bearer token returned 403.
- Anonymous Grafana dashboard API GET returned 401.
- Viewer-shaped Infinity query to a non-allowlisted localhost internal admin
  URL failed with `requested URL not allowed`.
- Infinity POST to the allowed projection path failed 405.
- Firefox screenshots captured at actual CSS viewports 1280x800, 390x844,
  430x932 under `/tmp/copytrade-grafana-phase1-qa/`; document scroll width
  did not exceed viewport width in these runs.
- Targeted read-only adapter/projection regression: 39 tests passed;
  relevant Ruff check passed.
- Protected Guardian `MainPID=2518410`, `NRestarts=0` before/after the
  integration checks; Marimo `MainPID=3439459` remains active.
  These observations **do not** establish protected financial journal cadence.
- Tailscale Serve port 8443 remains mapped to 127.0.0.1:18777, untouched.

## Mandatory acceptance still blocked

1. #184 exact-owner Tailscale Serve SSO has **not** been installed or proven
   for Grafana. Local admin login is staging-only, not owner SSO.
2. Grafana OSS Viewer ability to submit datasource queries means direct
   dashboard visibility alone is not enough. A broad non-internal network
   interface is available to the Grafana container for the staging HTTP port;
   a separate reviewed egress/ingress policy is required.
3. A same-UID `quant` process can tamper with local HTTP identity headers;
   auth-proxy equivalence cannot be claimed without trusted separation.
4. The Guardian owner-capture producer remains unavailable; protected finance
   and independent journal health cannot be verified here.
5. The visual proof is a minimal table-driven first slice. The full requested
   professional stat/timeline risk hierarchy and synthetic five-grade
   panel demonstration are not yet engineering-verified.
6. No temporary owner-authenticated Tailscale route was added: existing Marimo
   ingress remains untouched.

## Reproduce or tear down safely

From this worktree, export two independent private 48+ character secrets as
`GRAFANA_ADMIN_PASSWORD` and `GRAFANA_PROJECTION_TOKEN`.
Run `docker compose -f ops/grafana-phase1/compose.yaml up -d --build`.
Do **not** reuse production credentials. For cleanup, run
`docker compose -f ops/grafana-phase1/compose.yaml down --remove-orphans`.
No Tailscale cleanup is needed because no Tailscale routes were changed.

## Handoff

Re-use `DashboardReader` -> fixed `/v1/account-risk` projection and the
`risk-projection-v1` datasource as the prototype vertical slice for Phase 2.
Do not infer finance from private registry or source wallet observations.
Before declaring #181–184 complete, add owner-scoped ingress, independent
egress and same-host threat tests, full visual acceptance, and confirm that
no protected services or private routes changed.
