# Track B daily read-only official health capture

This is **not** a portfolio/Guardian/PM03/PM04 policy service. It has no broker
credentials or order route. First verify the current SQLite registry as-of
identity, approved source/market budget, and pinned Git revision.

Deploy only into an owner-approved, SHA-pinned **new** release directory with a
private prebuilt venv; never execute a dirty checkout in a timer. Keep the
previous release and its immutable raw generations as rollback evidence. The
release symlink is `~/.local/share/copytrade-wallet-health/current`. The
user-unit file is `copytrade-wallet-health.service`; the timer runs once per
UTC day and does not change official selected-position subscriptions.

Raw captures stay under mode-0700
`~/.local/share/copytrade/health-research/g...`; every generation is create
once and preserves original response bytes, request/response SHA-256, clocks,
scope and explicit retrospective/uncertainty flags. The only Grafana input is
a **redacted** checksum-verified snapshot at
`~/.local/share/copytrade-grafana-health/wallet-health.json`. Never mount
the private raw generations into Grafana. This read-only collector does not
automatically delist or recover an account or increase/decrease k.

Verification: check actual timer and unit state, pinned source SHA and venv,
fresh immutable report SHA, provider request budget/response errors, no
private addresses in journal stdout, and the Grafana fixed GET endpoint. A
stale/partial capture means UNKNOWN, not financial health. For rollback disable
only this timer, revert the health release symlink to its previous pinned
version, and verify Grafana continues to display stale/missing evidence safely.
Leave original source and paper services untouched.
