# Protected Forward-Paper service preflight — 2026-11-04

**STATUS: BLOCKED. This is not a deployment or a grant of service authority.**

`copytrade-pm-paper-preflight --inspect-services` performs read-only inspection of a fixed allowlist with `systemctl --user show` **and separate system-level** `systemctl show` for P1/P14/watchdog protected units, not `start`, `stop`, `restart` or `daemon-reload`. It reports loaded/active states, configured User/Group and PID metadata without claiming independently verified process identity. This is in addition to the existing runtime path and privilege preflight. CLI results are a timestamp-specific inventory; they do **not** attest to future runtime continuity or root-level systemd units.

## Verified live VPS state

| Systemd user unit | Load | State |
| --- | --- | --- |
| `copytrade-tracker.service` | loaded | active |
| `copytrade-source-abc.service` | loaded | active |
| `copytrade-ensemble.service` | loaded | active |
| `copytrade-paper-p1.service` | not-found | inactive |
| `copytrade-paper-p14.service` | not-found | inactive |
| `copytrade-paper-watchdog.service` | not-found | inactive |

The new live system-level inventory likewise confirms all three `copytrade-paper-{p1,p14,watchdog}.service` units are `not-found`/`inactive`, with no configured protected OS user. Merely observing a loaded unit in future does not prove process identity or immutable release authority.

Preflight found the following unresolved issues:

- Coding identity `quant` (effective UID 1001) can modify the generic release and paper-state candidate paths. No separate protected financial service user has been established.
- Proposed release and financial state use the same OS identity; generic reports directory has group/world access (observed mode 775). This cannot be treated as protected financial state.
- sudo/docker privilege separation and protected service stop/start authority are not verified.
- No separately authorized protected cutover or rollback acceptance exists for FP PR #73.

The read-only preflight continues to report `status=BLOCKED`, `financial_data_mutated=false`, `systemd_units_mutated=false`, `cutover_performed=false`. A manually supplied flag cannot substitute for independent external signoff.

## Reproduction

```bash
uv run --group dev copytrade-pm-paper-preflight \
  --release-root /home/quant/.local/share/copytrade/releases \
  --state-root /home/quant/.local/share/copytrade/reports \
  --deployment-uid 1001 --state-uid 1001 --inspect-services
```

Next authorized release work requires dedicated operator-managed OS user/group roles, immutable release installation, private financial state outside coder-accessible trees, a signed/independent start/rollback gate, actual worker unit and independent watchdog identities, and adversarial systemd recovery tests. The current paper observer heartbeat contract deliberately remains `OBSERVER_ONLY_NO_TRADE` and `protected_worker_attested=false`. No background process or service cutover was initiated in this engineering session.
