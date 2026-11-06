# Guarded protected-paper operations — staged deployment (2026-11-05)

**Classification: ENGINEERING STAGED, NOT ROOT-INSTALLED, NOT FINANCIAL PAPER.**

This implements a deliberately non-financial standby worker for P1 and P14,
a separately running watchdog, a persistent fail-closed HALT record, and
SHA-pinned root-level systemd unit candidates. No component submits orders or
commits a PM-03/PM-04 financial transition. This is the operational safety
shell; it is **not** a substitute for the missing prospective source NAV,
authenticated Propr orderability, complete market capacity or admission.

## Current VPS limitation and independent authorities

- The interactive coding identity is `quant`, UID 1001, in `sudo` and
  `docker` groups. `sudo -n -l` requires interactive authentication.
  Group-based root-equivalent access must not be used to bypass the protected
  deployment boundary. Separate OS accounts and a root-owned, immutable
  release cannot be installed from this session.
- Protected system units `copytrade-paper-p1.service`,
  `copytrade-paper-p14.service` and `copytrade-paper-watchdog.service`
  are not installed. The existing `copytrade-public-observer-p1p14.service`
  is a **different**, quant-owned read-only observer; do not restart it
  as part of this operation.
- Wallet inventory and saved portfolios remain authoritative in private
  SQLite. Research selection `gemini.phase4/E6`/`E2` does not
  authorize P1/P14 financial paper. Query `copytrade-wallet-registry doctor`
  and `portfolio --current` before future cuts.
- This repository's dedicated protected units target **P1 and P14 only**.
  Adding E6/E2 is a separate portfolio-registration/admission change,
  not a silent alias switch.
- GitHub Actions issue #113 is an external billing-lock blocker to hosted
  required checks. Local tests do not satisfy GitHub branch protection.

## Native entry points

```bash
uv run --frozen --group dev copytrade-pm capabilities show paper.standby
uv run --frozen --group dev copytrade-pm capabilities show paper.unit_bundle
uv run --frozen --group dev copytrade-pm capabilities validate
```

- `copytrade-pm-paper-standby worker` emits a SHA-bound self-PID heartbeat
  with `paper_running=false`, `protected_worker_attested=false`,
  `order_route=NONE`, and `BLOCKED_NO_FINANCIAL_ADMISSION`.
  It has **no** account-execution code, broker transport or financial ledger write.
- `copytrade-pm-paper-standby watchdog` independently checks both PID start
  epochs, boot ID, revision, clock freshness and heartbeat SHA. It also verifies
  its **own previously recorded process epoch**. A watchdog restart, release
  revision change, corrupted prior status or missing HALT record latches
  `halt-latch.json`; a corrupt or group-writable HALT record refuses the
  monitoring cycle. HALT never automatically clears, including after recovery.
  `alert_required=true` flags the incident in the durable JSON and service
  logs; **no independent alert delivery channel is installed**.
  `feed_evidence_status=UNATTESTED_NO_INDEPENDENT_SOURCE_OR_MARKET` explicitly
  distinguishes standby liveness from feed, NAV and execution readiness.
- Strict mode requires fixed independent service-account names, root-owned
  exact-SHA release directory, code actually loaded from that release,
  owner-controlled private state and separated monitoring group permissions.
  `--unprotected-canary` exists **only** for explicit synthetic tests and is
  excluded from all generated protected service units. Even in strict mode the
  heartbeat does not attest financial readiness.
- `copytrade-pm-paper-unit-bundle` stages three deterministic system-level
  unit candidates, SHA manifests and permission checks. Its manifest explicitly
  denies installation, signed build provenance, rollback verification and
  trading authority. There is no `--apply` or privileged side effect.

## Verified offline staging procedure

From a clean, reviewed **commit** (never a dirty checkout), create an
owner-private directory outside the working tree and stage a new exclusive
candidate:

```bash
REV="$(git rev-parse HEAD)"
ROOT="$HOME/.local/share/copytrade/protected-paper-candidates"
install -d -m 0700 "$ROOT"
uv run --frozen --group dev copytrade-pm-paper-unit-bundle \
  --revision "$REV" --out "$ROOT/$REV"
uv run --frozen --group dev copytrade-pm-paper-unit-bundle \
  --verify --out "$ROOT/$REV"
systemd-analyze verify "$ROOT/$REV/"*.service
```

