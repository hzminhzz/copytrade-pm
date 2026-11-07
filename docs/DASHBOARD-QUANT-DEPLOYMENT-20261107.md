# Quant-owned private dashboard: deployment acceptance, 2026-11-07

## Disposition

**DEPLOYED_PRIVATE_UI, RUNNING_OBSERVED; V1 PROTECTED-FINANCE ACCEPTANCE NOT_VERIFIED.**
The user explicitly selected the existing `quant` Linux identity for the dashboard
instead of creating a new service account. The selected configuration uses a
Bubblewrap sandbox to restrict that process's filesystem visibility. It does
not provide independent UID isolation from other `quant` processes.

The previous [independent source audit](DASHBOARD-FINAL-AUDIT-20261107.md)
predates this deployment. Its earlier source and blocker receipts remain historical
evidence and were not retroactively changed.

## Installed artifact and isolation

| Contract | Current evidence |
| --- | --- |
| Operating identity | `quant` user-systemd, linger enabled |
| User unit | `copytrade-dashboard.service`, enabled, restart-on-failure |
| App bind | `127.0.0.1:18777` only |
| Private ingress | Existing tailnet TLS proxy, **dedicated port 8443**; previous port 443 handlers untouched |
| Source code build | `a51d0a675f250350a565ce8d813882e134e86d40`, with no broker/Guardian code changes |
| Wheel digest | `cfaf2c4136f4705402bac7018ac469669136c9517a47890dee2918bbc964871f` |
| Dependency resolution | Frozen `uv.lock` export; `uv pip sync --offline --require-hashes`; no editable source |
| Python | 3.14.4 installed release interpreter |
| Service resource limits | 50% of one CPU, 512 MiB RAM, 96 tasks, 256 file descriptors |
| Mounts | Python executable/runtime; pinned read-only wheel installation; **one** read-only canonical SQLite registry file; no `~/dev`, private env, Guardian journal, Docker socket or DBus socket inside Bubblewrap |
| Viewer secret | Private mode-0600 `quant` configuration file; not in Git or published issues |
| Owner-finance captures | Not configured; protected source remains inaccessible under `quant` |
| External notification recipients | `NOT_CONFIGURED` |

The user service uses `ops/dashboard-quant/launch.sh`; it is not bound to,
required by or part of any Guardian, broker, planner, observer or watchdog unit.
The outer `quant` identity still has the permissions of that OS user on the
host. The application itself has only the mounted read-only file and package
inside its Bubblewrap namespace. `--share-net` preserves the loopback listener;
this is **not** an independent network namespace or a guarantee that arbitrary
code in the app could not make outbound network connections.

Private hostname and viewer password are intentionally omitted from this
public repository record. The operator can use the private URL/credential
provided in their interactive session; all commands below derive the hostname
from the current node or private environment.

## Live acceptance

- Authenticated application served by the actual private HTTPS proxy; TLS
  validation passed without disabling certificate checks.
- `GET /login`: HTTP 200; unauthenticated `GET /`: HTTP 401.
- Valid login and secure/HttpOnly cookie work through HTTPS; forged Origin,
  forbidden kernel execution and unauthenticated WebSocket attempts are denied.
  Correct HTTPS/Tailscale Host echoes are admitted only from loopback.
- **Firefox passed all 24 actual route/viewport combinations**: eight views
  at each `390×844`, `430×932`, `1280×800`. Every view was authenticated,
  hash-based page navigation worked, no page-level horizontal overflow,
  and the source registry UI rendered an actual Inventory SHA.
- Genuine screenshots: **24** retained privately at
  `~/.local/share/copytrade-dashboard/qa/`, not uploaded to Git.
- Actual private browser route render timing:
  **p50 643.2 ms; p95 979.8 ms** across 24 routes (page load until title
  and view marker). This is not journal/capture or broker latency.
- During the final private Firefox run, the dashboard user-unit peak was observed
  at **180,383,744 bytes** (approximately 172.0 MiB), below 512 MiB.
  An earlier service incarnation reached 192,430,080 bytes, also below the cap.
- Dashboard-only `SIGKILL`: user-systemd automatically restarted the unit;
  the private HTTPS login recovered (status 200).
- Invalid release pointer: dashboard startup failed as expected. Its prior
  correct pointer was atomically restored; reset/restart returned HTTPS 200.
- The current installed release pointer remains
  `releases/a51d0a675f2-cfaf2c4136f4`.
- The entire six-protected-service PID/restart vector remained unchanged
  across dashboard installation, browser loading, SIGKILL, bad-start test
  and rollback. Their previously observed installed release remained
  `07551a9978ee9ff3c7412dd1eadd5413e17b8421`.

Tests of the ingressed source correction: **1,495 passed / 3 skipped**
in the all-extras suite; Ruff, formatting, nine Marimo notebooks and
110 native capabilities passed. New forwarded-host regression tests also passed.
Historical separate owner and connector tests are in the original audit;
no new owner/connector installation or trade was performed here.

## Remaining acceptance gates

- The protected Guardian heartbeat and account journal remain unreadable by
  this operator: `PermissionError` and `OperationalError`, respectively.
  Therefore **journal hash-chain continuity and genuine reconciliation cadence
  before/after dashboard activity are NOT_VERIFIED**. Unchanged PIDs alone
  cannot prove that data cadence was unaffected.
- No owner-authoritative capture producer was installed. Owner-finance, pod
  budgets and actual broker-executed follower PnL must remain explicitly
  unavailable. The live canonical wallet registry view is available.
- Detailed tailnet admin ACL policy was not inspected. Serve is tailnet-only;
  HTTPS, signed-cookie auth, Host/Origin and unauthorized WebSocket denial
  were verified at the real private endpoint.
- Same-UID execution permits host `quant` to inspect its own processes,
  unlike a dedicated dashboard service UID. This is the operator-authorized
  deviation; the restricted app mount namespace is verified, not equivalent.
- No scientific qualification, financial promotion, risk HALT or order
  execution is implied.

## Operator lifecycle and rollback

```bash
systemctl --user status copytrade-dashboard.service
systemctl --user restart copytrade-dashboard.service
systemctl --user stop copytrade-dashboard.service
# Only when retiring this private dashboard exposure:
tailscale serve --https=8443 off
```

Private viewer credentials remain at
`~/.config/copytrade-dashboard/private.env` (mode 0600).
The installed release and current pointer are under
`~/.local/share/copytrade-dashboard/`. The pre-correction package remains
as a non-current release snapshot; the currently verified version has
an automated dashboard-only failed-start rollback test.

This branch's `ops/dashboard-quant/` contains the launcher, user unit,
hash-checking install/activate scripts, live smoke tests and fault test. The
runbook prohibits modifying the six protected services or publishing the
private hostname/secret to GitHub.

## GitHub acceptance boundaries

Parent #153 and TD-13 #166 retain the original mandatory protected-journal
and independent reconciliation-cadence evidence gate. TD-12 #165 can
be evaluated against its completed live mobile/browser criteria. TD-14 #167
has actual private installation/rollback evidence; final closure depends on
reconciling its original prerequisite #166 and the explicit user-approved
`quant` identity exception. Keep each conclusion evidence-specific.
