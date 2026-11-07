# Grafana Phase 1 staging (NOT production)

Pinned software: Grafana OSS 13.3.0 and Infinity 4.1.6.
Source of authority: `copytrade_pm.dashboard.adapter.DashboardReader`; the HTTP
layer only flattens an allowlisted account-risk snapshot.

## Run

Generate two independent random 48+ character secrets, then export
`GRAFANA_PROJECTION_TOKEN` and `GRAFANA_ADMIN_PASSWORD` in the shell
(without writing either to this repository). Run:

`docker compose -f ops/grafana-phase1/compose.yaml up -d --build`

Open `http://127.0.0.1:13070` from the VPS only.
Use `docker compose -f ops/grafana-phase1/compose.yaml down --remove-orphans`
to tear down. No production Marimo, Tailscale, Guardian, broker, planner,
SQLite, wallet journal or protected account is mounted or modified.

The prototype has **no owner-authenticated private ingress**. Browser testing
through localhost is not evidence for issue #184. Because Grafana OSS Viewers
can issue datasource queries, the pinned Infinity allowed-host configuration,
the internal Docker network and token-authenticated fixed GET-only projection
must all remain in place. An owner-scoped external ingress requires separate
end-to-end testing and a trust-boundary review.

The projection container intentionally has no canonical registry or Guardian
captures. Its observed status is UNAVAILABLE, not a simulated healthy account.
Live owner capture and host-process identity are not inferred from Docker.