These commands **only stage and check**. They cannot create independent
`User=` identities or install `/etc/systemd/system` files. The unit
configuration includes exact release SHA paths, separate P1/P14/watchdog
users, `NoNewPrivileges`, `ProtectSystem=strict`, private devices,
bounded memory and tasks, and **all IP traffic denied**. This is intentional:
the standby workers do not need exchange connectivity.

## Privileged cutover (NOT performed here)

A legitimate OS administrator must, in this order:

1. Remove the coding identity's ability to modify protected data or access
   root through unrestricted sudo/docker; independently verify the security
   boundary. Preserve other production workloads.
2. Create managed accounts `copytrade-paper-p1`,
   `copytrade-paper-p14`, `copytrade-paper-watchdog` and monitoring
   group `copytrade-paper-monitor` (each service account distinct).
3. Install a separately checked, pinned build at
   `/opt/copytrade-paper/releases/<exact SHA>` with root ownership and
   no non-root write access. Verify the wheel's source/build provenance and
   module SHA. A user-staged unit manifest alone is **not** an attestation.
4. Create private owner-specific state directories:
   `/var/lib/copytrade-paper/monitor/p1` (P1:monitor, 0750),
   `/var/lib/copytrade-paper/monitor/p14` (P14:monitor, 0750), and
   `/var/lib/copytrade-paper/watchdog` (watchdog-only, 0700).
   The monitoring group may **read** P1/P14 heartbeat files (0640) but may
   not modify worker state. Actual financial journals must be in separate
   protected 0700 directories and must NOT share the monitoring directory.
5. Verify all three candidate unit SHAs, install as root-owned mode-0644
   system units, run `systemd-analyze verify`, `systemctl daemon-reload`,
   then start P1 and P14 **standby only** and verify their fresh heartbeats.
   Start watchdog last; inspect `halt-latch.json`, systemd MainPID and
   boot ID independently. Never enable unattended financial paper here.
6. Perform controlled worker/watchdog SIGKILL/restart and tamper tests; verify
   a new PID or watchdog restart latches HALT until an independent reset.
   Independently verify source/quote transport-feed freshness when a trusted
   protected data channel exists; **this standby code has no such channel**.
   Rehearse rollback to the prior
   separately trusted release. Record exact before/after unit hashes,
   release revision, worker identities, journal SHA, and rollback outcome.
7. **Do not activate any financial PM-03/PM-04 worker** until independent
   source-book/NAV, complete positions, Propr market identity, trade capacity,
   risk, trusted price, first-known receipts and financial-run admission pass.

A boot-time watchdog HALT is deliberately fail-closed. There is no automated
HALT reset or cutover in this package. A clean, manual watchdog restart can
therefore latch HALT as a **conservative** response to a changed process epoch.
The operator must resolve and verify the underlying reason before any future
separate, authorized reset procedure. Removing `halt-latch.json` manually
without independent authorization is not a supported recovery procedure.

## Verification and rollback boundaries

```bash
# Read-only checks that the non-privileged session can execute today:
systemctl show copytrade-paper-p1.service copytrade-paper-p14.service \
  copytrade-paper-watchdog.service -p LoadState -p ActiveState -p User -p MainPID
systemctl --user show copytrade-public-observer-p1p14.service \
  -p ActiveState -p MainPID
uv run --frozen --group dev copytrade-pm-paper-preflight \
  --release-root /home/quant/.local/share/copytrade/releases \
  --state-root /home/quant/.local/share/copytrade/reports \
  --deployment-uid 1001 --state-uid 1001 --inspect-services
```

Rollback must preserve immutable source receipts and SQLite financial
journals. Stop only the protected P1/P14/watchdog units; switch the three
pinned unit definitions to a previously verified release; validate and
start the **standby** services; audit the HALT latch before any other action.
No tracker, ensemble, A/B/C source observer or existing public observer
should be modified. A root-level rollback is **not verified** by an
unprivileged subprocess or an offline synthetic test.

See [pre-existing protected preflight](FORWARD-PAPER-PROTECTED-SERVICE-20261104.md),
[forward financial readiness](FORWARD-PAPER-READINESS-20261104.md) and
[observer-only service](FORWARD-PAPER-PUBLIC-OBSERVER-SERVICE-20261105.md).
