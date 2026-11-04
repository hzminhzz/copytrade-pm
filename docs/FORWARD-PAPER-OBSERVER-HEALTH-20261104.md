# Forward-paper observer heartbeat and protected-run gate — 2026-11-04

**Engineering-only / not a running service.** The local observer heartbeat and independent watchdog are implemented and tested, but a truthful `PAPER_RUNNING` admission remains blocked until a separately protected service identity, signed operation approval, verified provider feeds and real complete source equity are established.

## Attestation and identity

`pm_forward_heartbeat.publish_observer_heartbeat` is an explicit, locally invoked observer heartbeat producer. It seals its own Linux PID, UID, process field-22 start ticks, kernel boot ID, release SHA equal to the already sealed paper-run manifest, manifest SHA, journal cursor/head, and worker/transport/source/market times. It writes an atomic, 0600, fsync'd JSON record in an owner-private 0700 directory. It cannot accept a caller-supplied PID or create a broker order.

`pm_forward_heartbeat.inspect_observer_heartbeat` checks the actual `/proc` identity (PID reuse and reboot resistant), file permissions, canonical local SHA, run/release/account hashes and freshness of independent transport, source and quote observations. Missing file, tampering, changed financial head, stale markets, stale transport or restarted workers fail closed. A quiet wallet can have a healthy transport but no new trades; the two signals remain distinct.

The inspector is **not cryptographically signed**, the current agent's OS identity can modify these files, and no independent protected runtime is yet running. Therefore even when every observed timestamp is recent, health is at most **DEGRADED / OBSERVER_ONLY_NO_TRADE**, `paper_admitted=false`, `protected_worker_attested=false`, `order_route=NONE`. This prevents a manually passed PID from falsely promoting registry `PAPER_RUNNING`.

## Read-only CLI

```bash
uv run --group dev copytrade-pm-paper-watchdog \
  --db /path/to/owner-private/paper-events.sqlite3 \
  --heartbeat-root /path/to/owner-private/heartbeats \
  --run-id <sealed-run-id>
```

`copytrade-pm-paper-status --db ... --run-id ... --heartbeat-root ...` consumes that same independent observer report without elevating it to a protected worker. The read-only CLI avoids initializing the paper journal or creating SQLite/lock files.

**Outstanding FP-11/12 acceptance:** install separately authorized OS users for protected release and financial state, audited ability/inability of the coding user to control units, immutable service releases, independent watchdog unit/alert delivery, bounded process crash/restart and feed outage tests under that protected environment. No unit installation, restart, broker mutation, or live pilot was performed.
