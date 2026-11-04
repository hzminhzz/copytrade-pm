# Offline Polars 2.x source / market processing — engineering checkpoint

Date: 2026-11-04. This is **not** a completed research sweep, an exact
PM-03 account replay, independent PIT verification, or executable liquidity
certificate. See [baseline](OFFLINE-PIT-BASELINE-20261104.md) and
[specification #78](https://github.com/hzminhzz/copytrade-pm/issues/78).

## Implemented isolated processing components

| Component | Input contract / outputs | Remaining integration |
| --- | --- | --- |
| `pm_offline_manifest` | Manifest v1 bounded streaming SHA on source/market/rule/cost/risk files, explicit equity max-age, five delays, frozen stress/k/cost scenario IDs, typed INVALID/BLOCKED | Independently attested real source-file semantics, receipt lineage and real manifest-to-report facade |
| `pm_offline_source` | Atomic verified initial book, exact same-millisecond chain or typed ambiguity, strict all-DEX/account identities and as-of positive equity, stable digest | Independent signed source/receipt producer and source/equity snapshot adapter |
| `pm_offline_eligibility` | Polars 2.1 lazy strict next-bar, event-specific eligibility, stable streaming/in-memory hash, right-censor | Connect whole-book source tape; independently verified real receipt SHA and maturity |
| `pm_offline_market` | Native day Parquet SHA; exact namespace + minute join; prior completed bar volume; ex-post volume separate | Source market-day manifest reconciliation; resource-bounded hot partitions; full minute MTM; source calendar/session |
| `pm_offline_cache`, `pm_offline_derived_cache` | Owner-private fsynced immutable SHA objects, independently sealed source-book/equity and native fixture market panels, per-fill tapes and per-scenario outputs; source/market/cost dependency isolation, corrupt-object fail-closed and SIGKILL restart tests | Real 90d context is cached; original native source immutable |
| `pm_offline_hot_market` | Optional SHA-qualified native 7-day calendar week to compact 10,080-row little-endian numeric panel, owner-private immutable bytes, read-only OS memory map across processes, exact UTC open and prior completed base-volume lookup; missing/invalid day BLOCKED | Optional prewarm/worker read interface; Float64 data remains SCREEN_ONLY, never exact financial certification |
| `pm_offline_account` | Fixture-only sequential PM-03 Decimal Account, PM-03 classifier/execute_targets, source-equity sizing, frozen per-manager intents, explicit funding-complete assumption or UNKNOWN, minute marks, gross-before-net veto, exact first target/breach times and PM03 snapshot SHA | Real source/native bars/funding/contract receipts and multi-day persistent account/restart audit |
| `pm_offline_certification` | Synthetic PM-03 Decimal exact inclusive floor/target verdict; SCREEN_ONLY never PASS; censor/unfilled residual and missing source/rulebook evidence UNKNOWN/AMBIGUOUS | Real qualified source and executable cost/funding paths before any real financial verdict |
| `pm_offline_intents`, `pm_offline_receipts` | Causal whole-account opening and per-fill eligible last-book intent, true as-of source equity at execution, source-ID/clock-matched SHA-local prospective fixture receipts | Receipt presence alone is not an external attestation; real 94-wallet inputs lack signed independent NAV/receipt evidence |
| `pm_offline_job` | Single manifest-to-report CLI for sealed complete synthetic PM-03 fixtures or real historical oracle SCREEN_ONLY; immutable report SHA and typed scenario-level BLOCKED/PARTIAL | No REAL financial PASS/BREACH/alpha path from historical vendor fills |

The PM-03 fixture adapter uses `Account`, `evaluate`, `mark`, `verify`, and
`execute_targets` from the existing PM-03 modules; it is not a competing
ledger or a real-data runner. Its summary is always labeled `SYNTHETIC_PM03_*`
and its source fixture completeness flag is not an independent attestation.

The new `pm_offline_sweep` CLI runs only explicitly marked synthetic
fixture studies, with read-only SHA-pinned native data and sealed scenario
cache, versioned source/risk/cost manifests, 3-/5-wallet stress, five delays,
and bounded 1-/2-worker replay. It accepts nonflat **independently specified** opening books only with complete leader marks and source-equity as-of at the actual execution minute; cross-DEX same-manager books remain blocked without a consolidated admission contract. One unadmitted manager blocks only the affected scenario, not unrelated completed work. The separate `pm_offline_job` manifest-driven facade also runs the sealed 90-day real-source oracle-only screening pipeline and never certifies real follower P&L.

Frozen PM-01 v2, PM-04, wallet registry and forward-paper modules are unmodified. One **internal PM-03 allocation precision fix** preserves all public PM-03 interfaces: exact full fills now retain original high-precision pod quantities, and partial pro-rata rounding redistributes residuals without exceeding requests. Deterministic 250-case Decimal stress, original account/FP tests and targeted high-precision partial execution regression are required before any review or merge.

### Timestamps and scientific meaning

Every event uses its own `eligible_at = first_known_at + delay`.
The next candidate minute open is **strictly after** eligibility, even at
exact-minute equality. Events already eligible at the same later open may
compact; later-known events may not. `HISTORICAL_ORACLE` requires the supplied
known clock equal the vendor event clock and cannot represent real first-known.
`PROSPECTIVE_FIRST_KNOWN` requires a separately hashed receipt source at the
manifest layer. A receipt hash is not independently validated clock fidelity
without the external producer/auditor.

Native 1m OHLCV is not an executable book. Current-minute realized volume is
diagnostic only. Capacity uses previous **completed** 1m volume as a proxy;
it does not establish known tradable depth. Native data hold float market
columns, so the market projection is `price_open_float_screen_only`, not
contractual cash precision.

### Manual regression

```sh
uv run --extra market --group dev python -m pytest -q \
  tests/test_pm_offline_sweep_cache.py tests/test_pm_offline_sweep_market.py \
  tests/test_pm_offline_sweep_source.py tests/test_pm_offline_sweep_eligibility.py \
  tests/test_pm_offline_sweep_manifest.py tests/test_pm_offline_baseline.py
# 44 passed (before later source changes)
uv run --group dev ruff check src tests
uv run --group dev ruff format --check src tests
```

The synthetic manifest-to-PM03 fixture runner and first bounded cold/warm
cache/worker timing now exist. Remaining: original real-data complete-source
adapters, nonzero initial admission, portfolio alias/DEX joint books,
independently verified first-local receipts and source NAV, real funding,
real contract and exact execution prices, 90-day bounded chunked account
replay, representative matched baseline, independent differential audit,
and final review. Accordingly Issues #81–#90 remain partial/open. No new trades, external network source
calls, protected service edits, private data commits or runtime restarts.

## Final bounded synthetic benchmark checkpoint

On the verified Python 3.14.6 / Polars 2.1.0 VPS, with 5 synthetic source
managers, 3 portfolio/cost scenarios, all five delay policies, one synthetic
minute market, 2 workers, an isolated private cache and no source acquisition:

| Trial | Wall time | CPU user | CPU system | Process peak RSS high-water | Sealed tape hits | Scenario hits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| cold private cache (OS page cache not purged) | 0.123106 s | 0.093407 s | 0.072921 s | 90,692 KiB | 0/5 | 0/15 |
| warm private cache 1 | 0.033308 s | 0.014988 s | 0.025409 s | 91,076 KiB | 5/5 | 15/15 |
| warm private cache 2 | 0.029599 s | 0.019520 s | 0.019483 s | 91,460 KiB | 5/5 | 15/15 |

All scenarios have the same SHA
`d47aae6d8e17f3f17eadc85c9115c183e193e9121537b1e5c9769a49cba88287`
across trials. This is **not** a measured old-versus-new production speedup:
the existing PM-01 benchmark has different oracle policy, workload and
accounting. An independently comparable 90d/500k fills/13M 1m bar
benchmark, memory/spill and p50/p95 are still BLOCKED by incomplete
real-data source/equity/receipt and native sidecar evidence.

## Updated independent cache and PM-03 high-precision regression (Option A)

The current synthetic complete-fixture pipeline now has **four independently
keyed immutable stages** before the final report: (1) whole-source-book +
as-of NAV, (2) native 1-minute market panel, (3) per-delay whole-book
eligibility tape, and (4) scenario ledger. Input changes affect only
dependent outputs: changing cost does **not** rebuild source/market/eligibility;
changing native market SHA rebuilds market/scenario but not source/tape;
changing source SHA rebuilds source/tape/scenario but not market; changing
declared owner/DEX identity cannot borrow another cached source book.
All SHA objects remain private, fsynced, byte-validated and bounded.

Five synthetic managers, 3 portfolio/cost scenarios, five delays, two workers,
isolated private cache and **no disk-cache purge** produced:

| Trial | Wall | Source hits | Market hits | Delay tape hits | Scenario hits | Cache bytes | Process RSS high-water |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial sealed fixture | 0.187041s | 0/1 | 0/1 | 0/5 | 0/15 | 107,823 | 92,244 KiB |
| Warm #1 | 0.028671s | 1/1 | 1/1 | 5/5 | 15/15 | 107,823 | 92,244 KiB |
| Warm #2 | 0.025495s | 1/1 | 1/1 | 5/5 | 15/15 | 107,823 | 92,244 KiB |

All outputs share logical SHA
`a06326b77b897b6675b5402380888b8b036eae069667f26b4124da1350d073ab`.
A true child-process **SIGKILL** after one sealed scenario resumed 1/15
scenario hits, preserved source/market/eligible state and reached exactly
the same final logical SHA. This tests software crash-consistency, not live
broker state recovery.

A changed native open price exposed the original PM-03 allocation function
rounding a high-precision complete fill, causing a false
`OVERSIZED_PARTIAL_ALLOCATION`. The internal allocator now preserves exact
pod quantities for complete fills and clamps/redistributes pro-rata partial
rounding. Its public API and financial Account authority are unchanged.
Dedicated positive/negative randomized 250-case Decimal allocation tests,
source/market invalidation tests, partial reduction, overnight funding,
subcent inclusive floor tests and original PM-03 compatibility tests
demonstrate the engineering correction.

**Hot weekly cache:** independent verified BTC week 2026-10-19–25 UTC was compiled into 10,080 rows / 485,609 bytes with read-only mmap and exact source-sidecar SHA. Initial observed wall 0.260344s, warm mapping 0.002481s and 0.001780s; SHA `5a16af43ee151d6b5d9a44db04830443d9ed1c1e9104d41578ca4e9bc30f347f`. The 7-day layout was selected after bounded-source profiling; the default 90-day oracle context still uses its existing fast, output-parity-verified cache. Both are SCREEN_ONLY and never imply executable L2 liquidity. No protected native files are rewritten.
Scientific qualification also remains unavailable without independently
as-of source NAV, complete historical book and real receipts.

## Real local source and native alignment added after synthetic checkpoint

The prior sections cover the synthetic-only manifest/PM-03 fixture.
Additional read-only, **real-source** modules now provide a strict
90-day retrospective historical-oracle fill cache and SHA-verified native
market matching without pretending real first-known or historical
source equity exists. The detailed counts, source/tape/market SHA,
same-input optimized versus original join timings and remaining
financial gate are in the [2026-11-04 real source audit](OFFLINE-PIT-REAL-ORACLE-20261104.md). The source/market adapters remain
independent of the synthetic PM-03 fixture and Forward-Paper policy.
