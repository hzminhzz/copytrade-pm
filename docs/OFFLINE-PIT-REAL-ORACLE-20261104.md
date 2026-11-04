# Offline Polars 2.x real historical-oracle evidence — 2026-11-04

## Single-manifest engineering acceptance (owner-approved Option A)

The production-independent read-only public interface is
`python -m copytrade_pm.pm_offline_job` with
[the SHA-pinned HL94 historical-oracle job](OFFLINE-HL94-ORACLE-JOB-20261104.json).
A verified 90-day run emitted the immutable
`pm_offline_research_job_report_v1` result with report SHA
`3141e4acb2df842025f880403d9dd4be2702c6811917bcb7949546dbdc6cbd1a`:
`COMPLETE_HISTORICAL_ORACLE_SCREEN_ONLY`,
`engineering_path_verified=true`,
`financial_status=BLOCKED_MISSING_ATOMIC_BOOK_ASOF_NAV_AND_REAL_FIRST_KNOWN`,
`financial_certified_real=false`, `scientifically_qualified=false`.
This is engineering verification of source/market screening, **not**
real PM-03 contractual P&L.

A six-run warm-cache replay after the first report publication produced
exactly the same report SHA; measured wall seconds
`[1.552521,1.247195,0.987402,1.220082,1.059701,0.951829]`,
median `1.139892s`, largest sample `1.552521s`, single process
peak RSS `262508 KiB`. This is six opportunistic runs on a shared VPS,
not an established distributional p95, not a cold-disk trial and not an
old PM-01 financial-simulation speedup. Cache hit was sealed on the five
subsequent runs. The source/market status and missing evidence stayed
unchanged. See [engineering versus scientific qualification](OFFLINE-MILESTONE2-ENGINEERING-ACCEPTANCE-20261104.md).


