# Track B daily read-only official health capture

This is **not** a portfolio/Guardian/PM03/PM04 policy service. It has no broker
credentials or order route. The job reads the roster read-only and the official
Hyperliquid read-only REST endpoints; it writes normalised facts and immutable
raw generations only.

## Job

`ops/wallet-health/daily.sh` runs the single installed console command:

```bash
copytrade-pm facts capture-health --apply \
    --roster-db ~/.local/share/copytrade/roster.sqlite \
    --store ~/.local/share/copytrade/facts \
    --generation ~/.local/share/copytrade/health-research/"g$(date -u +%Y%m%dT%H%M%SZ)-example" \
    --max-wallets 512 --deep-wallets 12 --weight-per-minute 600
```

Without `--apply` the command plans the capture and exits without network or
writes. Candidates are the active and unsettled draining wallets from the
committed roster book plus scored candidates; `--no-scored-candidates` observes
only the book, and `--facts-root` optionally unions wallets already present in a
fact store. `--publish-dir` is optional and, when given, writes an
aggregate-only snapshot that refuses to publish any wallet address.

Deploy only into an owner-approved, SHA-pinned **new** release directory with a
private prebuilt venv that contains the `copytrade-pm` console script; never
execute a dirty checkout in a timer. The roster database must already exist and
be approved for the release — the capture never creates or repairs it. Keep the
previous release and its immutable raw generations as rollback evidence. The
release symlink is `~/.local/share/copytrade-wallet-health/current`. The
user-unit file is `copytrade-wallet-health.service`; the timer runs once per UTC
day and does not change official selected-position subscriptions.

Raw captures stay under mode-0700
`~/.local/share/copytrade/health-research/g...`; every generation is create once
and preserves original response bytes, request/response SHA-256, clocks, scope
and explicit retrospective/uncertainty flags. Normalised `equity`, `funding` and
`ledger` rows go to the day-partitioned fact store, where each row's known-at
clock is the reply receive time. This read-only collector does not automatically
delist or recover an account or increase/decrease k.

The repository job no longer passes `--publish-dir`, so it does **not** refresh
`~/.local/share/copytrade-grafana-health/wallet-health.json`. A dashboard that
still reads that file shows stale evidence until an operator re-enables
`--publish-dir` against a directory with the required permissions. Never mount
the private raw generations into Grafana.

## Verify

1. Confirm the unit and timer state, the pinned release SHA and venv, then check
   that the pinned release checkout contains this `daily.sh`.
2. Run `copytrade-pm facts verify --store ~/.local/share/copytrade/facts` and
   `copytrade-pm facts coverage --store ~/.local/share/copytrade/facts`; the
   default kinds include `equity`, `funding` and `ledger`.
3. Check the fresh immutable report SHA, provider request budget and response
   errors, and that journal stdout carries no private addresses.

A stale/partial capture means UNKNOWN, not financial health.

## Installed unit note (deploy, not code)

The repository never rewrites an installed unit. `copytrade-wallet-health.service`
calls `daily.sh` from the release checkout, so it picks up this interface only
after the release symlink points at a candidate that contains it. A unit whose
`ExecStart` still runs `python -m copytrade_pm.wallet_health_official` with
`--db .../registry/wallet_registry.sqlite` uses the deleted pre-cutover interface
and will fail; repoint it at the console command above. The retired
`copytrade-registry-paper*` paper units reference the archived registry and are
not part of this job.

For rollback, disable only this timer, revert the health release symlink to its
previous pinned version, and verify any dashboard continues to display
stale/missing evidence safely. Leave original source and paper services
untouched.
