# Offline PIT sweep baseline (Issue #80)

**Scope:** frozen existing PM-01 historical fill reconstruction, synthetic market
control, and PM-03 baseline regressions. No offline-sweep optimizer is present
at this checkpoint. Source pages and native market data were not mutated.

## Host and version evidence (2026-11-04)

- Verified `origin/main` base: `e5d99339c8b4eceac92744cbf804497a3b05cc6a`.
- Python 3.14.6, Polars 2.1.0, uv 0.12.15, 8 logical CPUs.
- Root volume 436 GiB, 368 GiB used, 68 GiB free (85% used).
- Memory 23 GiB total; 13 GiB available at inspection.
- Swap 8 GiB total; 4.8 GiB in use. Shared services not interrupted.
- Optional-market dependency metadata currently allows `polars>=1.20`;
  the lock/environment resolves to 2.1.0. Do not assume every install is 2.x.

## Read-only reference

```sh
uv run --extra market --group dev python -m copytrade_pm.pm_offline_baseline --fills 120 --iterations 2
```

The harness constructs a deterministic credential-free 120-fill W001/BTC
source fixture in a private temporary directory. It calls the **existing**
`_source_fills` and `replay_wallet` with the frozen 5-minute historical
oracle policy and an explicitly synthetic constant-price/unlimited-volume
market. It does not write to the authoritative market lake, original source
pages, registry, or ledger. Its logical-result hash excludes elapsed time.

Source JSON SHA256: `ab25621ec99f567f62fe936363ccb5c3e5fd7c89d28ed2df417a33ed0039f60d`.

| Trial | Wall time | Source parse | Peak process RSS high-water | Logical result SHA256 |
| --- | ---: | ---: | ---: | --- |
| First (cold fixture, OS cache unproven cold) | 0.005693 s | 0.001488 s | 30012 KiB | `6448c4af02a24daa68566197ed99b2a63061428e6f5e0361e996f68f5bb9f85a` |
| Second (warm OS cache) | 0.003475 s | 0.000934 s | 30012 KiB | same |

This is a fixture microbenchmark, **not** a 500k-fill / 13M-bar production
baseline. No per-iteration allocated RSS, physical disk read bytes, CPU time,
OS cache purge, streaming Parquet throughput, or stress footprint has been
independently measured. The first trial is **not** a guaranteed cold-disk read.
A numeric optimizer speedup target cannot be established from this alone.

## Preserved contracts and independent boundaries

| Surface | Unmodified contract |
| --- | --- |
| PM-01 | `pm01_fill_only_replay_v2`, exactly 36 frozen identities, legacy 5/15/60m hypothetical delay |
| PM-01 source | SHA-verified vendor pages; exchange event time is historical oracle, not first-known |
| Native minute source | `VerifiedHyperliquidMinuteSource` SHA-validates day Parquet and metadata |
| PM-03 | Decimal `Account` and `Rulebook`; exact sequential financial authority/HALT |
| PM-04 / FP PR #73 | Separate first-event, non-resetting T+300s future paper policy |
| Wallet registry | Mainline read-only ownership; PR #57 was closed unmerged on GitHub; merged replacement PR #79 and fix #91 on `main` |
| Research status | No scientific qualification, real orders, or prospective first-known inference |

At baseline, the following verification commands passed:

```sh
uv run --group dev python -m pytest -q tests/test_pm_fill_replay.py tests/test_pm03_account.py tests/test_pm03_adversarial.py
# 40 passed
uv run --group dev ruff check src tests
# All checks passed
```

Do not compare the existing synthetic/hindsight result numerically against a
new strict per-fill, exact-PM03 simulation as if execution policies were equal.
Further baseline benchmarking requires observed, independently verified native
inputs and bounded resource envelopes.
