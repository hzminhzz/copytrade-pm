# Six-portfolio Reservoir two-DEX historical update — 2026-11-12

**State:** HISTORICAL SOURCE ACQUIRED + PRIVATE CATALOG VERIFIED; not canonical ingestion, not complete intraday books, not first-known receipt proof, not paper-trading financial admission, and not trading authorization.

**What changed:** The six candidate paper portfolios' selected source-wallet identities were verified against the current sealed SQLite registry. A **31-completed-UTC-day retrospective window, 2026-10-12 through 2026-11-11**, was acquired and indexed from Hydromancer Reservoir for **`hyperliquid` + `xyz` only**, with no other HIP-3 sources queried. Each DEX/day was scanned once for the entire wallet set; only selected-wallet rows were retained.

The six portfolio definitions: A v2, B v2, C v2, Combo2 v2, `regime.macro/TriadA` v2 and `regime.macro/TriadChop` v2. They reference 18 sealed membership records and **14 distinct wallet addresses**. Selected-account historical as-of availability starts November 2–7; earlier backtests of this fixed roster must be labeled **EX_POST_SELECTION**, not historical manager-selection skill.

## Exact data and verification

| Measure | `hyperliquid` main | `xyz` | Total |
| --- | ---: | ---: | ---: |
| Actual selected-wallet historical fill rows | 14,619 | 3,603 | **18,222** |
| Fill IDs absent from current canonical store for same dates/DEX | 8,148 | 3,603 | **11,751** |
| Existing local trade IDs matched in Reservoir | 6,471 | 0 | **6,471** |
| Wallets with at least one fill over 31 days | 14 | 8 | 14 unique selected |
| Source position rows retained within approved DEX scope | 2,940 | 1,118 | **4,058** |
| Consecutive-day two-sided endpoint comparisons | 2,653 | 980 | **3,633** |
| Matching signed-fill aggregate endpoint deltas | 2,653 | 980 | **3,633** |
| Positions present on only one of two consecutive anchors | 389 | 203 | **592** |

**Source bounds:** 31/31 dated fill and position objects checked per DEX, original S3 path, ETag, source sizes, non-null temporal source block and file SHA retained. The 2026-11-05..11-11 **main DEX fill set was reused from the original pilot** (no repeat S3 main-fill scan); its existing global perp snapshot was **filtered to main-market rows only** in the research catalog. All other new main/xyz anchors use **exact native per-DEX snapshots**. Main/xyz source snapshot block/time identities agreed for **31/31 days**.

**Parity meaning:** All explicitly comparable *daily endpoint quantities* match the aggregated signed fills, including across separate weekly batches. This does **not** prove uninterrupted intraday position state: multiple fills share the same timestamp, 592 snapshot legs lack two explicit anchors, and non-fill account actions or missed wallet scopes may remain. Zero selected-wallet fills never certify inactivity.

**Network/storage efficiency:** Full S3 source objects were never copied locally. Ten fill columns (native `DECIMAL(20,10)` quantities and UInt64 trade IDs), selective snapshot columns, and one query per selected DEX/day. Combined preflight projected compressed source column chunks over all batches: **~7.816 GB** (not measured network bytes or AWS invoice). Previously instrumented only three original main-Dex days: **206.563 MB of process-level TCP receive syscalls**, not precise S3 charge. Actual retained private zstd Parquet across 124 files: **1,122,867 bytes (~1.12 MB)**. Other external fees/request counts not measured; avoid claiming a precise AWS bill.

## Private data authority and access

**Private catalog path:**

`/home/quant/.local/share/copytrade/research/reservoir-six-20261012-20261111/catalog.json`

**SHA256:** `5260c2cdad7ac16af7a2e19913bf33bd8fd9c250b97b7ab2fa6c64b6bb5e8bf0`

The catalog is a source-qualified immutable index pointing to the exact SHA-verified stored fill and snapshot Parquet files and preserving cohort set SHA plus six sealed portfolio version records. It does **not** replace the SQLite wallet registry (`wallet_registry.sqlite`), canonical mutable data services, or existing private journals.

**Agent-owned reader:**

~~~python
from scripts.catalog_reservoir_six_portfolios import (
    CATALOG_ROOT, read_manifest, scan_fills, scan_snapshots,
)
import polars as pl

catalog = read_manifest(CATALOG_ROOT / "catalog.json")
main = scan_fills(catalog, "hyperliquid")
xyz = scan_fills(catalog, "xyz")
main_positions = scan_snapshots(catalog, "hyperliquid")
xyz_positions = scan_snapshots(catalog, "xyz")

print(main.select(pl.len()).collect())           # 14619 fills
print(xyz.select(pl.len()).collect())            # 3603 fills
print(main_positions.select(pl.len()).collect()) # 2940 anchor rows
print(xyz_positions.select(pl.len()).collect())  # 1118 anchor rows
~~~

`scan_fills` and `scan_snapshots` refuse third DEXes, outside-window scans, missing date files, paths escaping the private research root and SHA-mismatched Parquet. All source data still has **exchange event time**, not first local receipt.

**Verification commands** (Python 3.13 / quant-lab DuckDB research environment):

~~~bash
/home/quant/dev/quant-lab/.venv/bin/python scripts/catalog_reservoir_six_portfolios.py verify
/home/quant/dev/quant-lab/.venv/bin/python -m pytest -q \
  tests/test_catalog_reservoir_six_portfolios.py \
  tests/test_pilot_reservoir_wallet_scoped.py \
  tests/test_pilot_reservoir_contract.py
~~~

**Expected:** exact manifest SHA, 31/31 two-DEX dates, 14-wallet scope, 14,619 + 3,603 rows; 22 focused research tests passing at last execution. Broad repository CI and PR merge are separate and must be reverified before claiming completion.

## Next gates before paper economic use

1. **Source/admission:** A modeled five-minute checkpoint must use the independently documented historical observation-latency model; vendor historical fills cannot become actual first-known. Same-millisecond event ordering and single-ended positions must be bounded/blocked. Only selected **main + xyz** DEX scope is supported. If other markets were held, mark **PARTIAL_WALLET_BOOK** rather than a zero.
2. **History coverage:** This update is **31 days**, not January–November 2026. Older history has uneven existing local registrations (5–14 wallets per month, depending on month). To claim full 2026 economics, independently budget, acquire and verify the missing earlier dates; do not equate local partition presence with complete source history.
3. **Finance:** Backtest position state and realistic follower execution only after PM-03/PM-04 source-to-finance integration, authentic frozen k mandates, follower quotes, costs, funding, risk and independent approvals. Historical source checks are not six-portfolio financial paper admission.
4. **Production isolation:** The protected live CWSA source/paper services, original selected registry, existing canonical fills partitions and Guardian remain **untouched** by this backfill. The 11,751 source-only IDs were not silently written into canonical `data/private/wallet_store`, whose schema migration is a separate reviewed change.

**Code:** `scripts/pilot_reservoir_wallet_scoped.py` supports allowlisted two-DEX per-day acquisition and immutable source manifests; `scripts/catalog_reservoir_six_portfolios.py` builds and verifies the cross-week catalog and exposes the Polars scan. See the [Reservoir acquisition plan](RESERVOIR-WALLET-DUCKDB-PLAN-20261112.md) and the [original seven-day pilot](RESERVOIR-WALLET-PILOT-20261112.md).

**Attribution:** Data: Hydromancer Reservoir (reservoir.hydromancer.xyz), CC BY 4.0. This report describes an address-filtered, source-pinned, historical derivative and no independent endorsement.
