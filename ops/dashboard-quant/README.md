# Quant-owned private read-only dashboard deployment

The operator explicitly selected the existing `quant` UID for all quant work.
This is a conscious deviation from the earlier proposal to add a new Linux user.
It is NOT a claim of separate OS-user isolation. The verified, unprivileged
Bubblewrap mount namespace is the narrower security boundary.

## Release identity

The reviewed HTTPS-capable installation pins package source commit
`a51d0a675f250350a565ce8d813882e134e86d40`, wheel SHA256
`cfaf2c4136f4705402bac7018ac469669136c9517a47890dee2918bbc964871f`,
and frozen `uv.lock` dependency hashes. Installed release directory:
`/home/quant/.local/share/copytrade-dashboard/releases/a51d0a675f2-cfaf2c4136f4`.
The preceding root-only candidate `307629eec3b9-e718faa6bf13` remains intact
for evidence, but does not admit Tailscale's legitimate HTTPS proxy headers.

`launch.sh` has no dependency on the protected six system services.
It binds only the approved package release and canonical SQLite registry file
read-only. Credentials, `~/dev`, the Guardian journal and systemd/dbus sockets
are absent inside the sandbox; protected finance must show UNKNOWN/UNAVAILABLE.

## Operator setup

- On a fresh host with no existing dashboard service, execute `install.sh`
  as `quant` with `DASHBOARD_TAILNET_HOST` set to the exact current tailnet
  hostname. For example:
  `DASHBOARD_TAILNET_HOST="$(tailscale status --json | jq -r '.Self.DNSName | rtrimstr(".")')" sh ops/dashboard-quant/install.sh`.
  The script refuses existing services/pointers/credentials. It installs the
  launcher with mode 0700, user service, and a private 0600 environment file
  containing a generated 64-character access secret and exact Host/Origin
  allowlists. Never commit or display that secret.
- Use `systemctl --user daemon-reload`, `enable --now`, `status`, and
  inspect `journalctl --user -u copytrade-dashboard.service` (no password
  is printed).
- Locally verify unauthenticated page 303 to `/login`, private API 401,
  valid Origin login cookie and authenticated view without exposing the
  service outside 127.0.0.1.
- Preserve existing Tailscale Serve routes. Add a separate tailnet-only HTTPS
  listener at port 8443 only after the local service is healthy. Check
  `tailscale serve status --json` before and after.
- Test authenticated HTTP, WebSocket and browser navigation through the HTTPS
  endpoint and verify rollback / original six protected service identities.

## Reversal

Stop or disable only `copytrade-dashboard.service`. Restore its prior `current`
release pointer if one existed; otherwise remove only the new pointer. Remove
only the new Tailscale 8443 handler (never `tailscale serve reset`).
Restart only the isolated dashboard unit. Do not restart Guardian/broker/planner/
observer/Bybit observer/watchdog or alter their journal/risk policies.

## Evidence limits

The user chose `quant`; host UID isolation from other `quant` projects is not
established. Source Guardian captures require a separately verified producer
with source-owned files, distinct UID, compatible release and measured scan cost;
never fabricate quant-owned captures to satisfy the reader.
No live trading, order routing, HALT or financial writes are authorized.
External incident delivery remains NOT_CONFIGURED.
