# Roster: seat leases, sticky reconciliation and daily unsigned proposals

**Role:** canonical owner of `copytrade_pm.roster` and the `copytrade-pm facts | research | roster | paper | release` command surface. This page describes the contract; it is not a live roster, a release, or a trading permission.

The roster replaces the static SQLite pod registry as the *decision* layer for who occupies a seat. It does not own research scoring (that is Slice 4 / `trading-ops`) and it does not own broker authority (that is Guardian in `prop-production`).

## Model

| Type | Meaning |
| --- | --- |
| `SeatSpec` | One logical seat: `seat_id`, `risk_unit_usd`, `max_cdar_share`. Occupancy is derived. |
| `SeatLease` | An occupied seat bound to exactly one owner generation. `owner = digest([account_id, mandate_id, generation])`, matching `SignedMandate.owner`. `baseline_required` is always `True` (Q14=A). |
| `SeatBook` | Frozen snapshot: occupied seats **and** `draining` owners in separate tuples, plus `policy_epoch` and a monotone `sequence`. `mode` is `ACTIVE` (all seats), `PARTIAL` (some), or `FLAT` (zero). |
| `DrainingOwner` | A retired owner whose open residuals are still managed by `KernelState`. Never re-seated, never inherits, never transfers positions (Q16/Q21). |
| `WalletScorecard` | Research verdict plus its evidence: account value, active fill days, 5m markout, participation, Euler CDaR, suggested k, cluster, copyable drift, and an explicit tuple of `GateFailure`s. |
| `BenchCandidate` | Portfolio-conditioned candidate: `suggested_k`, `marginal_cdar_share`, `cluster_id`, `cluster_distance`, and the exact `scorecard_sha` it was scored from. |
| `RosterCUSUMState` | Q12 memory: `s_neg`, `episodes_seen`, and a terminal `retired_latch` for its policy epoch. |
| `CooldownRecord` | Non-edge eviction window: `evicted_ms`, `last_failure_ms`, reason. |
| `OperatorVeto` | Human containment with an optional expiry and an explicit revocation clock. |

Two invariants are enforced by construction, not by convention:

1. An owner cannot be both leased and draining, and no seat may be leased to a draining owner.
2. A latched `CUSUM_KILL` is terminal inside its epoch. Only an explicit new policy epoch (`RosterStore.clear_epoch(new_epoch)`) resets it; a later episode never does.

## Reconciliation

`reconcile_roster(current=..., scorecard=..., bench=..., vetoes=..., policy=..., as_of=...)` is a pure function of recorded evidence:

* **Sticky incumbents.** A healthy incumbent keeps its seat even when the bench ranks a candidate higher.
* **Missing evidence never evicts.** A seat whose wallet has no scorecard is retained and reported as `SCORECARD_MISSING:<seat>`. Missing evidence is never coerced to zero or to `FLAT`.
* **Hard eviction.** `CUSUM_KILL`, `LOW_ACCOUNT_VALUE_LT_1K`, `NEGATIVE_5M_MARKOUT`, dormancy (`NO_ACTIVE_FILLS`) and an active `OPERATOR_VETO` retire the owner into `draining` and free the seat in the same plan.
* **Q14 promotion.** A freed seat immediately accepts the best eligible orthogonal candidate (`PROMOTE`, generation `+1`). With no eligible candidate the seat stays `VACANT`; a fully vacant book is `FLAT`.
* **Orthogonality and CDaR.** A candidate is refused when its cluster equals a seated cluster, its cluster distance is below the policy floor, its marginal CDaR exceeds that seat's `max_cdar_share`, it is vetoed or latched, its evidence SHA does not match the stored scorecard, or its copyable 5m drift is unproven.
* **Cooldown.** Wallets evicted for `LOW_ACCOUNT_VALUE_LT_1K` or dormancy are bench-eligible again only after a continuous 14-day cooldown *and* account value at or above the `$5,000` re-admission floor *and* active fills *and* proven copyable drift.
* **Idempotence.** With unchanged evidence and the same clock, `reconcile_roster` returns the current book unchanged (same SHA, no sequence bump), so committing the same plan twice writes nothing.

`plan.trading_authorized` is structurally `False`: reconciliation is research/paper state.

## Persistence

`RosterStore(path)` opens read-only; pass `create=True`/`writable=True` to write. `path` is normally `~/.local/share/copytrade/roster.sqlite`.

