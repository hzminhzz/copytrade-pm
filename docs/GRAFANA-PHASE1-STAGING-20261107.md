# Grafana Phase 1 — Operational Evidence Plane acceptance, 2026-11-07

**Scope:** #180 parent, Phase 1 #181–#184, isolated staging only. No Phase 2, no Marimo cutover, no broker/Guardian risk/portfolio modification, no trading. This receipt supersedes the earlier draft-only staging notes; prior test observations are historical evidence rather than current production claims.

## Implemented architecture

Existing `DashboardReader.overview()` remains the validation/financial-authority seam. A bounded single-writer **publisher** (no network in staging) calls this interface every 15s, validates seven fixed metric fields and source grades, and atomically replaces one 32-KiB-maximum JSON generation in a private Docker volume. The generation retains exact Decimal text, source_observed/captured/retrieved clocks, account binding, release revision, journal sequence and explicit error codes. Files use exclusive no-follow temp creation, fsync, atomic replace, and SHA256 **integrity** validation. SHA256 is **not** an independent signature or protected financial attestation.

The independent **gateway** has only a read-only volume mount and contains no `DashboardReader`, private SQLite, broker gateway, journal, signer or native domain reader implementation. HTTP GET `/v1/account-risk` reads only the last published generation; staging-only GET `/v1/fixture-states` serves a conspicuously synthetic five-grade QA matrix. Unsupported paths, methods, queries, bodies or unauthorized Bearer tokens fail closed. A missing/corrupt publisher generation displays blocked/unavailable, and a stale source/publisher **downgrades verified evidence without converting its last-known Decimal text to zero or updating the source time**.

Grafana OSS **13.3.0** and Infinity **4.1.6** read the gateway through an allowlisted internal Docker origin using backend JSONata. Both Docker networks are internal-only with no default route, and no TCP socket is published. Grafana and native projection have no protected credential mounts. Grafana is a Viewer via exact-owner Tailscale Serve ingress and cannot execute risk/order/mutation commands. A separate nginx gateway checks exact owner login, TLS forwarded protocol, external Host, safe Origin and overwrites the Grafana auth-proxy identity header. The Unix backend socket is beneath a root-owned mode-0700 directory; **Tailscale HTTPS :8444 was temporary staging only, :8443 was never changed**.

The small numeric visual `evidence_code` is derived from already-validated status strings purely for Grafana's native Stat reducer. It cannot compute finance or authorize trades. A VERIFIED *report of HALTED* renders HALTED in the headline, rather than misleadingly rendering green VERIFIED. A VERIFIED *report of broker certainty UNKNOWN* renders UNKNOWN, not reconciled. The synthetic fixture explicitly shows HALTED, RECONCILED, decimal zero, VERIFIED, STALE, BLOCKED, UNKNOWN, and UNAVAILABLE; its State timeline uses Infinity's `timestamp` type, independently verified as a Grafana time field. Real source finance remains UNAVAILABLE.

## Pinned dependencies

- Grafana image: `grafana/grafana:13.3.0@sha256:488984b716c0862639f91a698adbe2862677a5a07bad42da5f03f3030883b205`
- Infinity plugin: `yesoreyeram-infinity-datasource` v4.1.6, installed and runtime-reported
- Python image: `python:3.14-slim@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d`
- nginx image: `nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de`
- Helper: `busybox:1.37@sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec`
- Grafana dashboards: file provisioning is the single version-control authority; no Git-Sync credential.

## Independent acceptance

