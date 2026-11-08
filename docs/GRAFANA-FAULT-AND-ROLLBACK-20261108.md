# Grafana fault matrix, rollback and performance — 2026-11-08

Evidence for #189 (reproducible release with rollback) and #190 (alert
transitions, performance). Isolated staging stack on Tailscale HTTPS 8444.
No protected service, Guardian, broker or registry state was touched.

## Alert transition matrix

Rules are file-provisioned from `ops/grafana-phase1/provisioning/alerting/operational.json`,
group `copytrade-operational-source-health`, interval 30s, all three with
`noDataState: Alerting` and `execErrState: Alerting`.

State read from `/api/prometheus/grafana/api/v1/rules` in an authenticated
owner browser session.

| Injected fault | `Evidence generation unavailable or stale` | `Account risk source incomplete` | `Operational capability incomplete` |
|---|---|---|---|
| Baseline (publisher live, age 8.8s) | inactive | inactive | inactive |
| Publisher stopped, evidence age 86.4s (> `max_age_seconds` 45) | **firing** | inactive | inactive |
| Publisher restarted, age 9.9s | inactive | inactive | inactive |
| Projection stopped (datasource error) | **firing / error** | **firing / error** | **firing / error** |
| Projection restarted | inactive / ok | inactive / ok | inactive / ok |

No transition produced a false-green state: a dead datasource raises all three
rules rather than reporting healthy.

While stale, the Risk Command dashboard showed `ACCOUNT EVIDENCE COVERAGE:
INCOMPLETE`, publication age `2.4 mins` then `3.4 mins` (threshold red), and the
finance rows stayed `UNAVAILABLE` with `PROTECTED_CAPTURE_UNAVAILABLE`.

## Release rollback

Installed release `~/.local/share/copytrade-grafana/current`, approved bundle
`aecf29bdbb6f8646a29b87c32f1e1be4dd1895ae29088e934626badd683bad65`.

1. Tampered one provisioned dashboard (structurally valid JSON, panel height
   changed) in the mounted release directory.
2. `release_verify.py --expected-bundle-sha256 <approved>` → **`UNAPPROVED_RELEASE_BUNDLE`**,
   fail closed. A structurally valid edit cannot self-admit.
3. Restored the file from the pinned release.
4. Re-ran the verifier → bundle SHA matches the approved value, `release_admitted: true`.
5. Re-ran browser acceptance → 6/6 route/viewport checks pass, no horizontal overflow.

## Performance

Cold render of the five dashboards at 1280×800, 390×844 and 430×932, measured by
`ops/grafana-phase1/browser_acceptance.py` across four runs on the live staging
stack:

| Run | p50 | p95 (nearest rank) |
|---|---|---|
| 1 | 4185 ms | 4368 ms |
| 2 | 4318 ms | 4502 ms |
| 3 | 3997 ms | 4208 ms |
| 4 | 4033 ms | 4432 ms |

**The provisional #180 target of p95 < 2 s is not met.** p95 sits at 4.2–4.5 s.
This is a measured finding, not a pass: either the target is revised or the
dashboards need fewer Infinity round-trips per load.

## Still unverified

- Authentic protected Guardian finance (the publisher has no protected capture,
  so every financial cell is `UNAVAILABLE`).
- Genuine non-owner Tailscale principal denial (#184) — deferred by operator
  decision.
- Protected Guardian journal continuity and reconciliation cadence during load.
- Independent visual review by a second reviewer.
- Installed bad-plugin / failed-start rollback (only bad-config was exercised).
