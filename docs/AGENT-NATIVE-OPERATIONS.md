# Appliance operations

Current operational interface. Use the installed canonical checkout at `/home/quant/dev/copytrade-pm`. The default persistent root is `~/.local/share/copytrade`; override it only with an explicit `--state-root`.

## Discover and inspect

```bash
.venv/bin/copytrade-pm capabilities list
.venv/bin/copytrade-pm capabilities show operations.appliance.status
.venv/bin/copytrade-pm capabilities validate
.venv/bin/copytrade-pm appliance status --json
```

Discovery inspects the actual pure argparse parser and a small reviewed effect catalog. It imports no providers, credentials or store writers. Unknown or retired routes fail catalog validation. Inspect leaf `--help` for required arguments; the catalog describes effects and never grants permission.

Status reports the checkout revision, lock pin, configured roots, observed worker PIDs/revisions, source scope coverage, quote freshness, paper financial cursors, roster integrity and explicit blockers. `HEALTHY` is an operational result. It does not authorize trading or qualify economics. `paper status` is the researched roster view; `appliance status` reports all configured operational portfolios.

## Reconcile and recover

```bash
.venv/bin/copytrade-pm appliance reconcile --json
.venv/bin/copytrade-pm appliance reconcile --apply --json
.venv/bin/copytrade-pm appliance recover --apply --json
.venv/bin/copytrade-pm appliance status --json
```

All mutation leaves default to dry run. Reconcile validates configuration, RosterStore integrity, checkpoint scope pins and existing signed paper bundles. Applied reconciliation updates native units and enables one target. Recovery restarts that target. Inspect `journalctl --user -u copytrade-pm-source -u copytrade-pm-paper -u copytrade-pm-quotes` for a reported worker failure.

The four role commands under `appliance run` are the systemd entry points. A process must match its configured revision and acquire each owner lease. Do not start a second process over active journals.

Source restart never backfills missed boundaries as fresh observations. The canonical journal records a gap and requires recovery baseline semantics. Paper restart recovers original source/financial cursors. An unavailable source is not an empty position; a fresh process is not a new financial account.

## Configuration

`appliance.json` is private (0600), inside a private root (0700). Its schema is `copytrade_appliance_v1`:

| Section | Required data |
| --- | --- |
| `sources.<name>` | Relative state root, selected portfolio IDs, checkpoint configuration path and SHA-256 |
| `papers.<name>` | Relative state root, source group, immutable run label, portfolio definitions and optional approval pin/public key |
| Portfolio definition | Folder, source member labels, initial balance, optional pinned observation-selection version |
| `quotes` | Relative journal root, instrument union, polling interval |
| `health` | Maximum wallet/deep-wallet counts, public request budget and UTC daily calendar |

The existing run label, folder, source policy, original selection seal and signed mandate must match existing journals. A configuration change cannot reset a journal or replace a signed fixed-k coefficient. Unsigned portfolios remain observation-only. A changed scope or financial policy requires the existing separately reviewed evidence workflow.

## Update software

Prepare and review a clean candidate in an isolated worktree. Run `scripts/ci.sh all` on its committed revision. Incorporate it into `origin/main`, then fetch main in the canonical checkout. Keep the canonical checkout clean.

```bash
.venv/bin/copytrade-pm appliance update \
  --candidate /absolute/candidate-checkout \
  --receipt /absolute/exact-sha-ci-receipt.json --json
.venv/bin/copytrade-pm appliance update \
  --candidate /absolute/candidate-checkout \
  --receipt /absolute/exact-sha-ci-receipt.json --apply --json
.venv/bin/copytrade-pm appliance status --json
```

The command checks the candidate's CI receipt and ancestry before stopping the target. It fast-forwards software and runs frozen uv sync. If activation fails, it restores the prior software revision and environment. The rollback leaves the canonical checkout detached at the prior revision for explicit inspection. It never rewinds financial journals. The operation receipt is under `runtime/update.json`.

Check observed process revisions and new owner receipts after an update. A successful git operation alone is not deployment verification.

## Phase D observation adoption

The historical default roster had an account declaration but no committed books or leases. Existing observations still depended on the retired wallet registry. Adoption imports authentic sealed observation memberships into RosterStore without pretending they are researched seat promotions.

```bash
.venv/bin/copytrade-pm appliance adopt \
  --registry-snapshot /absolute/quiescent/legacy.sqlite --sha256 ORIGINAL_SHA --json
.venv/bin/copytrade-pm appliance adopt \
  --registry-snapshot /absolute/quiescent/legacy.sqlite --sha256 ORIGINAL_SHA --apply --json
```

The source must be a pinned quiescent SQLite snapshot. Preserve originals and back up the destination first. Adoption is atomic and idempotent, retains origin clocks/seals, and records a new adoption clock. Schema 1 migrates additively; unknown schemas fail closed. Historical source paths and mandates retain their identities. Source-only adoption does not populate scorecards, k, seat leases or release bindings.

## Authority and historical obligations

Facts, researched roster changes and explicit release signing remain under their existing CLI groups. Signing requires the appropriate independently supplied evidence and key. No appliance command touches broker credentials, submits orders, signs mandates automatically or mutates independent Prop-Production accounts.

Ops Control Center, Site sync, dashboard containers, Prefect and independent worker release installations are permanently retired. Old rollout documents and preserved release archives are for forensic reproduction. The frozen forward assessment scheduled for 2026-12-02 remains pending and its original holdout restrictions remain binding; removing its timer is not completion.
