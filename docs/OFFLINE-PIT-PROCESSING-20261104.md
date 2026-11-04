# Offline Polars 2.x source / market processing — engineering checkpoint

Date: 2026-11-04. This is **not** a completed research sweep, an exact
PM-03 account replay, independent PIT verification, or executable liquidity
certificate. See [baseline](OFFLINE-PIT-BASELINE-20261104.md) and
[specification #78](https://github.com/hzminhzz/copytrade-pm/issues/78).

## Implemented isolated processing components

| Component | Input contract / outputs | Remaining integration |
| --- | --- | --- |
| `pm_offline_manifest` | Manifest v1 SHA and source/market/rule/cost file checks, clock basis, 0/1/2/5/10m, typed INVALID/BLOCKED | Verify source-file semantic schemas and native day identities; one manifest-to-report facade |
| `pm_offline_source` | Atomic verified initial book, position-before/after continuity, strict all-DEX/account identities and as-of positive equity, stable digest | Independent signed source/receipt producer; source/equity snapshot integration; same-ms continuity inference |
| `pm_offline_eligibility` | Polars 2.1 lazy strict next-bar, event-specific eligibility, stable streaming/in-memory hash, right-censor | Connect whole-book source tape; independently verified real receipt SHA and maturity |
| `pm_offline_market` | Native day Parquet SHA; exact namespace + minute join; prior completed bar volume; ex-post volume separate | Source market-day manifest reconciliation; resource-bounded hot partitions; full minute MTM; source calendar/session |
| `pm_offline_cache` | Owner-private immutable SHA object keys, fsync hardlink sealed metadata, error on corruption, content-sensitive dependencies and size/disk floor | Actual compiled tape/market worker integration, restart process fault/memory benchmark |
| `pm_offline_account` | Fixture-only sequential PM-03 Decimal Account + PM-03 execute_targets, whole-source-equity target sizing and per-minute risk marks | Integrate only verified source/market tapes and funding/contract receipts; account-lifecycle SHA journal and exact certification |

The PM-03 fixture adapter uses `Account`, `evaluate`, `mark`, `verify`, and
`execute_targets` from the existing PM-03 modules; it is not a competing
ledger or a real-data runner. Its summary is always labeled `SYNTHETIC_PM03_*`
and its source fixture completeness flag is not an independent attestation.

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

Until the verified-data account replay, exact financial certification, full manifest-to-report
and end-to-end cold/warm private benchmarks are built and verified, Issues
#81–#90 retain open or partial status. No new trades, external network source
calls, protected service edits, private data commits or runtime restarts.
