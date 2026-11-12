# Private Site registry sync

## Authority and scope

The SQLite registry on VPS is the source of truth for wallet and portfolio metadata. The private Site at https://copytrade-ops-control-center.hoangminh-1007.chatgpt.site receives a bounded, signed, read-only projection in its own D1 database. D1 is a display cache; it must never be used to make trading decisions or write back to SQLite.

The publisher uses the native registry owner commands, verifies the registry doctor integrity state and the same inventory SHA across paginated wallet reads and the current portfolio selection, and never reads SQLite directly. Raw wallet addresses are not sent. Only non-address, uniquely evidence-bound aliases are included. Unresolved or ambiguous records remain counted as unresolved.

The Site keeps wallet eligibility and assessment pending, source equity unknown, edge decay unknown, and evidence unverified. Imported current portfolios remain candidates with prospective/unverified evidence. Historical portfolio archives are outside this sync. Neither a successful transfer nor a current selection establishes paper-running, scientific qualification, or trading authorization.

This Site is an evidence and handoff tracker. Grafana remains the live operator surface. This sync has no broker connection, trading endpoint, HALT control, emergency cut-risk action, force-stop, or force-close behavior.

## Transport and credentials

The VPS publisher sends a JSON snapshot over HTTPS to /api/ingest/registry. It signs the exact request body with HMAC-SHA256 and a five-minute timestamp. Site access is additionally restricted by the Site's service authorization header.

Keep these values out of Git:

- VPS file: /home/quant/.config/copytrade/site-registry-sync.env, mode 0600.
- COPYTRADE_SITE_ACCESS_TOKEN: Site service token, sent only to this Site.
- COPYTRADE_SITE_INGEST_SECRET: same HMAC key configured as the secret Site runtime variable REGISTRY_INGEST_SECRET.
- COPYTRADE_SITE_URL: private Site origin.

Rotate the VPS and Site HMAC values together, then deploy a Site version so the new runtime secret revision is active. Do not print either secret or add them to an environment template committed to the repository.

## Install and operate

Copy the checked-in user units into ~/.config/systemd/user/, then reload and enable the timer:

~~~sh
install -m 0644 ops/systemd/copytrade-site-registry-sync.service ~/.config/systemd/user/
install -m 0644 ops/systemd/copytrade-site-registry-sync.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now copytrade-site-registry-sync.timer
systemctl --user start copytrade-site-registry-sync.service
~~~

The timer runs once three minutes after boot and then every 15 minutes. The service has no restart loop; the next timer tick retries after an error. It emits a compact receipt with source freshness, inventory SHA, row counts and Site response. It does not log tokens, request bodies or raw addresses.

Check it with:

~~~sh
systemctl --user list-timers copytrade-site-registry-sync.timer
systemctl --user status copytrade-site-registry-sync.service --no-pager
journalctl --user -u copytrade-site-registry-sync.service -n 30 --no-pager
~~~

For a manual read-only validation, run uv run --frozen --group dev python scripts/site_registry_sync.py --dry-run from the repository. To send one snapshot manually, source the protected environment file in the same shell and omit --dry-run.

## Checkout pin and current deployment

The unit defaults to the stable checkout /home/quant/dev/copytrade-pm. During the initial review period, the publisher is installed from isolated worktree /home/quant/.devspace/worktrees/copytrade-pm-abc88639 on branch feat/site-registry-sync-20261110; a systemd user drop-in pins WorkingDirectory there until the code is merged. Keep that worktree until the service is switched to a reviewed merged revision. The main checkout is deliberately untouched.

The VPS timer only publishes registry evidence. It does not install, start, or modify any copytrade execution, paper-trading, Guardian, or Grafana process.

## Evidence and failure handling

A Site receipt distinguishes source observedAt from transport receivedAt. A recent receipt can still contain sourceStatus=STALE; transfer freshness never upgrades upstream evidence. The first accepted snapshot recorded:

- SQLite inventory SHA 6553b8b7a725474b73a3924fcce63c198e42656d8064c82144816240ca0a762d.
- 502 wallet records; 181 unique aliases displayed; 321 unresolved.
- Two current research-only selections, both retained as candidates.
- Wallet health, source equity and edge-decay pending/unknown; paper-running unknown; scientific qualification and trading authorization false.
- Upstream status stale, as of the source receipt timestamp, not current time.

Incomplete snapshots are not published as the current projection. If staging or commit fails after receipt creation, the last accepted rows remain visible and that receipt records the error. Failures before receipt creation appear in the VPS timer logs. D1 keeps the most recent ten accepted row snapshots and retains receipt history for audit.
