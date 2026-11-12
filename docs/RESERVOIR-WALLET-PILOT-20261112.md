# Reservoir seven-day wallet-scoped pilot — 2026-11-12

**Status:** HISTORICAL SOURCE PILOT COMPLETED; no canonical ingestion, paper execution, scientific qualification, or trading authorization.
**As-of:** 2026-11-12 12:16:32 UTC. **Window:** 2026-11-05 through 2026-11-11, UTC.
**Cohort:** 14 unique wallet identities resolved privately from latest sealed SQLite definitions for six portfolios: A, B, C, Combo2, `regime.macro/TriadA` and `regime.macro/TriadChop`. The sealed selection known-at dates run from November 2 to November 7, so this is a retrospective fixed-cohort study, **not** a historical PIT selection study.

## Execution and evidence

- Seven main-DEX `by_dex/hyperliquid/fills/perp/all/date=YYYY-MM-DD/fills.parquet` objects, read using DuckDB httpfs/requester-pays. **One remote query per UTC DEX/day for all 14 wallets**, selecting only address, timestamp, coin, dex, side, size, start_position, trade_id, direction, is_liquidation. No one-query-per-wallet repeated scans.
- Seven global daily perp snapshots (`global/snapshots/perp/all/date=YYYY-MM-DD/{block}_{timestamp_ms}.parquet`), using the genuine state timestamp and block, never synthetic midnight. Exact source object sizes, ETags, single-state path, projected compressed bytes, private cohort hash, and schema were preflight-checked.
- Selected results stored as private, immutable zstd Parquet with SHA sidecars; canonical `data/private/wallet_store` partitions **not modified**.

**Private immutable evidence:** `/home/quant/.local/share/copytrade/research/reservoir-wallet-pilot-20261112/`

Contains `preflight.json`, `fills/day=*/data.parquet`, `position_snapshot/day=*/data.parquet`, provenance sidecars, per-day fetch summaries and corrected `parity-report-v2.json`. An initial `parity-report.json` is retained as superseded evidence; its naïve chain ordering misclassified ambiguous same-millisecond groups as 144 broken pairs. **Authoritative private v2 report SHA256:** `00449476a553a1f174880fe324fbf0993792493c96bba5a27042cb8d8c7a1cb9`. Private address data and credentials are excluded from Git and from summary reports.

## Efficiency and measured quantities

| Source volume or metric | Result |
| --- | ---: |
| Seven unfiltered main-DEX fill object sizes (HEAD) | **2,635,843,318 bytes** |
| Seven unfiltered global snapshot sizes (HEAD) | 212,652,917 bytes |
| Core ten-field compressed column-chunk estimate (Parquet footer) | 816.398 MB |
| Snapshot compressed column-chunk estimate | 212.566 MB |
| Total preflight estimate versus cap | **1,028.964 MB / 1,300 MB cap** |
| Private selected-wallet fill Parquet retained | **51,038 bytes** |
| Private selected-wallet snapshot Parquet retained | **71,706 bytes** |

Address min/max row-group statistics were absent in all seven inspected main-DEX fill objects; the one-wallet prior test accessed all row groups. **Filtering wallets reduces returned rows and stored bytes, but not proportionally the S3 transfer.** Projecting only ten columns and scanning **once per DEX/day for the entire cohort** are the primary efficiency improvements.

Socket receive-syscall observations (strace, TLS + non-S3 traffic included): November 5 **96.969 MB**, November 6 **72.061 MB**, November 7 **37.532 MB**, total **206.563 MB** across those three days. November 8–11 transfer **not measured**. These are observed recvfrom/recvmsg bytes, **not authoritative S3 billed bytes**; some network receive implementations may be uncounted. Do not extrapolate one short window into guaranteed monthly cost. The November 7 container command timed out after writing both complete file/sidecar pairs; a retry verified the immutable pair and produced its day summary without refetching.

## Exact local/source trade-ID comparison

The checked period is **98 wallet-days**. Every one of the 78 local matched trade IDs appears in Reservoir, and 1,000 additional source IDs were not in the canonical store.

