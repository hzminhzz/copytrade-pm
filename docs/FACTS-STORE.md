# Unified Fact Store (`copytrade_pm.facts`)

**Status:** IMPLEMENTED / ENGINEERING_VERIFIED (Slice 2, Phase D). No archive has
been migrated from this document; the migration is run locally by the operator.

This supersedes the write path of [the canonical wallet store](WALLET-STORE.md).
The wallet store remains readable as a legacy archive; it is no longer a writer.

---

## 1. Why

The wallet-first store wrote `wallet=0x…/year=YYYY/month=MM/day=DD/data.parquet`
— 19,261 files — and typed every money column as `Float64`. That combination
forced consumers to bypass the store: `trading-ops` globbed Reservoir prefixes
directly (`discover_fill_archive`), so it silently missed the feeds the glob did
not name, truncated decimal prices, and re-derived same-millisecond fill order at
read time from a non-monotonic `trade_id` (59,584 / 68,744 chain breaks in a
30-day window).

The fact store fixes the three at the storage boundary:

| Fault | Fix |
| --- | --- |
| `Float64` money | `Decimal(38, 12)` on every money column, in Parquet |
| ~50k tiny files / 250-wallet scans | one immutable batch per `(kind, day)`, `~200` files |
| read-time order repair | `arrival_seq` assigned once, at ingest |
| glob-driven discovery | SQLite manifest, no filesystem globbing |

## 2. Physical layout

```
<root>/<kind>/day=YYYY-MM-DD/<batch_sha16>.parquet    zstd, mode 600
<root>/facts.sqlite                                   manifest, mode 600
```

* `<kind>` is one of `fills`, `positions`, `equity`, `funding`, `ledger`, or `bars_1m`.
* `<batch_sha16>` is the first 16 hex of SHA-256 over the canonical Parquet
  payload, so identical content always resolves to the same path and a day batch
  is never rewritten.
* A day holds **exactly one** batch. Writing different content for a closed day
  replaces the batch and deletes the previous file; two competing batches for one
  day are unrepresentable.
* Rows are sorted by `(wallet, coin, event_ts_ms, source_rank, arrival_seq)` for
  `fills`, `(wallet, symbol, event_ts_ms, source_rank, arrival_seq)` for
  `positions`, and `(venue, coin, event_ts_ms, source_rank, arrival_seq)` for
  `bars_1m`, giving Parquet row-group statistics usable predicate pushdown.

## 3. Schemas

Canonical column sets live in `copytrade_pm/facts/schemas.py` and are the only
write contract.

`fills` (28 columns): `wallet`, `coin`, `dex`, `dex_raw`, `provider`, `side`,
`size`, `price`, `fee`, `fee_token`, `size_usd`, `start_position`, `closed_pnl`,
`trade_id`, `order_id`, `direction`, `is_liquidation`, `is_maker`, `crossed`,
`exchange_ts`, `event_ts_ms`, `source_ts`, `first_known_at_ms`, `known_at_basis`,
`arrival_seq`, `source_id`, `source_rank`, `batch_sha16`.

`positions` (27 columns) keeps the legacy wallet-store vocabulary plus the same
five provenance columns.

`equity` (14 columns), `funding` (14 columns), and `ledger` (13 columns) capture
official Hyperliquid account snapshots, funding payments, and ledger updates.

`bars_1m` (16 columns): `venue`, `coin`, `open`, `high`, `low`, `close`,
`volume`, `quote_volume_usd`, `bar_ts`, `event_ts_ms`, `first_known_at_ms`,
`known_at_basis`, `arrival_seq`, `source_id`, `source_rank`, `batch_sha16`.
Ingest enforces minute-grid alignment (`event_ts_ms % 60_000 == 0`), non-negative
`volume` and `quote_volume_usd`, non-empty `venue`/`coin`, and bi-temporal
causality (`first_known_at_ms >= event_ts_ms` across all kinds). `scan("bars_1m",
coins=...)` filters by coin and fails closed on `wallets=...`; `distinct_wallets()`
skips non-wallet kinds.

Money columns — `size`, `price`, `fee`, `size_usd`, `start_position`,
`closed_pnl` for fills; `size_token`, `size_usd`, `entry_price`, `mark_price`,
`liquidation_price`, `unrealized_pnl`, `leverage`, `margin_used`,
`liq_progress` for positions; `equity_usd`, `withdrawable_usd`,
`margin_used_usd` for equity; `payment_usd`, `funding_rate`, `size` for
funding; `amount_usd` for ledger; `open`, `high`, `low`, `close`, `volume`,
`quote_volume_usd` for `bars_1m` — are `Decimal(38, 12)`.

**Fields a source does not publish stay null.** They are never set to `0`,
`False`, or an interpolated price. `provider` is null for Reservoir rows because
the archive does not publish a provider; `price`/`fee` are null when a Reservoir
shard omits them.

### 3.1 Scale floor