* `books`, `leases`, `policies` and `cusum_events` are append-only (UPDATE/DELETE abort triggers).
* `scorecards` are idempotent by content SHA; `bench` snapshots are keyed by `(account, as_of_ms)`.
* A settled draining owner is marked `settled_ms`, never deleted.
* `latest_scorecard(as_of=...)` merges CUSUM events at or before the cutoff and active vetoes into `failures`. Account-scoped reconciliation reads the policy epoch from the selected book.
* `inventory_sha()` hashes every authority row in a fixed order; `health()` and `verify()` are read-only reports.

## CLI

```bash
copytrade-pm facts    migrate|verify|coverage|benchmark|capture-health   # store, one implementation
copytrade-pm research scorecards                            # aggregate gate counts
copytrade-pm roster   register|show|plan|commit             # seats and the daily cycle
copytrade-pm roster   scorecard|bench|veto|cusum|proposal    # typed evidence
copytrade-pm paper    mandates --as-of ...                 # unsigned proposal view (order_route NONE)
copytrade-pm release  propose|sign|verify|export             # offline Ed25519 signing
```

`facts capture-health` reads the roster read-only (active seats, unsettled draining owners and scored candidates) and writes official `equity`/`funding`/`ledger` facts; see [fact store](FACTS-STORE.md). It never creates or repairs the roster.

Every write requires `--apply`; without it the command prints the plan it would perform and exits `0`. Wallet addresses are redacted to `wallet:<sha16>` unless `--identities` is passed.

### Daily unsigned proposal, then one offline signature

1. `release propose --store ... --account ... --out proposal.json --apply` builds the exact `portfolio_release_v2` body from the committed book plus the recorded release binding, stages it once per UTC day in `proposals`, and writes it `0600` `O_EXCL`.
2. `release sign --store ... --proposal proposal.json --reviewer-public reviewer.pub --source-observer-public observer.pub --release-signing-key key --out release.json --apply` verifies the staged proposal before opening the key. Apply requires a regular `0600` key and a new output in a private directory. Dry runs leave the key unopened. The signature uses the existing `production_manifest` format.
3. `release verify --envelope release.json --signer-public key.pub` re-verifies with `production_manifest.verify`.

If the staged body differs from the body derived from the current verified roster and release binding, signing returns `RELEASE_PROPOSAL_BODY_DRIFT` before opening the key. A change to the roster inventory pin can invalidate an already staged daily proposal.

The signing cadence is the settled Phase D decision: one batched `ReleaseProposal` per daily cycle, one offline signing command, no autonomous bench allowlist inside Guardian (`Q12=A`, `Q18=A`).

`release sign` gates `SYNTHETIC` and `PROSPECTIVE` proposals identically: the reviewer-signed `production_release_policy_v1` must cover the exact staged body and carry independent source-observer attestations whose `source_mode` matches the binding, and that check runs before any signing key is opened. A selection without that evidence returns `SELECTION_ATTESTATION_MISSING` and produces no signature. The current binding carries provenance hashes and scope parameters. A replacement lease with an overlapping predecessor still needs separately authorized mandate control.

## Boundaries

| Claim | Status from this page |
| --- | --- |
| Roster code and proofs in an edited worktree | `IMPLEMENTED` / `ENGINEERING_VERIFIED` (see `tests/test_roster.py`, `tests/test_roster_cli.py`) |
| Any deployed or scheduled roster run | Not established here |
| Paper or live authority | Not established; `trading_authorized` is always `False` |
| Registry (`wallet_registry.sqlite`) retirement | Complete in Slice 3: `wallet_registry*` modules and `pm_copy_mandate.py` are deleted; `pm_forward_continuous`, `dashboard/adapter.py`, and `facts capture-health` read `RosterStore` (`roster.sqlite`), and the legacy SQLite file is archived read-only (`0400`) |

The legacy SQLite registry remains archived read-only as historical evidence (`archive/legacy_wallet_registry_20261119.sqlite`). Nothing in code reads it at runtime.

## Related

* [Architecture](ARCHITECTURE.md)
* [Fact store](FACTS-STORE.md)
* [Wallet registry workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md) (current registry consumers)
* [ADR: unified bi-temporal fact store](decisions/2026-11-19-unified-bi-temporal-fact-store.md)
