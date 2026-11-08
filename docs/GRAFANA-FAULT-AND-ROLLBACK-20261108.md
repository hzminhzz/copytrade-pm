# Grafana fault matrix, rollback and performance — 2026-11-08

Evidence for #189 (reproducible release with rollback) and #190 (alert
transitions, performance). Isolated staging stack on Tailscale HTTPS 8444.
No protected service, Guardian, broker or registry state was touched.

**These tests do not close #189 or #190.** The gaps that remain are listed at
the end, and two of them are mandatory gates.

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
| Grafana restarted (`docker compose restart grafana`) | inactive / ok | inactive / ok | inactive / ok |

Within the fault transitions actually exercised, no false-green state was
observed: the tested dead datasource raised all three rules. After the Grafana restart all three rules
re-evaluated to `inactive/ok` and the dashboards re-rendered.

While stale, Risk Command showed `ACCOUNT EVIDENCE COVERAGE: INCOMPLETE`,
publication age `2.4 mins` then `3.4 mins` (threshold red), and the finance rows
stayed `UNAVAILABLE` with `PROTECTED_CAPTURE_UNAVAILABLE`.

### NoData was not tested; valid gateway responses normally carry monitoring

`noDataState: Alerting` is configured. On both successful `read_generation`
and fail-closed `no_evidence` code paths, the gateway adds a numeric
`monitoring` object before returning a valid JSON response. This makes NoData
unlikely on those *successful HTTP response* paths. It does **not** guarantee
that the Infinity datasource always supplies a frame: plugin/schema changes,
empty frames, transport errors and HTTP failures remain distinct conditions.
The tested projection outage produced **error**, not NoData. There is no
independent NoData transition receipt; do not claim it is impossible.

## Release rollback

Three releases are installed under `~/.local/share/copytrade-grafana/releases/`.

| Step | Action | Observed |
|---|---|---|
| 1 | `current` → `153ae4f` (previous good), recreate grafana | Grafana healthy; Risk Command shows the **time picker** and coverage columns in alphabetical order — the pre-fix release is genuinely served |
| 2 | `current` → `96898de` (current), recreate grafana | Time picker hidden, `Coverage` before `Age seconds` — the fixed release is served again |

Rollback and forward restore both verified by observable dashboard differences,
not by container state alone.

### Bad-config provisioning failure

A candidate release with `dashboards/health.json` replaced by invalid JSON:

- Grafana **starts** and `/api/health` returns `database: ok`.
- Provisioning logs, every 15s:
  `failed to load dashboard from /etc/grafana/staging-dashboards/health.json error="invalid character 't' looking for beginning of object key string"`.
- The health dashboard route is unavailable; `risk-command` still loads.
- Restoring `current` to `96898de` and recreating grafana brings the health
  dashboard back.

Blast radius is one dashboard, not the stack.

### Bundle fingerprint — detection only, not admission

`release_verify.py` over the installed release yields bundle
`aecf29bdbb6f8646a29b87c32f1e1be4dd1895ae29088e934626badd683bad65`.
A structurally valid dashboard edit (one panel height changed) is rejected with
`UNAPPROVED_RELEASE_BUNDLE` when that value is passed as
`--expected-bundle-sha256`.

**That SHA was derived from the same installed bundle, so this proves tamper
detection, not independent admission.** #189 requires an independently approved
pin; that approval does not exist yet and this test does not substitute for it.

## Infinity column compatibility

The declared backend JSON column is `selector: value`, `text: Value`, but
in the installed Grafana 13.3.0 / Infinity 4.1.6 rendering the four risk
metric tables require an `A` alias to restore the displayed `Value` column.
The organize transform supports either `A` or `Value` at index 1, renaming
`A` only; structural tests and the live browser verify the displayed Value
header and diagnostic scroll. **Raw Infinity response field names were not
captured independently in the review.** A plugin upgrade must inspect raw
frame schemas and reject simultaneous `A`/`Value`, missing both fields, or
any changed mapping before accepting a new release. The alias is a bounded
compatibility shim, not a general parser invariant.

## Performance

| Harness | Coverage | Result |
|---|---|---|
| `browser_acceptance.py` | 2 dashboards × 3 viewports | p50 3.99–4.32 s, p95 4.21–4.50 s over four runs |
| `browser_phase2.py` | 5 dashboards × 3 viewports | 15/15 pass, no horizontal overflow |

**The provisional #180 target of p95 < 2 s is not met.** The earlier four
runs measured 4.2–4.5 s. In the independent 2026-11-08 review rerun after
restoring mobile diagnostic coverage, six browser loads measured p95 **6.65 s**
(nearest-rank). This is a small sample, not a performance regression estimate;
none of the measurements qualifies the provisional target.

## Gates that remain open

- **Independent approval of the release bundle SHA** — the admission test above is circular.
- **Authentic protected Guardian finance** — the publisher has no protected
  capture, so every financial cell is `UNAVAILABLE`.
- **Genuine non-owner Tailscale principal denial** (#184) — deferred by operator
  decision, not passed.
- **Protected Guardian journal continuity and reconciliation cadence** during
  load — not attempted.
- **Independent visual review** by a second reviewer — screenshots exist, no
  human signoff.
- **NoData transition** — not exercised; valid gateway responses contain monitoring, but missing Infinity frames and transport errors still need separate tests.
- **Bad-plugin rollback** — only bad config was exercised.
