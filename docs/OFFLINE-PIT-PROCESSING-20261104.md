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
| `pm_offline_cache` | Owner-private immutable SHA object keys, fsync hardlink sealed metadata, error on corruption, content-sensitive dependencies and size/disk floor | Actual compiled tape/market worker integration, restart process fault/memory benchmark |
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

All files are new offline-only modules. Frozen PM-01 v2, PM-03,
PM-04, wallet registry and forward-paper modules are unmodified.

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

## Real local source and native alignment added after synthetic checkpoint

The prior sections cover the synthetic-only manifest/PM-03 fixture.
Additional read-only, **real-source** modules now provide a strict
90-day retrospective historical-oracle fill cache and SHA-verified native
market matching without pretending real first-known or historical
source equity exists. The detailed counts, source/tape/market SHA,
same-input optimized versus original join timings and remaining
financial gate are in the [2026-11-04 real source audit](OFFLINE-PIT-REAL-ORACLE-20261104.md). The source/market adapters remain
independent of the synthetic PM-03 fixture and Forward-Paper policy.