**Scope:** read-only historical source normalization, per-fill delay batching and exact native Hyperliquid 1-minute **market-context screening**. This is **not** first-known receipt evidence, a verified full-account source book, real follower execution, PM-03 contractual P&L, scientific qualification, or authorization to trade. Related: [approved specification #78](https://github.com/hzminhzz/copytrade-pm/issues/78), [milestone #2](https://github.com/hzminhzz/copytrade-pm/milestone/2), [draft PR #92](https://github.com/hzminhzz/copytrade-pm/pull/92).

## Recovered original source directories (read-only)

The data used here are **ignored/private files** in the original repository checkout and canonical adjacent market-data repository, not files copied into the implementation worktree. Do not add original wallet/address JSON, Parquet, live secrets or aliases to Git. Study window: **2026-08-05T00:00:00Z to 2026-11-03T00:00:00Z, end exclusive** (90 UTC days).

| Source / contract | Observed count |
| --- | ---: |
| Local wallet fill JSON files: original / broader / Nansen | 19 / 55 / 20 (94 total) |
| Source raw fills across those files, including outside study | 500,168 |
| Fill rows outside frozen 90-day window | 34,341 |
| Inside study but not verified native perp scope (spot-style `@...`, unsupported DEX etc.) | 15,655 |
| Supported, uniquely keyed historical perpetual fill events inside study | **450,172** |
| Supported native instrument/DEX namespaces in studied fills | **216** |
| Local static `equity` scalar per source JSON | Present; **not a timestamped historical equity tape** |
| Independently evidenced local first-known event receipts in those files | **0** |
| Independent atomic initial whole-account books and complete source NAV as-of | **UNKNOWN / insufficient evidence** |

Original source file SHA-set digest (hash of sorted SHA-256s of exactly the 94 JSON byte streams):

`1deefe08279936770e896f0521664cf0ee1976bc0eecec78d5c615cb8799117d`

Several fills in directories labeled “90d” are older than the frozen window; the importer independently enforces the window. Spot-like `@107` and other invalid perpetual identifiers are excluded **with counts**, not silently mapped to existing perpetual instruments. A duplicate account/instrument/TID would be rejected from the tape. Any unverified source date, NAV or hedge state must remain UNKNOWN and must not be filled with a current equity value.

A later **30-run SHA-identical warm-cache** sample of the same public
90-day job on the shared VPS measured observed **wall p50 1.011240s**,
**nearest-rank p95 1.174315s**, mean 1.036187s, range
0.913131–1.250435s, process RSS high-water **278,556 KiB**.
User+system CPU p50 1.210000s, observed nearest-rank CPU p95
1.451843s. All 30/30 were cache hits with unchanged report SHA
`3141e4acb2df842025f880403d9dd4be2702c6811917bcb7949546dbdc6cbd1a`.
These are **empirical warm shared-host samples**, not a promised latency SLA,
independent cold-disk runs, or whole PM03 account simulator benchmark.

## Reproducible bounded 90-day benchmark (Issue #89)

The read-only `pm_offline_benchmark` CLI measures the **same sealed
historical-oracle research job** on a newly empty application cache and
repeats it without clearing OS page cache or source lake. Run:

```bash
uv run --extra market --group dev python -m copytrade_pm.pm_offline_benchmark \
  docs/OFFLINE-HL94-ORACLE-JOB-20261104.json \
  --input-root docs \
  --source-root /home/quant/dev/copytrade-pm/data \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --cache-root /home/quant/.cache/copytrade-polars-bench-20261104-verified-v1/cache \
  --workers 2 --repeats 10
```

Actual first-run independent-cache result (2026-11-04): **one
CACHE_CREATED + nine CACHE_HIT**, unchanged report SHA
`3141e4acb2df842025f880403d9dd4be2702c6811917bcb7949546dbdc6cbd1a`.

| Measure | Verified value |
| --- | ---: |
| First application-cache run (not OS cold disk) | 11.381831 s |
| Nine warm wall p50 / nearest-rank p95 | 0.951180 s / 1.042981 s |
| Nine warm CPU p50 / nearest-rank p95 | 1.120042 s / 1.338226 s |
| All 10 wall p50 / nearest-rank p95 | 0.959456 s / 11.381831 s |
| All 10 CPU p50 / nearest-rank p95 | 1.148770 s / 16.624076 s |
| Peak process RSS high-water (including first scan) | 835,596 KiB |
| Cache footprint after ten identical runs | 15,751,252 bytes |
| Linux physical-read counter first run / warm runs | 180,224 bytes / 0 bytes |
| Candidate batches / native matched batches | 377,130 / 322,970 |

`/proc/self/io` physical reads reflect the OS page cache, not all
logical bytes scanned. Polars scratch-file high-water is unmeasured
(`null` in reproducible report), not fictitiously zero. Comparison to
the **full 90-day PM-03 financial replay** is **BLOCKED_REAL_WORKLOAD**:
the original source supplies no independently as-of NAV/whole-account
snapshots/real first-known. The old PM-01 constant-price fixture uses a
different execution/financial policy; never claim a meaningful
end-to-end old/new financial simulation speedup.

The separately frozen source+native join stage was instead compared
on identical market batch inputs: unoptimized 75.50s versus optimized
5.20–8.12s (measured stage-only reduction; native Parquet output SHA
identical). All tests and performance work are **engineering screening**
and do not supply real follower P&L.

## Verified native market evidence

Canonical market root is the adjacent ML4T data lake under `crypto_futures_ohlcv_1m_HYPERLIQUID_*` daily Hive Parquet. Full verification reads **and hashes** each consumed `data.parquet` against the corresponding native `source.json`; it never substitutes the partial consolidated short candle files.

For the 216 historical-source instruments across the 90-day window (19,440 theoretical instrument-days):

| Market-day source status | Instrument-days |
| --- | ---: |
| SHA-verified complete native day, declared 1,440 bars | **6,985** |
| SHA checked but partial day, not sufficient for whole-day matching | 90 |
| Missing native source day | 12,365 |
| Native bars *declared by sidecars* | 10,182,527 |
| Native instrument scopes complete for all 90 days | **44 of 216** |

The source-only audit reports these counts without deriving missing prices, intrabar path order, funding or liquidity. A successful SHA check establishes only that local bytes match the source sidecar; it does not independently certify vendor correctness.

## Deterministic historical-oracle per-fill delay tape

`pm_offline_oracle` reads the original source JSON, keeps immutable SHA lineage, maps supported perp namespaces and compiles five delays **0 / 1 / 2 / 5 / 10 minutes**. For this labeled **retrospective oracle** study only, the source exchange event timestamp is treated as hypothetical knowledge; this is **not** a real local first-known receipt.

Each event has `eligible_ms = source_event_ms + delay_ms`. Its candidate action is the **strictly next minute open**, including if eligibility is exactly on the minute. Batching happens *after* each event becomes individually eligible, per account, native instrument and action minute. The full 90-day window produces **75,426 groups per delay** (377,130 grouped observations total), representing 450,172 fill observations at each delay. A uniform whole-minute delay changes the candidate minute but does not change which fills share a minute, except at right-censored boundaries; the observed full-window cohorts had zero right-censored fills at all five delays.

Source batch Parquet SHA-256 (full 5-delay tape, both Polars 2.1.0 streaming and in-memory):

`a035bc76357c55be3e451d899f32159ebdfeceedaa6164a51718f7060489e3ee`

Normalized batch logical SHA-256:

`333205f5478a5c8187e3886c682c24f9e565733ded8528217d3f6ada6815854c`

The first real-data test found different Parquet bytes due to Polars output chunk partitioning. A deterministic `.rechunk()` before serialization fixed this without changing row values. A 12,000-record regression also tests exact streaming/in-memory byte equality. Source JSON is now cached as an immutable normalized event tape as well as a hashed 5-delay batch tape.

## Exact native next-open and known-capacity matching

The real native-market compiler joins each batch on **exact UTC minute opening timestamp** with matching Hyperliquid instrument/DEX, and separately joins the **previous completed minute’s base volume**. Native future/current-bar realized volume, hypothetical L2 liquidity and “nearest price” lookups are explicitly prohibited.

Among all 377,130 5-delay batches, **322,970** match verified complete native days, exact opens and completed prior-minute volume. The other **54,160** remain explicitly unmatched (missing/partial days or unavailable prior-minute volume). Required instrument-day slices containing at least one candidate: 4,088; SHA-verified complete: 3,060; missing/partial: 1,028.

Full output Parquet SHA (unoptimized per-day join and optimized per-instrument join **identical**):

`b31302a223b47c69810c0e387bba7f1e4ebad5965c35ef7c0f5fc5b456e9820e`

Native matching logical SHA (both engines):

`242b624ea015975c2cbeda7efaa8946ae6456dcb7990ccb3582af1f7300fb59c`

The 3-market BTC/ETH/ZEC subset also has byte-identical outputs before and after optimization: 103,150 matched candidate batches across 267 independently SHA-verified complete market-days.

## Measured performance, resource headroom and limitations

**Host:** Python 3.14.6, Polars 2.1.0, 8 logical CPUs; initial shared VPS RAM 23 GiB with ~13 GiB available; root volume ~68 GiB free; swap already ~4.8 GiB occupied. No protected service restarts or source re-acquisition.

| Operation (same real input) | Observed wall / stage duration | Notes |
| --- | ---: | --- |
| Original real native one-day-at-a-time Polars join | **75.5007 s** join (76.574 s overall) | 377,130 batches, 216 markets |
| Optimized one-instrument-at-a-time vectorized join | **5.203–8.122 s** join (6.125–9.177 s overall) | Same output SHA; wall variation under shared VPS load |
| Optimized warm sealed context (2 runs) | **0.902 / 0.885 s** overall | Including SHA revalidation of native-day files |
| Normalized source+5-delay tape cold cache | **6.392 s** overall | 450,172 source fills |
| Normalized source+5-delay tape warm cache | **0.224 s** overall | File hashes checked; sealed source and batch tapes reused |
| Process maximum RSS: original native run / final optimized native run | **~807 / ~558 MiB** | Process high-water, not controlled per-stage allocation |

The observed **same-input market-join stage** improvement is approximately **9.3–14.5×** relative to the original day-at-a-time implementation, with byte-for-byte equality of cached output. This is **not an old PM-01 financial-simulator speedup**. First runs had cold *application* cache but the Linux disk cache was not cleared; CPU scheduling, IO caching and other jobs are uncontrolled. These are observed runs, **not** 90-day statistically sampled p50/p95 or unconditional performance guarantees.

Market Parquet generations differ in optional trade-count/quote-volume columns and UTC timestamp units (ms/us). The optimized scanner projects the seven common source-verified OHLCV fields, normalizes UTC time to microseconds and validates exact 1,440 bars and OHLC/volume constraints; genuinely irregular day inputs fall back to individually checked daily handling without assigning invented prices.

## Reproduce (read-only, with private sources configured)

From a clean isolated `copytrade-pm` worktree with local read permission for the original source and canonical ML4T lake, set:

```bash
RESEARCH_ROOT=/home/quant/dev/copytrade-pm/data
NATIVE_LAKE=/home/quant/dev/quant/ml4t-data/.data/store
PRIVATE_CACHE=/home/quant/.cache/copytrade-polars-oracle-dev-20261104
BEGIN=2026-08-05T00:00:00+00:00
END=2026-11-03T00:00:00+00:00

uv run --extra market --group dev python -m copytrade_pm.pm_offline_repository \
  --source-root "$RESEARCH_ROOT" --market-root "$NATIVE_LAKE" \
  --start "$BEGIN" --end "$END" --verify-market-sha

uv run --extra market --group dev python -m copytrade_pm.pm_offline_oracle \
  --source-root "$RESEARCH_ROOT" --cache-root "$PRIVATE_CACHE" \
  --start "$BEGIN" --end "$END" --engine streaming

uv run --extra market --group dev python -m copytrade_pm.pm_offline_oracle_market \
  --source-root "$RESEARCH_ROOT" --market-root "$NATIVE_LAKE" \
  --cache-root "$PRIVATE_CACHE" --start "$BEGIN" --end "$END"
```

All source inputs are read-only and original SHAs remain untouched. The private content-addressed cache is owner-only and refuses corrupted objects and low disk headroom; the per-run market scope is bounded at 6,000 unique instrument-days. No network API or broker is imported or called.

## Remaining **BLOCKED** acceptance

1. Historical vendor timestamps cannot be promoted to genuine independent first-known receipts. The 94 inspected files lack such observations.
2. Each file has one contemporary equity number, not an independently time-indexed source NAV and atomic all-DEX/subaccount opening book; cannot faithfully calculate follower relative sizing or gross exposure from those records.
3. **PM-03 real historical account replay and exact contractual PASS/BREACH remain UNKNOWN** until independently verifiable complete books, equity, contract, fee/funding and executable context exist. Tests and simulated fixtures do **not** fill these fields.
4. Native day coverage has material gaps. Real 216-market 90-day end-to-end follower simulation must fail closed on such gaps, not substitute different venues or zero market volume.
5. Scientific alpha/qualification, true prospective matched controls, and broker/trader authorizations are **not** established.
6. The original PM-01 36-wallet `pm01_fill_only_replay_v2`, PM-03/PM-04, registry ownership and Forward-Paper PR #73 non-resetting first-event 300-second policy are unchanged.

This evidence expands Issues #80–#85, #88–#90 with **real existing-source technical verification**, but it does not close the independent scientific/PM03 financial acceptance gates for milestone #2.
