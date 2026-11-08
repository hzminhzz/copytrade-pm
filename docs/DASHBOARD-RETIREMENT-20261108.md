# Marimo operator dashboard retirement — 2026-11-08

**Issue:** [#192](https://github.com/hzminhzz/copytrade-pm/issues/192) (GRAF-12).
**Actual action:** an operator-directed, early retirement on 2026-11-08.
**Governance:** this action preceded #190 independent acceptance and #191 formally
approved cutover. The operator's retirement instruction is recorded; it does
**not** retroactively satisfy either prerequisite, demonstrate their evidence,
or close #192. Independent acceptance remains **NO_GO**. Review the explicit
out-of-sequence disposition before merging or claiming the GRAF-12 ticket complete.
**Scope:** only the operator presentation. No SQLite, Guardian, broker, provider,
journal, research contract or trading authorization changed.

## Installed state and preserved code

| Surface | Observed after retirement |
|---|---|
| `copytrade-dashboard` user service | disabled, inactive |
| Tailscale HTTPS 8443 | previous route absent |
| Tailscale HTTPS 8444 | Grafana read-only route present |
| `pages/`, `server.py`, `navigation.py`, `views.py`, `phase2_views.py`, `release.py` | deleted from current source |
| `ops/dashboard-quant/` | deleted from current source |
| `dashboard` extra | no Marimo or Altair requirement |
| `chart_data.linked_chart` | removed; `prepare_series` retained |

Preserved: `DashboardReader` in `adapter.py`, native registry and
owner-capture adapters, `notifications.py`, `evidence_plane.py`,
`grafana_projection.py`, `grafana_capabilities.py`,
`grafana_acceptance.py`, Polars point reduction in `chart_data.py`, and
the historical dated dashboard records. The Grafana publisher uses the native
read models, not the old Marimo presentation.

## Recovery from the retained installed wheel

The host retains a **separate installed** wheel and venv, not a live import
from a Git checkout:

- `/home/quant/.local/share/copytrade-dashboard/current` — observed symlink
  into `releases/b4989bbdc098-59ba035cabeb` on 2026-11-08.
- `/home/quant/.local/share/copytrade-dashboard/launch.sh`.
- `/home/quant/.config/systemd/user/copytrade-dashboard.service`.
- `/home/quant/.config/copytrade-dashboard/private.env` (mode 0600).

**Do not use `git checkout <old-sha> -- src/...` to restore this service.**
That changes the source worktree but not the installed wheel. Do not restore a
source checkout into `main` or overwrite another session's work. If the
installed wheel is missing or corrupted, use a separately reviewed offline
release rebuild, not a blind source reset.

Preflight as the `quant` user; stop and escalate if any test fails:

```bash
ROOT=/home/quant/.local/share/copytrade-dashboard
RELEASE=$(readlink -f "$ROOT/current")
case "$RELEASE" in "$ROOT"/releases/*) ;; *) exit 1 ;; esac
test -r "$RELEASE/dashboard.whl"
test -x "$RELEASE/venv/bin/python"
test -x "$ROOT/launch.sh"
test -r /home/quant/.config/copytrade-dashboard/private.env
test -r /home/quant/.config/systemd/user/copytrade-dashboard.service
test -r /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite
systemctl --user is-enabled copytrade-dashboard # expected: disabled
tailscale serve status # verify 8443 is unclaimed before restoring
```

Local read-only recovery probe (does **not** open tailnet ingress):

```bash
systemctl --user start copytrade-dashboard
systemctl --user is-active copytrade-dashboard
# Wait until localhost returns 403: SSO denies requests without owner proxy identity.
curl --max-time 5 --silent --output /dev/null --write-out '%{http_code}\n' \
  http://127.0.0.1:18777/
```

Expected direct-localhost result: **403**, not 200; a 200 would be an
authentication regression. A healthy systemd PID alone is not enough.
For an actual emergency restoration, separately authorize the ingress change
after verifying the exact Tailscale host and prior 8443 ownership:

```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:18777
tailscale serve status
# Test owner HTTPS 8443 and genuine non-owner denial.
```

Restore the retired state after the emergency: remove **only** the verified
8443 route using the installed Tailscale CLI, stop and disable the user service,
and reconfirm the 8444 Grafana route. Never reset all Serve routes, change the
8444 route or restart protected services. If 8443 is occupied or identity
denial cannot be proved, stop rather than overwrite another service.

### Verification boundary

On 2026-11-08 a bounded **local-only** recovery probe started the retained
wheel; it became active, served localhost **403** after four readiness polls,
and was stopped. The service was left **disabled and inactive**. Its first
two-second probe had not yet reached readiness, so readiness polling is required.

**Not yet demonstrated:** authenticated owner HTTPS 8443 access, real
non-owner denial, full ingress restore and reverse-cutover timing. These are
still required before calling the recovery route fully proven.

## Outstanding Grafana acceptance

Local Python tests and browser smoke checks do not close #190/#191. The
synthetic fixture is still enabled, authentic protected Guardian finance is
not admitted and every real financial cell remains `UNAVAILABLE`. The
independently approved release bundle, protected noninterference, and p95
target remain unresolved. The out-of-sequence retirement changes no trade,
risk, scientific or financial authority.
