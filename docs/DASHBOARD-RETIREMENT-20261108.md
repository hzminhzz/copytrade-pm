# Marimo dashboard retirement — 2026-11-08

**Issue:** [#192](https://github.com/hzminhzz/copytrade-pm/issues/192) (GRAF-12).
**Authorization:** explicit operator instruction to retire the Marimo operator UI.
**Scope:** operator presentation only. No SQLite, Guardian, broker, provider,
journal or research change.

## What changed

| Surface | Before | After |
|---|---|---|
| `copytrade-dashboard` user service | enabled, active | **disabled, inactive** |
| Tailscale HTTPS 8443 | `→ http://127.0.0.1:18777` | **route removed** (connection refused) |
| `src/copytrade_pm/dashboard/pages/` | 9 run-only notebooks | deleted |
| `server.py`, `navigation.py`, `views.py`, `phase2_views.py`, `release.py` | ASGI mount, hash routes, presentation helpers | deleted |
| `ops/dashboard-quant/` | install/activate/launch/acceptance tooling | deleted |
| `dashboard` extra | `marimo==0.24.0`, `altair>=6.0,<7` | removed |
| `chart_data.linked_chart` | Altair Vega-Lite brush | removed |

Tailscale HTTPS 8444 (Grafana) is unchanged and healthy.

## Preserved deliberately

Per #192, the domain-read contracts survive:

- `adapter.py` — `DashboardReader`, the native read owner the Grafana publisher calls.
- Registry, owner-capture and `dashboard_read_result_v1` validation semantics.
- `notifications.py` — notification evidence.
- `evidence_plane.py`, `grafana_projection.py`, `grafana_capabilities.py`, `grafana_acceptance.py`.
- `chart_data.prepare_series` — Polars point reduction used by `DashboardReader.history()`; only the Altair renderer was removed.
- Every dated `docs/DASHBOARD-*.md` record, unchanged, as historical evidence.

## Backup and rollback

Retained on the host, untouched:

- `/home/quant/.local/share/copytrade-dashboard/` — last known-good release including its venv.
- `/home/quant/.config/copytrade-dashboard/private.env`.
- `/home/quant/.config/systemd/user/copytrade-dashboard.service`.

Re-enable (requires the retired source, so restore the release from a pre-retirement
commit `bb5f51b` first):

```bash
git checkout bb5f51b -- src/copytrade_pm/dashboard ops/dashboard-quant
systemctl --user enable --now copytrade-dashboard
sudo tailscale serve --bg --https=8443 http://127.0.0.1:18777
```

## Verification

- Full suite: **1515 passed, 1 skipped** (was 1565/3; the delta is the deleted
  Marimo presentation tests).
- `https://…:8443/` → connection refused; `https://…:8444/api/health` → `database: ok`.
- Grafana acceptance still passes on obscura at 1280×800, 390×844 and 430×932.

## Explicit non-claims

Retirement is not Grafana acceptance. #190 stays OPEN and #191 stays blocked:
the Grafana stack is DEPLOYED_READ_ONLY, the synthetic fixture is still enabled,
authentic protected Guardian finance is not admitted, and installed rollback has
not been demonstrated. Nothing here changes trading, scientific or financial
authority.