`Decimal(38, 12)` cannot represent `|x| < 1e-12`; the cast truncates such a value
to zero. The migration counts those cells (`rows_quantized_to_zero` in the
receipt) instead of hiding them. On 2026-11-19 the highest-precision observed
envelope was sub-1e-9 prices, well inside scale 12.

### 3.2 Already-lossy Float64 sources

Reservoir and legacy wallet-store shards are `Float64`. The migration does **not**
try to recover a "true" decimal: it widens through the shortest round-trip
decimal representation of the stored float (`Decimal(str(float))`), so the value
written is exactly the value that was read. No binary→decimal rounding is
introduced and no precision is invented. `0.1 + 0.2` stays `0.300000000000`.

## 4. Bi-temporal contract

Two clocks, never conflated:

* `event_ts_ms` — when the fill happened (from the source).
* `first_known_at_ms` — when *we* first had the row, with `known_at_basis`
  recording how that was established.

| `known_at_basis` | Meaning | `ProvenanceTier` |
| --- | --- | --- |
| `partition_fetch_clock` | legacy wallet-store catalog `partitions.fetched_at` | `OBSERVED_FETCH` |
| `unrecorded` | no clock exists for the row | `RETROSPECTIVE` |

Reservoir archives record no fetch clock. Those rows therefore carry
`first_known_at_ms = NULL` and are **invisible** to `scan(as_of_ms=...)`; they are
never assigned an invented timestamp derived from the file or the window. A
caller that wants them must say so:

```python
facts.scan("fills", as_of_ms=as_of, allow_unknown_known_at=True)  # explicit, never default
```

`allow_unknown_known_at` admits unclocked rows but still excludes any row whose
*recorded* clock is later than `as_of` — opting in to "unknown" never overrides
an observed clock.

## 5. Intake-only order repair

`repair_same_ms_order` (`facts/repair.py`) runs exactly once per day rebuild,
after dedupe, on each `(wallet, coin)` chain:

* only same-millisecond bursts whose `start_position` continuity is broken are
  reordered;
* a burst with a missing `start_position` or an unknown side is left in arrival
  order and counted (`bursts_skipped_missing_start_position`) — never guessed;
* `arrival_seq` is then the chain ordinal and is stable forever after. Readers
  sort by `(wallet, coin, event_ts_ms, arrival_seq)` and never re-derive order.

`trade_id` is never used for ordering.

## 6. Manifest

`facts.sqlite` (see `facts/manifest.py`, stdlib only — importable by clients that
do not have Polars):

| table | holds |
| --- | --- |
| `datasets` | kind, schema version and schema SHA |
| `sources` | the five named sources with their fixed priority |
| `days` | one row per closed `(kind, day)`: batch id, rows, file SHA, **inputs fingerprint** |
| `batches` | batch id → path, bytes, SHA, contributing sources |
| `inputs` | per input file: relative path, content SHA, rows read / kept |
| `day_sources` | authoritative per-source reconciliation for each day |
| `runs` / `run_sources` | one row per migration run and its totals |

A day is the unit of idempotence: `days.inputs_fingerprint` is the SHA-256 of the
exact input set (relative path + content SHA + row count). Re-presenting the same
inputs is a no-op; presenting a different set rebuilds the whole day from **all**
recorded inputs, so the result never depends on migration history.

## 7. Migration

### 7.1 Sources and priority

Priority is fixed in `facts/sources.py`, not derived from CLI order:

| `source_id` | priority | layer | kinds |
| --- | --- | --- | --- |
| `wallet_store` | 0 | legacy partitions | `fills`, `positions` |
| `reservoir:full-history` | 1 | archive | `fills` |
| `reservoir:monitored-plus-six` | 2 | archive | `fills` |
| `reservoir:roster-daily` | 3 | archive | `fills` |
| `reservoir:liquid12-discovery` | 4 | archive | `fills` |

Discovery reads every `*.parquet` under a supplied root (sorted, excluding
`.metadata`). A source that yields no rows is listed in `sources_empty`; a
wallet-store kind directory that exists but is not ingested is listed in
`unmigrated_kinds`. Nothing disappears quietly.

### 7.2 Row accounting

Every read row lands in exactly one bucket, per source:

```
rows_read = rows_kept                     # written
          + rows_duplicate_within         # lost to the same source
          + rows_duplicate_cross          # lost to a higher-priority source
          + rows_null_key                 # no usable identity
          + rows_rejected                 # null wallet or null timestamp
```

`rows_conflicting_values` is an *of which* counter: a dropped duplicate whose
payload differs from the winner. It is inside one of the duplicate buckets and is
never added twice.

Dedupe identity:

* fills — `(wallet, coin, trade_id)` when `trade_id` is present, otherwise
  `(wallet, coin, event_ts_ms, side, size, price)`;
* positions — `(wallet, symbol, dex, event_ts_ms)`;
* bars_1m — `(venue, coin, event_ts_ms)`.

