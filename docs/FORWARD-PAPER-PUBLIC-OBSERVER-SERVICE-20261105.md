# Public P1/P14 observer-only user service — 2026-11-05

## Scope and evidence truth

This is an **unprivileged, public-data-only observation service**. It is
not either of the protected P1/P14 PM-03 financial workers and not a protected
watchdog. The service deliberately stays `paper_observed=false`,
`protected_worker_attested=false`, `source_nav_attested=false`,
`financial_events_committed=0`, and `order_route=NONE`.
`systemctl active` means only an OS process is running; the independent
observer heartbeat and sealed journal establish the limited public-evidence
health class `DEGRADED_OBSERVER_ONLY`, **never** `PAPER_RUNNING`.

An approved bounded canary (2026-11-05) captured five P1/P14 parent-account
public source receipts, first-known spot/vault diagnostics for each account,
and 24/25 SHA-chained native L2 market receipts. `para/ANSEM` remained
unaccepted. The observed open-instrument census was 12 P1 and 25 P14 at that
specific time; its changes do not imply revised sealed portfolio membership.
One bounded observer cycle returned `DEGRADED_OBSERVER_EVIDENCE`,
zero financial effects and zero broker orders. A separate initial transient
user systemd service `copytrade-public-observer-p1p14.service` was started
without modifying the tracker/ensemble/Source-ABC services. Its first
heartbeat was independently checked: process verified, five source tapes,
24 quote tapes and five collateral tapes, `DEGRADED_OBSERVER_ONLY`. This
is a dated observation, not verified 72-hour continuous coverage.

## Controlled, pinned user-unit installation

The new `copytrade-pm-public-observer-unit` supports dry-run by default
and explicit `--apply`. It verifies the exact active pinned registry release
using the **existing** release controller; checks the exact immutable SHA
directory, owner-private journal root, registry and address locator
availability; tests that public source/market dependencies are installed;
then proposes a 0600 user unit. The generated unit uses the explicit SHA
release path, not the mutable `current` symlink, and has tight CPU/memory
limits, restart-on-failure and `NoNewPrivileges`.

Run these commands only from the reviewed release containing this helper:

```bash
git -C /home/quant/dev/copytrade-pm fetch origin main
REV="$(git -C /home/quant/dev/copytrade-pm rev-parse origin/main)"
REG="$HOME/.local/share/copytrade/registry/release-control/current"
STATE="$HOME/.local/share/copytrade/prospective/p1p14-observer-20261105"

# Confirm that current really pins this revision (not only Git).
uv run --project "$REG" --offline --frozen --no-dev python \
  "$REG/scripts/registry_release.py" verify

uv run --project "$REG" --offline --frozen --no-dev \
  copytrade-pm-public-observer-unit \
  --revision "$REV" \
  --registry "$HOME/.local/share/copytrade/registry/wallet_registry.sqlite" \
  --primary-dir /home/quant/dev/copytrade-pm/data/wallet_fills_90d \
  --secondary-dir /home/quant/dev/copytrade-pm/data/nansen_smart_money_fills_90d \
  --state-root "$STATE"

# Only after the dry-run is VERIFIED and the exact unit SHA reviewed:
uv run --project "$REG" --offline --frozen --no-dev \
  copytrade-pm-public-observer-unit \
  --revision "$REV" \
  --registry "$HOME/.local/share/copytrade/registry/wallet_registry.sqlite" \
  --primary-dir /home/quant/dev/copytrade-pm/data/wallet_fills_90d \
  --secondary-dir /home/quant/dev/copytrade-pm/data/nansen_smart_money_fills_90d \
  --state-root "$STATE" --apply

# Stop *only* the old public-observer transient process before reloading.
systemctl --user stop copytrade-public-observer-p1p14.service
systemctl --user daemon-reload
systemctl --user enable --now copytrade-public-observer-p1p14.service
systemctl --user show copytrade-public-observer-p1p14.service \
  -p ActiveState -p MainPID -p NRestarts -p FragmentPath
```

If the active release does not match the requested SHA, the installer fails
closed. It never installs, starts, stops, reloads or enables systemd by
itself. The installer will not overwrite an existing unit or follow a
symlinked unit destination. It does not touch protected paper unit names.

**Engineering controls are not privileged isolation.** The observer and its
private tapes are writable by the `quant` coding identity; historical address
locator directories may be group writable and do not constitute signed source
or independent economic evidence. This deployment must never be cited as a
protected financial service signoff or a successful prop-firm paper run.

## Runtime observation and rollback

```bash
STATE="$HOME/.local/share/copytrade/prospective/p1p14-observer-20261105"
systemctl --user show copytrade-public-observer-p1p14.service \
  -p ActiveState -p MainPID -p NRestarts
journalctl --user -u copytrade-public-observer-p1p14.service -n 40 --no-pager
copytrade-pm-paper-observer-health --state-root "$STATE"
copytrade-pm --observer-state-root "$STATE" health

# Reversible public observer stop; no protected paper unit is touched.
systemctl --user disable --now copytrade-public-observer-p1p14.service
```

After any restart, the first complete new cycle must publish a new observer
heartbeat. A stale/missing heartbeat, stopped process, tape head divergence,
unexpected quote set or broker authority must return `UNKNOWN` or
`DEGRADED_OBSERVER_ONLY`, not `PAPER_RUNNING`. The finite source and quote
observations are time-staggered, and service restarts create an explicit
prospective coverage gap.

## Protected financial activation remains blocked

Read-only audit of the actual private P1/P14 journal reports:
`UNSEALED_FROZEN_MEMBER_WALLET_IDS`, incomplete parent/subaccount NAV,
unattested source equity/collateral and marks, unverified complete traded
volume, HIP-3 session limitations, and absent dedicated root-level paper
worker/watchdog OS identities. The protected cutover preflight also finds
sudo/docker separation and operator-signed release authority missing.
**Do not reduce validation, backdate aliases or mark source wallet NAV as
complete.** An unrelated public data observer cannot satisfy these gates.

Authoritative source: [P1/P14 readiness](FORWARD-PAPER-READINESS-20261104.md),
[shared observer](FORWARD-PAPER-SHARED-OBSERVER-20261104.md),
[protected service controls](FORWARD-PAPER-PROTECTED-SERVICE-20261104.md)
and [native agent operations](AGENT-NATIVE-OPERATIONS.md).
