# Grafana Phase 1 — One-way Operational Evidence Plane

**Current boundary:** read-only Grafana operator surface on HTTPS 8444. The original #180 staging contract covered tickets #181–184; the Marimo UI was later retired early under #192 despite #190/#191 remaining open. This is not formal cutover acceptance, trading authority, or authorization to change protected Guardian/broker services. See [the retirement record](../../docs/DASHBOARD-RETIREMENT-20261108.md).

## Contract

The independently timed publisher calls the existing DashboardReader and serializes seven bounded risk fields, source provenance, error codes, observation/capture/retrieval times, account-binding SHA, release revision and journal sequence. Exact Decimal strings are retained. The existing DashboardReader decides finance validity. Browser refresh never starts a native reader.

The publisher atomically replaces a checksum-validated file in a dedicated Docker volume. The projection gateway has that volume mounted read-only, contains only the evidence plane and presentation gateway code (no adapter or native readers), and exposes fixed GET-only account-risk and staging-only synthetic-fixture URLs with token authorization. Missing/corrupt data fails visibly, and a paused publisher makes previous VERIFIED evidence STALE without changing the numeric value or source clock. A SHA256 checksum detects corruption, not a malicious writer with filesystem authority.

The staging fixture is explicitly synthetic; it demonstrates VERIFIED, UNKNOWN, STALE, BLOCKED, UNAVAILABLE and exact zero. The real live-account view does not substitute synthetic finance.

## Isolated runtime

Publisher UID 10002: no network, output-only snapshot volume, no protected inputs mounted.

Projection UID 10001: internal data network, read-only snapshot volume, no database/journal files or native reader implementation.

Grafana 13.3.0 + Infinity 4.1.6: internal-only data and viewer networks with no default route; no exposed TCP listener. Infinity can query only the fixed projection origin. Grafana Viewer is a presentation identity, not a business authority.

Nginx: internal-only viewer network and a Unix socket under root-owned mode-0700 /run/copytrade-grafana-phase1. Tailscale Serve forwards HTTPS port 8444 to this socket only. Nginx validates the exact Tailscale owner login, HTTPS forwarded protocol, exact forwarded external Host and safe Origin. Tailscale Serve rewrites the internal Unix backend Host to localhost. Nginx strips and overwrites Grafana auth-proxy identity headers, and Grafana accepts auth-proxy headers only from the static ingress IP. At initial staging, Tailscale 8443 was untouched. The separately directed early Marimo retirement later removed the 8443 route; 8444 remains isolated. Full 8443 recovery has not been demonstrated.

**Trust limitation:** the host quant account belongs to the Docker group and consequently has root-equivalent authority. The Unix socket blocks unprivileged local spoofing, but not a malicious Docker/root administrator. This is a declared host trust boundary, not multi-tenant isolation.

## Reproduction

From this branch, use:

1. On an isolated disposable stack only, bash ops/grafana-phase1/stage.sh start. Do **not** repeat this command against the running owner ingress as an incidental smoke test.
2. Open the owner-only staging URL on HTTPS port 8444.
3. For local test: source the generated mode-0600 private environment at ~/.local/share/copytrade-grafana-phase1/private.env and run the browser_acceptance.py script with `uv run --frozen --extra source python` (the CDP client needs the source extra's pinned `websockets` dependency). It drives the local obscura CDP server (`systemctl --user start obscura`; `obscura serve --port 9222 --stealth --allow-private-network`), so the loopback and tailnet URLs are reachable.
4. bash ops/grafana-phase1/stage.sh stop

The stage script uses pinned Docker images and a minimal root-equivalent Docker helper to configure only the staging Unix-socket Tailscale Serve route. It does not need a sudo password. It must refuse to replace a preexisting 8444 route or untrusted socket directory. Teardown removes only the matching staging route, containers, evidence volume, socket directory and generated staging secrets.

## Verification

- Unit/HTTP tests: tests/test_grafana_projection.py and existing dashboard tests.
- Integration: real Grafana API query to fixed projection, synthetic grade timeline, Viewer-crafted arbitrary URL and method attacks.
- Browser: obscura CDP at real 1280x800, 390x844 and 430x932 CSS viewports; the two Risk Command dashboards, horizontal diagnostic scrolling on phones, and no document-level overflow. Private screenshots reside at /tmp/copytrade-grafana-phase1-qa/.
- Publisher pause: previously VERIFIED fixture zero becomes STALE; recovery updates only on new publication.
- Protected-service checks: exact PID and restart counts before/after, without opening protected financial journals. Independent protected finance cadence remains unverified.

**Do not commit private Tailscale owner identities, staging tokens, wallet addresses, account IDs, broker credentials or screenshots containing private finance.**