| Day (UTC) | Reservoir selected perp fills | Local matched | Source-only | Selected-account perp snapshot rows |
| --- | ---: | ---: | ---: | ---: |
| Nov 5 | 153 | 0 | 153 | 118 |
| Nov 6 | 145 | 0 | 145 | 133 |
| Nov 7 | 73 | 0 | 73 | 126 |
| Nov 8 | 226 | 0 | 226 | 134 |
| Nov 9 | 206 | 45 | 161 | 133 |
| Nov 10 | 175 | 33 | 142 | 128 |
| Nov 11 | 100 | 0 | 100 | 131 |
| **Total** | **1,078** | **78** | **1,000** | **903** |

96/98 wallet-days had no local registered fill partition. Of 98 wallet-days, **43** were source-positive/local-empty; **53** had no fills in either source for the checked DEX/day and remain **UNKNOWN**, not confirmed inactive. Local-only IDs: 0 in this sample. The 1,000-source-ID acquisition gap is proven *relative to these selected objects and dates*, not a universal source completeness claim.

## Position continuity: positive findings and strict limits

Six consecutive daily snapshot pairs yielded **511 wallet-market positions explicitly present at both endpoints**. Of these, **52** had intervening source fills, and **51** had nonzero endpoint size changes. All 511 endpoint deltas—including the 51 changed positions—matched signed aggregate fills. **459** had no intervening fills. **30** snapshot entries were present at only one endpoint and could not be admitted as two-sided parity checks. A daily snapshot is not a complete five-minute tape.

**Event order remains unresolved for most fills:**
- 43 wallet-market fill series.
- 142 multi-fill same-millisecond groups containing **911/1,078 fills**.
- 172 adjacent timestamp-group transitions touch a multi-fill group and have ambiguous internal ordering.
- **94/94** neighboring timestamp groups containing exactly one fill each passed signed start_position continuity; zero proven mismatches in that restricted class.
- Prior naïve `ORDER BY timestamp,trade_id` produced false mismatch candidates and is **not an approved position-chain reconstruction**.

The source fills carry leader **exchange execution time**; neither these nor daily snapshot files provide genuine local first-known receipt time. Only the main DEX fill objects were fetched; HIP-3/other DEX completeness, real intraday state and follower execution economics remain unverified.

## Reproduction and safe next work

Code: `scripts/pilot_reservoir_wallet_scoped.py` (isolated worktree, pending review/merge). Run via the existing quant-lab Python 3.13 + DuckDB 2.0 + PyArrow environment; the copytrade-pm Python 3.14 venv did not contain DuckDB. Commands:

~~~bash
python scripts/pilot_reservoir_wallet_scoped.py preflight --start 2026-11-05 --end 2026-11-11 --max-projected-mb 1300
python scripts/pilot_reservoir_wallet_scoped.py fetch --day 2026-11-05
# Repeat each frozen day, idempotently and within the preflight budget.
python scripts/pilot_reservoir_wallet_scoped.py report
~~~

13 focused synthetic research tests plus 2 dependency-light source safety tests passed in the research environment; core/market CI each passed 2 tests with the optional 13-test research module skipped. Ruff lint/format passed. Every query is wallet-scoped, DEX/day-bounded, source version checked and fail-closed. No private selected-wallet list or API credentials are committed. No canonical data or production execution was touched.

**Next separate task, not authorized as part of this pilot:** verify complete selected HIP-3 DEX scopes and budget them separately; reconcile the 1,000 missing canonical IDs through a reviewed, versioned schema; solve same-millisecond causal event order with independently verified native evidence; handle single-ended anchors and account-mode gaps; only then create explicitly **MODELED** five-minute checkpoints under calibrated receipt lag. Do not equate any result with prospective follower profitability or permission to trade.

See [the Reservoir acquisition plan](RESERVOIR-WALLET-DUCKDB-PLAN-20261112.md) in the primary checkout and the [official fills schema](https://docs.hydromancer.xyz/reservoir/schema-reference/fills.md).

Data: Hydromancer Reservoir (reservoir.hydromancer.xyz), CC BY 4.0. Changes: filtered to a private, sealed cohort and reconciled against local trade IDs and daily position anchors.