The highest-priority source wins; ties inside a source keep the earliest input
path and row. Every day is asserted before commit:

```
sum(rows_read) == sum(kept + dup_within + dup_cross + null_key + rejected)
sum(rows_kept) == rows in the day batch
```

A violation raises `ROW_ACCOUNTING_MISMATCH` / `WRITTEN_ROW_MISMATCH` and nothing
is committed.

## 8. Commands

All commands run from the `copytrade-pm` worktree root. Polars comes from the
`market` extra.

```bash
# 1. Dry run: reads every source, computes every batch id and row count,
#    writes nothing (no directory, no manifest row).
uv run --frozen --extra market copytrade-pm facts migrate \
    --store ~/.local/share/copytrade/facts \
    --wallet-store ~/dev/copytrade-pm/data/private/wallet_store \
    --reservoir full-history=~/.local/share/copytrade/research/reservoir-full-history-20261115 \
    --reservoir monitored-plus-six=~/.local/share/copytrade/research/reservoir-monitored-plus-six-20260701-20261111 \
    --reservoir roster-daily=~/.local/share/copytrade/research/reservoir-roster-daily-20261118 \
    --reservoir liquid12-discovery=~/.local/share/copytrade/research/liquid12-discovery-20261117 \
    --require-all-sources \
    --report /tmp/facts-migration-dry.json

# 2. Apply. Idempotent: re-running with the same inputs creates nothing.
uv run --frozen --extra market copytrade-pm facts migrate \
    <same arguments> --apply --report /tmp/facts-migration-receipt.json

# 3. Integrity: re-hash every batch against the manifest.
uv run --frozen --extra market copytrade-pm facts verify \
    --store ~/.local/share/copytrade/facts

# 4. Coverage per kind.
uv run --frozen --extra market copytrade-pm facts coverage \
    --store ~/.local/share/copytrade/facts

# 5. 250-wallet x 200-day cross-sectional scan benchmark. Without --store it
#    builds a synthetic store of that shape, so the command is reproducible
#    without private data.
uv run --frozen --extra market copytrade-pm facts benchmark \
    --wallets 250 --days 200
uv run --frozen --extra market copytrade-pm facts benchmark \
    --store ~/.local/share/copytrade/facts --wallets 250 --days 200
```

Slice 3 completed that cutover: `copytrade-pm` is the only installed console
script and `copytrade-pm facts migrate|verify|coverage|benchmark|capture-health`
is the supported invocation, with a catalog entry per leaf under
`operations.facts.*`. `python -m copytrade_pm.pm_facts_cli` still parses the same
four store verbs for unit `ExecStart` compatibility; it is not a separate
product surface.

`copytrade-pm facts capture-health` plans the capture without network or writes. With
`--apply`, it reads the roster and official Hyperliquid responses and writes
`equity`, `funding`, and `ledger` facts. Each row uses the response receive time
as its known-at clock. The command accepts an optional aggregate `--publish-dir`.
Use `--generation` for a private raw archive or `--no-raw-archive` for facts only.

The repository daily job uses the console command. Cut over the installed user
unit only after the candidate release and its roster configuration are approved.

### 8.1 Output discipline

Only aggregates are printed: source names, day counts, row counts, batch ids,
SHAs, timings. Wallet addresses are redacted to `<wallet>` at the print boundary
and `assert_aggregate_only` fails closed if one ever reaches it.

### 8.2 Exit codes

| code | meaning |
| --- | --- |
| 0 | reconciled; identities hold |
| 1 | `verify` found problems |
| 2 | a migration invariant or input error; nothing committed for the failing day |

## 9. Reading

```python
from copytrade_pm.facts import FactStore, ProvenanceTier

facts = FactStore("~/.local/share/copytrade/facts").expanduser()
slice_ = facts.scan(
    "fills",
    wallets=[...],
    start_day="2026-05-01",
    end_day="2026-11-14",
    as_of_ms=known_at_ms,
    tiers=(ProvenanceTier.OBSERVED_FETCH,),
)
frame = slice_.collect()          # polars DataFrame, Decimal columns
coverage = facts.coverage("fills")  # days present, missing days, tier rows
```

`FactSlice` also carries `files`, `manifest_rows` and `notes`
(`NO_PARTITIONS`, `UNKNOWN_KNOWN_AT_EXCLUDED`, `UNKNOWN_KNOWN_AT_INCLUDED`,
`MISSING_PARTITION_FILES:<n>`).

## 10. Boundaries

* `copytrade_pm.facts` never imports `roster`, scoring, paper risk or broker code.
* It owns raw facts only: no rollups, no per-wallet scores, no flats.
* The legacy wallet store's writer is retired: `wallet_store.store.ingest` refuses
  to write to the default live store root without an explicit opt-in, so no new
  wallet-first partition can appear. Reads (`scan`, `coverage`, `verify`) still
  work for the historical archive.