- Whole repository all-extras pytest regression: **1,533 passed, 3 skipped**; focused dashboard/HTTP suite: **150 passed, 3 skipped**. Full Ruff lint, formatting of changed Python, diff validation, shell syntax and Compose config passed. Capability validation returned **VERIFIED (110 capabilities, zero errors)**. These counts are not protected-finance tests.
- Actual owner HTTPS `GET /api/user`: **200**, mapped Viewer identity `risk-observer`, not GrafanaAdmin. `/api/user/orgs` returned Viewer. Grafana `/api/admin/settings` and `/api/users`: **403**. Real HTTPS forged Origin: **403**. Client-injected owner/proxy identity headers are overwritten by Tailscale Serve as evidenced by continued binding to the actual owner.
- Direct non-owner/missing-login and wrong forwarded-host queries to the Unix socket returned **403**. Nonprivileged `quant` direct socket access denied. A second, separately authenticated tailnet non-owner peer was **not available** for a real peer-origin test. The deterministic owner-header denial and Tailscale's trusted injection were tested separately; do not claim an observed peer-origin denial.
- Actual Grafana Viewer `/api/ds/query` returned real missing-data rows. Infinity arbitrary internal admin host was rejected by allowedHosts; arbitrary file path, query and POST to the projection rejected. Grafana `/proc/net/route` contains **zero default routes**, both Docker networks `internal=true`, and the projection image lacks `adapter.py`.
- Real Firefox six route/viewport combinations: **1280x800**, **390x844**, **430x932**, each for risk + synthetic QA, all authenticated without a second password. Assertions waited for **actual displayed source rows and state headlines**, not just a Grafana shell. All six: no document horizontal overflow. The synthetic State timeline was also visually inspected after fixing Infinity's timestamp type. Source screenshots remain private under `/tmp/copytrade-grafana-phase1-qa/`. Synthetic-only screenshots safe for source review: `docs/assets/grafana-phase1-synthetic-{1280x800,390x844,430x932}.jpg`.
- Real Firefox data-ready render, six samples: **p50 3,361ms / p95 3,605ms** (nearest-rank); after a clean restart **p50 3,371ms / p95 3,687ms**. This is **above** the specification's provisional <2s UX target; carry it as a performance improvement target into #190 rather than report a fabricated pass.
- Publisher pause for >45s: the already validated synthetic decimal `"0"` remained `"0"`, grade changed VERIFIED→STALE; after unpausing and a new publisher cycle, grade returned VERIFIED. Source data was not recalculated by Grafana refresh.
- Grafana-only forced restart: private owner GET temporarily returned 502 twice then 200 after two bounded probes; existing Marimo route stayed unchanged.
- Measured container memory (point sample): Grafana ~323 MiB (limit 1GiB), projection ~23 MiB (128MiB), publisher ~22 MiB (256MiB), ingress ~8 MiB (128MiB).
- Systemd baseline versus post-test for **six protected units** (Guardian, planner, broker, observer, watchdog, Bybit observer): **all MainPID, NRestarts and ActiveState unchanged**. Existing Marimo `copytrade-dashboard.service` remained active with unchanged PID. **This does not prove protected journal hash-chain continuity or independent Guardian reconciliation cadence**; protected journal access was not expanded.

- Fresh start/stop acceptance passed twice. On the final clean run, the owner-only HTTPS 8444 route, four containers and two dashboards were recreated. Real security and six Firefox checks passed; subsequent teardown removed the temporary route, containers, networks, generated secrets, socket root and evidence volume. Only existing Marimo Serve HTTPS 8443 remained.

## Residual limitations

1. No independently owner-published Guardian financial snapshots are mounted or created. All real finance and actual live pod-budget fields remain explicitly **UNAVAILABLE**, not inferred.
2. No independent actual non-owner tailnet peer session was available; negative identity tests covered the exact proxy ingress with forged/absent headers. Keep any requirement for second-user empirical denial as **not verified**, rather than falsely passing it.
3. The host `quant` account belongs to `docker` and therefore has root-equivalent authority. The root-private Unix socket blocks normal unprivileged requests, but cannot protect against compromise of that trusted Docker/root administration identity. The accepted security model trusts this VPS administrator. Do not claim hardened isolation from host-root.
4. Render latency p95 3,605ms exceeded the provisional <2s target. Source HTTP and UI semantic correctness were verified, but additional performance tuning/acceptance belongs in #190.
5. No protected financial cadence proof, science or live trading authorization is implied by the Grafana POC. No production Grafana service or Tailscale route was installed.

## Reproduce and rollback

From this isolated feature branch:
```bash
bash ops/grafana-phase1/stage.sh start
set -a
. "$HOME/.local/share/copytrade-grafana-phase1/private.env"
set +a
uv run --frozen --extra dashboard --group dev python ops/grafana-phase1/security_acceptance.py
uv run --frozen --with selenium python ops/grafana-phase1/browser_acceptance.py
bash ops/grafana-phase1/stage.sh stop
```

The stage script creates only disposable containers, evidence volume, root-private Unix socket, separate ephemeral secrets, and *only* temporary HTTPS port 8444. Teardown is required to remove these staging resources and return to the prior Tailscale Serve state; it must not touch port 8443. Root-equivalent Tailscale API access uses the already-existing `quant` Docker administration permission, without reading or publishing any sudo password.

## Phase 2 handoff

The stable deep seam is `DashboardReader → atomic evidence generation → fixed read-only gateway → Infinity`. #185–#189 should add only bounded, authority-labeled publication capabilities behind the publisher, then Grafana-native panels. Neither the Viewer nor the gateway may initiate protected reads. Keep independent source-observed clocks, entry/binding/revision/sequence identity, source finance vs modeled research vs synthetic QA, explicit unknown states and no trading route. Phase 2 work requires a separate execution authorization; the user authorization covered Phase 1 only.
