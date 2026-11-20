# ADR 2026-11-19 — Unified bi-temporal fact store (Slice 2)

**Status:** accepted (Phase D, Slice 2). Code lives in `copytrade_pm.facts`; the
archive migration is run locally by the operator, not by this change.

**Supersedes:** the write path of the canonical wallet store (`wallet_store/store.py`).

## Context

`wallet_store` wrote one Hive partition per wallet per day
(`wallet=<addr>/year=/month=/day=/data.parquet`) with `Float64` money columns and
a SQLite catalog. Two consequences were measured in production:

* 19,261 files for 480 wallets, so a 250-wallet × 200-day scan touches thousands
  of tiny files and research bypassed the store entirely;
* `trading-ops` globbed Reservoir prefixes directly
  (`study_data.discover_fill_archive`). The globs named two of the four prefixes,
  so `reservoir-roster-daily` and `liquid12-discovery` were silently invisible,
  and wallet-store rows never entered a study at all.

Separately, `trade_id` is not monotonic inside a same-millisecond burst:
sorting by it broke 59,584 / 68,744 position-chain links in a 30-day window.
Order was being repaired at read time, per consumer, with different helpers.

## Decision

One writer, one layout, one clock model.

1. **Layout** `<root>/<kind>/day=YYYY-MM-DD/<batch_sha16>.parquet` plus a
   `facts.sqlite` manifest. One immutable batch per day; a batch name is its
   content identity (day + canonical Parquet payload), so identical content is
   never rewritten and a day cannot hold two batches.
2. **Precision** every money column is `Decimal(38, 12)`. No `Float64` write path
   exists in the package, and `write_day` casts to the canonical schema at the
   boundary so an adapter cannot drift the Parquet contract.
3. **Ordering** `repair_same_ms_order` runs once, at ingest, on
   `start_position` continuity. `arrival_seq` is the chain ordinal and never
   changes afterwards. Readers sort, they do not repair.
4. **Clocks** two fields, never conflated: `event_ts_ms` (source) and
   `first_known_at_ms` + `known_at_basis` (our knowledge). `scan(as_of_ms=…)`
   returns only rows whose recorded clock is `<= as_of`; unclocked rows are
   invisible unless the caller opts in explicitly.
5. **Discovery** named sources with fixed priority, read through the manifest —
   no filesystem globbing in a consumer.
6. **Migration** idempotent per day, driven by an inputs fingerprint, with exact
   per-source row accounting and SHA reconciliation.

## Migration treatment of imperfect inputs

These are the cases the design did not settle; each is decided here and enforced
in code, and none of them is "fixed" by inventing data.

| Case | Treatment |
| --- | --- |
| No historical clock (all Reservoir shards) | `first_known_at_ms = NULL`, `known_at_basis = 'unrecorded'`, tier `RETROSPECTIVE`. Never derived from the file name, the window, or the ingest time. Invisible to `as_of` scans; counted in `CoverageReport.retrospective_rows`. |
| Legacy wallet-store rows | The catalog's per-partition `fetched_at` is real evidence: `first_known_at_ms = fetched_at`, basis `partition_fetch_clock`, tier `OBSERVED_FETCH`. A partition with no catalog row stays `unrecorded`. |
| Already-lossy `Float64` source values | Widened through the shortest round-trip decimal repr of the stored float. The value written is exactly the value read; no recovery is attempted and no precision is invented (`0.1+0.2` → `0.300000000000`). |
| `\|x\| < 1e-12` | `Decimal(38,12)` cannot represent it; the cast truncates to zero. Counted per source as `rows_quantized_to_zero` and reported in the receipt. Not silently zeroed. |
| Missing optional columns (`price`, `fee`, `direction`, `is_liquidation`, provider) | Stored as `NULL`. Never `0`, `False`, or an interpolated value. |
| Same fact in several sources | Highest-priority source wins; the loser is counted as `rows_duplicate_cross` and, if the payload differs, additionally as `rows_conflicting_values` (an "of which" counter, never a second bucket). |
| Same fact twice in one source | `rows_duplicate_within`. |
| No usable identity | `rows_null_key`; null wallet or null timestamp → `rows_rejected`. |
| A day whose inputs are all empty | Closed as an explicit zero-row batch, so "read and empty" is never confused with "absent". |
| A day with rows where every row is rejected | Fails closed (`NO_VALID_ROWS`); data would otherwise be lost. |

## Consequences

* Consumers (`trading-ops`) read `copytrade_pm.facts.manifest` — a stdlib-only
  module — and never glob. `discover_fill_archive` is deleted.
* Research over an unclocked archive cannot silently become point-in-time:
  `as_of` scans return nothing unless the caller asks for the unknown tier.
* The wallet-first writer is retired: `wallet_store.store.ingest` refuses to
  write into the default live store root without an explicit opt-in. Reads of the
  historical archive keep working.
* Studies that previously reached the archive by glob now depend on the migration
  having run. A missing day is a loud `MISSING_SOURCE_DAYS` failure, not a silent
  short window.
* Slice 3 (`roster`) and Slice 4 (`score_universe`/`run_kernel_backtest`) consume
  `FactStore.scan`; the fact package still imports neither.

## Rejected alternatives

* **Keep wallet-first partitions and add an index.** The file count, not the
  index, is the cost driver.
* **Sort by `trade_id`.** Non-monotonic within a millisecond; measured chain
  breakage above.
* **Repair order at read time.** It has already drifted between consumers and
  makes a scan's result depend on the caller.
* **Back-fill `first_known_at` from the ingest clock.** That would make every
  archive row look point-in-time at migration time and silently legitimise
  look-ahead bias.
* **Deduplicate by full row equality only.** Two sources publish the same trade
  with different optional fields; full-row equality would keep both and
  double-count position chains.
