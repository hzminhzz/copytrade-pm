# Grafana Phase 2 — isolated engineering receipt (2026-11-08)

Scope: parent #180, Phase 2 #185–#189. Source branch `feat/grafana-phase2-0811` from Phase 1 merged `f3343cdde77e793fed373d0b2d80d70ea867f24c`. No production Grafana release, trading commands, protected service changes, Marimo cutover or Tailscale 8443 modification.

## Architecture and actual evidence

- The original Phase 1 Risk Command still uses `grafana_account_risk_v1` published by `DashboardReader.overview()`. New `grafana_operational_capabilities_v1` is validated as a **strictly bounded optional** additive field in the same atomic generation (single writer, immutable publication, read-only gateway).
- Publisher-only reader calls: `portfolio_explorer(limit=25)`, `execution_monitor()`, `health()`, `wallets(limit=50)`. Independent failed sources publish typed unavailable rows; the gateway does not import the native adapter. Each capability has a fixed field/row allowlist. Browser variables cannot trigger native reads. Source and generation clocks remain independent; current freshness logic downgrades each capability independently.
- Pods view keeps research selection separate from **UNKNOWN deployed/running**, no fabricated signed fixed-k, exposure, budgets or finance.
- Execution view carries separate first-known, T+300s due, decision, intent, broker acceptance/fill and reconciliation clocks. Two intents against one market/decision become `MULTIPLE_ORDER_INTENTS` even if a single intent has multiple fills. No simulated broker fill is promoted to owner receipt.
- Health view distinguishes reported Guardian certainty, public observer, watchdog and OS liveness. Viewer alerts do not control Guardian HALT. Wallet Explorer publishes sanitized alias/cohort/exclusion and inventory identity only. No private address or unrestricted SQL in gateway.
- Native Grafana dashboards: `risk-command.json`, `portfolios.json`, `execution.json`, `health.json`, `wallets.json`. Synthetic QA remains separate and visibly labeled. File provisioning owns all dashboard definitions. No Git Sync credential or new database.
- Three Grafana-managed backend alerts are provisioned: generation fault, account-risk evidence fault, operational-evidence fault. No external contact point/delivery claim. Missing/error data are configured Alerting, not Normal.
- `ops/grafana-phase1/release_verify.py` generates deterministic SHA256 inventory over source/config/alert/dashboard artifacts; this is **not** an authority signature or proof of installed release.

## Verified runs

- Complete local `uv run --frozen --all-extras --group dev pytest -q`: **1,545 passed, 3 skipped** before final documentation/release-test addition. Current focused Phase 2+Phase 1 Grafana regression: **36 passed**.
- Ruff lint passed on new/modified files. Browser provisioning: **15 route/viewport checks** (five operator dashboards × 1280×800, 390×844, 430×932) after loading explicit failure-source states, with zero document-level horizontal overflow. Private screenshots: `/tmp/copytrade-grafana-phase2-qa/` on VPS. **Screenshots have not been independently visually examined through the current remote tool interface; cosmetic acceptance remains open.**
- Grafana OSS 13.3.0 / Infinity 4.1.6 disposable staging: source query for all four operational capabilities returned backend frames, with only bounded allowed rows. Grafana alert provisioning API returned three rules; Account-risk and Operational-evidence alerts entered active state independent of an open browser. Publisher pause >45s produced actual `generation_fault=1`, and publisher was unpaused; remaining source evidence was not recertified by browser refresh.
- Phase 1 owner HTTPS security acceptance exercised Viewer only, forbidden administrative endpoints, forbidden arbitrary Infinity host/path/query/method and internal-only container networking. Independent non-owner tailnet peer still unavailable.
- Protected service observation immediately before/after publisher-pause fault: Guardian, planner, broker, public observer, watchdog, Bybit observer unchanged MainPID, NRestarts and ActiveState. The existing `copytrade-dashboard.service` was **inactive both before and after**; no claim of Marimo service liveness. Tailscale Serve 8443 preserved. These are process observations, **not** protected journal/cadence proof.

## Known acceptance gaps — do not close tickets falsely

1. Staging's no-network publisher cannot access private canonical SQLite or owner-authenticated protected Guardian captures. The four screens render explicit `UNKNOWN`/`UNAVAILABLE`/source errors rather than actual research-wallet or pod finance. Production source integration must be separately authenticated and safely mounted/authorized; do not add journal access as a shortcut.
2. Execution UI has bounded causal rows, but broker acceptance is absent in the current owner stream. No assertion of actual follower single-order timing or fill economics.
3. Alert failure-mode synthetic test matrix and full bad-version **installed runtime rollback** remain outstanding. Offline invalid dashboard UID is detected by the release verifier; that's not an installed rollback.
4. No independent real non-owner Tailscale identity denial. #184 stays OPEN, so #189 cannot attain complete ticket acceptance.
5. Manual visual screenshot inspection and cold p95 performance acceptance remain outstanding under #190; no performance PASS.
6. No external notification delivery, protected journal continuity, financial scientific qualification or trading authorization.

## Reproduce without production changes

```bash
uv run --frozen --all-extras --group dev pytest -q
uv run --frozen --group dev ruff check .
uv run --frozen --group dev ruff format --check src/copytrade_pm/dashboard/evidence_plane.py src/copytrade_pm/dashboard/grafana_projection.py src/copytrade_pm/dashboard/grafana_capabilities.py tests/test_grafana_phase2.py tests/test_grafana_phase2_config.py ops/grafana-phase1/release_verify.py ops/grafana-phase1/browser_phase2.py
uv run --frozen python ops/grafana-phase1/release_verify.py
bash ops/grafana-phase1/stage.sh start
set -a; . "$HOME/.local/share/copytrade-grafana-phase1/private.env"; set +a
uv run --frozen --extra dashboard --group dev python ops/grafana-phase1/security_acceptance.py
uv run --frozen --extra source python ops/grafana-phase1/browser_phase2.py
bash ops/grafana-phase1/stage.sh stop
```

The staging script uses only temporary HTTPS 8444 and a root-private Unix socket, with pinned images and no protected financial mounts. Confirm 8444 is unused before starting. Stop removes only its own containers, temporary route, evidence volume and generated credentials.

Status: **SOURCE IMPLEMENTED, FOCUSED TESTS VERIFIED, DISPOSABLE STAGING DEMONSTRATED, NOT PRODUCTION DEPLOYED, NOT FULLY ACCEPTED**. Only close each ticket when its own mandatory acceptance conditions are actually proven.
