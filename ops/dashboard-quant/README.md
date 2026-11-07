# Quant-owned private read-only dashboard deployment

The operator explicitly selected the existing `quant` UID for all quant work.
This is a conscious deviation from the earlier proposal to add a new Linux user.
It is NOT a claim of separate OS-user isolation. The verified, unprivileged
Bubblewrap mount namespace is the narrower security boundary.

## Release identity

The private owner-identity SSO release pins source commit
`b4989bbdc09847c09fe4c572fbae985fbeb8b543`, wheel SHA256
`59ba035cabeb55dc6c64e3c90ef28cdb704ce1afd44c6dc89a7cdc987099cc16`
and frozen `uv.lock` dependency hashes. Installed release directory:
`/home/quant/.local/share/copytrade-dashboard/releases/b4989bbdc098-59ba035cabeb`.
Previous password-mode release `29d006131662-aa94784c356f` remains intact
for dashboard-only rollback.

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
- The initial installation keeps the private password mode to permit a
  controlled cutover. To enable passwordless owner SSO in the deployed service
  run `sh ops/dashboard-quant/activate_tailnet_sso.sh` from the reviewed
  checkout. This pins the current Tailscale Serve owner's exact login in a
  private 0600 environment file, retains a private backup, restarts only the
  dashboard and verifies HTTPS root 200, login redirect 303 and direct
  localhost denial 403. Failed activation restores password mode.
- In owner-SSO mode, no viewer cookie or password is required on the
  authenticated tailnet URL. Requests from other Tailscale users, tagged
  devices (which lack user-login headers), malformed proxy headers or direct
  localhost without the headers are denied.
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

Tailscale Serve strips client-supplied identity headers and populates
`Tailscale-User-Login` for authenticated user-owned peers. Only the exact
pinned owner value is accepted with the existing loopback TLS proxy contract.
**Security boundary:** local processes sharing the `quant` OS account can
forge proxy headers when connecting to loopback. This does not authorize
order submission, broker credentials or Guardian journal access: the dashboard
remains read-only in a restricted Bubblewrap filesystem. The design is
appropriate only under the operator's trusted-quant-host assumption.
For stronger isolation, use a separate service UID / protected Unix socket or
a signed upstream identity proxy; never equate tailnet membership alone with
authorization.
