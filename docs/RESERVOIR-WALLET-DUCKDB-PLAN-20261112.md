# Reservoir: wallet-scoped DuckDB acquisition and PIT backtest plan

**Status:** 14-wallet, 31-day two-DEX source staging **completed** ([evidence](RESERVOIR-SIX-PORTFOLIO-BACKFILL-20261112.md)); wider **269-wallet, July 1–November 11** historical acquisition **metadata prepared but fills BLOCKED by expired AWS authentication** ([current runbook](RESERVOIR-MONITORED-PLUS-SIX-269-20261112.md)). Only `hyperliquid` + `xyz`; no canonical-store ingestion, paper financial admission or trading authorization.
**Evidence reviewed:** 2026-11-12 10:32–10:50 UTC, source docs fetched 2026-11-12.
**Working checkout inspected:** /home/quant/dev/copytrade-pm, HEAD 6c07cc6d; checkout dirty and behind remote. These are dated observations, not current source-of-truth service status.

**When to read:** Before any Hydromancer Reservoir S3 query, wallet-fill backfill, historical position reconstruction, account-value interpretation, or historical CWSA five-minute checkpoint study. For the canonical wallet-store API and its catalog, read [WALLET-STORE.md](WALLET-STORE.md). For current source inventory and unresolved data semantics, read [DATA-SOURCES-RESERVOIR-VIKE-20261112.md](DATA-SOURCES-RESERVOIR-VIKE-20261112.md).

## 1. Decision: scan once per DEX/day, retain only selected wallets

**ADOPT:** The **only allowed Reservoir perpetual DEXes are `hyperliquid` (main/default) and `xyz` (HIP-3)**. Run one bounded DuckDB S3 query per allowed DEX and UTC day with **all selected wallet addresses in the same prepared predicate**. Project only required fields, retain the complete wallet execution history *within those two DEXes*, and persist matching wallet rows into private immutable Parquet. Reuse already verified local partitions first. The 2026-10-30 Propr public-display snapshot maps 96 unique crypto perps to `hyperliquid` and 61 equities/index/commodity instruments to `xyz` (157 unique in total); this is a **dated display universe**, not account-specific order authorization or a historical listing guarantee.

**AVOID as default:** one Reservoir query *per wallet*, wide global fills when a single DEX object suffices, SELECT *, full-object local downloads, joining snapshots by the folder date instead of the block timestamp, and combining the fill sub-datasets with the overlapping perp/all tape.

**Important bandwidth caveat:** A WHERE address predicate filters the result rows, but it does NOT promise a tiny network transfer. A one-wallet sample scanned all 9 Parquet row groups, and address statistics were absent in all 9. Projected column-chunk transfer, not output row count, dominates that example. Actual network bytes were **not instrumented**.

Scope: Start with the **actual sealed selected source-wallet scope** of the new six-paper-portfolio CWSA study (previously 14 accounts; re-resolve before execution). Explicitly **exclude all other HIP-3 DEXes** (`cash`, `hyna`, `flx`, `km`, `vntl`, `para`, `io`, etc.) from acquisition. If selected wallets hold exposure outside `hyperliquid` + `xyz`, report it as **OUT_OF_STUDY_SCOPE / PARTIAL_WALLET_BOOK**, not flat and not a faithful whole-wallet replication. The full 264-wallet production roster and the 502-identity research registry are separate scopes. A current selection backtested before its historical known_at is an ex-post fixed-cohort study, **not** a PIT selection strategy.

## 2. Official Reservoir source reference (checked 2026-11-12)

- [Native Hyperliquid source](https://docs.hydromancer.xyz/reservoir/hyperliquid.md) — main crypto perp/spot source available from 2025-07-28; HIP-3 dexes have separate prefixes.
- [Fills and exact types](https://docs.hydromancer.xyz/reservoir/schema-reference/fills.md) — all perpetual executions, 27-column documented schema; decimal(20,10), uint64 trade/order IDs, timestamp(ms, UTC), signed position-before-fill. Optional columns have date-dependent availability.
- [1-second candles](https://docs.hydromancer.xyz/reservoir/schema-reference/candles.md) — one object per DEX/day, all markets for that DEX, trade-derived 1s OHLCV, decimal prices/sizes. Larger intervals may be aggregated using first/open, max/high, min/low, last/close, sum/volume and sum/trade_count; never fabricate no-trade seconds.
- [Daily snapshots and semantics](https://docs.hydromancer.xyz/reservoir/schema-reference/snapshots.md) — one ABCI state per available day, filename is {block}_{timestamp_ms}. Source rows describe the captured state **at that timestamp**; not necessarily UTC midnight. The vendor documents a late-October to mid-December 2025 capture gap, plus a 2026-10-15 re-export of all dates with revised unified/PM semantics. Snapshot revisions require fresh source hashes and explicit provenance.
- [Reservoir attribution](https://docs.hydromancer.xyz/reservoir/license-and-attribution.md) — CC BY 4.0. Derived datasets must acknowledge Hydromancer Reservoir and transformations.

Requester-pays S3 bucket: s3://hydromancer-reservoir, AWS region ap-northeast-1. Reuse the already working helper **/home/quant/tmp/reservoir_query.py**: it obtains transient default-profile credentials with aws configure export-credentials, installs/loads DuckDB httpfs, sets S3 region and requester-pays, and creates an in-connection DuckDB S3 secret. Keep secrets and wallet lists out of Git, CLI logs and docs. As of the test, DuckDB in the quant-lab venv was 2.0.0 (Python 3.13); the copytrade-pm Python 3.14 venv did **not** have DuckDB. Pin approved dependencies when promoting an adapter; do not silently switch runtimes.

### Paths; never use a market-wide glob by accident

| Need | Exact object family | Scope |
| --- | --- | --- |
| Main perp fills | `by_dex/hyperliquid/fills/perp/all/date=YYYY-MM-DD/fills.parquet` | 14-wallet query, one per UTC day |
| Propr `xyz` perp fills | `by_dex/xyz/fills/perp/all/date=YYYY-MM-DD/fills.parquet` | Same wallet set, separate one-per-day query |
| Main perp position anchors | `by_dex/hyperliquid/snapshots/perp/date=YYYY-MM-DD/{block}_{timestamp_ms}.parquet` | One state per available day; verify block/time |
| `xyz` perp position anchors | `by_dex/xyz/snapshots/perp/date=YYYY-MM-DD/{block}_{timestamp_ms}.parquet` | Verify block/time compatibility with main |
| Existing main-only pilot's global anchors | `global/snapshots/perp/all/date=YYYY-MM-DD/{block}_{timestamp_ms}.parquet` | Retained historical pilot input; **not approved for new acquisition** |
| Existing account values | data/private/nav_hyperliquid_perp_daily/date=YYYY-MM-DD/data.parquet | Already downloaded locally; mode-aware, selected roster |
| Optional spot collateral | global/snapshots/spot/date=YYYY-MM-DD/{block}_{timestamp_ms}.parquet | Only if collateral/account-mode reconciliation needs it |
| Optional 1s candles | by_dex/{dex}/candles/1s/date=YYYY-MM-DD/candles.parquet | Only for unresolved market-day/intraminute evidence |

**Hard source allowlist for this study:** `hyperliquid`, `xyz`. A `xyz:` market is separate from the main `hyperliquid` DEX; main-only extraction misses those instruments. Do not query any other HIP-3 DEX, global fill tape, or unrelated market-wide input. Preserve all selected-wallet events *within these two DEXes*, including trades in markets not on Propr's dated display list, and label non-Propr instruments as non-executable rather than silently removing hedges. Source `perp/all` already includes liquidations, ADL, builder and TWAP executions; the named sub-datasets overlap and must not be appended.

The fills document specifies 27 schema columns; the sampled Parquet footer exposed 28 physical columns. Confirm exact columns **per actual object**, preserve optional-column evolution and refuse unsupported schema shifts; do not force all dates to the latest field set.

### Native semantics to preserve

- Fill timestamp is **leader exchange execution time**, never local signal receipt time.
- start_position is signed native quantity before the execution; size is unsigned magnitude, side is buy/sell. Validate every fill chain, including flips, liquidations, ADL, settlement and exceptional account events.
- trade_id and order_id are uint64. Retain exact unsigned types or lossless strings, never float32/64.
- Reservoir fill numeric precision: decimal(20,10); do not downgrade to Float64 in lossless research staging. Reservoir daily position-anchor sizes and NAV are supplied as float64; do not create false Decimal precision on those fields.
- Daily position snapshot size is signed. A missing position row alone does not independently prove flatness without proving the wallet book and source scope are complete at that block.
- Snapshot perp funding_pnl is documented as **cumulative PnL** in the market's collateral token; whether it resets under position changes was not established by a matched funding-event test. Store as a diagnostic; never difference as a per-hour cashflow without that proof.
- Account values: standard/dex_abstraction are per-DEX collateral equity; unified account_value can repeat across DEX rows sharing collateral and includes spot balance; portfolio_margin uses pm_total_account_value for whole-account total and per-token account_value can be negative. Never sum duplicate unified rows or unlike collateral units.
- Source files can be missing or revised. No rows served is UNKNOWN, not proof of inactivity, account flatness or zero payments.

## 3. Live one-wallet validation and measured column cost

A read-only DuckDB query previously executed against the selected main-DEX file for 2026-09-29:

- Object: by_dex/hyperliquid/fills/perp/all/date=2026-09-29/fills.parquet
- S3 HEAD object size: **590,501,233 bytes (590.5 MB)**.
- One privately selected registry wallet: **154 source fills** and **154 locally catalogued HL fills**. All 154 trade IDs matched; source-only/local-only IDs: 0; start_position NULL: 0; 13 markets; source query 35.139 s cold.
- EXPLAIN ANALYZE of the subsequent cached scan: **9/9 row groups scanned**. Cached duration 0.358 s is **not** the cold-network benchmark.
- Footer metadata: ~589.88 MB sum of compressed column chunks, **no address min/max statistics in 9/9 row groups**, tx_hash alone ~151.75 MB. This explains why selecting one wallet does not prune entire row groups.

A separate read-only DuckDB parquet_metadata() test on that SAME object estimated the compressed chunks projected by each proposed query:

| Projection on the sample object | Columns | Sum compressed chunks | Interpretation |
| --- | ---: | ---: | --- |
| Minimal eight-column comparison | 8 | ~202.2 MB | Benchmark only; excludes some required event classifications |
| **Position-signal core** | 10 | **~183.0 MB** | Preferred stage-one payload |
| Signal + follower-economic source diagnostics | 16 | ~320.5 MB | Only where leader execution/cost diagnostics need these columns |
| Above + tx_hash | 17 | ~472.2 MB | Exceptional reconciliation/ordering evidence |
| All columns in object | 28 | ~589.9 MB | Avoid as the default |

**All rows groups were accessed** in the single-wallet sample. These figures are **Parquet compressed chunk sums, not actual bytes over HTTP/S3, not billed egress, and not guaranteed transferable bounds**. Source objects on other dates/DEXes have different layouts and sizes. One day cannot justify a 365-day cost forecast without a range sample. The 590.5 MB object is not stored locally by these DuckDB SELECTs.

**Optimization implication:** Projecting columns is the measurable gain; re-reading the same DEX/day object for each of 14 wallets is wasteful. Query **14 wallets at once**, cache the filtered private output, and only request tx_hash on exceptional dates, where its added scan cost is justified.

## 4. Exact extraction design (proposed code, NOT a run command authorization)

### 4A. Preflight: freeze wallet scope and object budget

1. Read the *current* signed SQLite registry and CWSA selection, verify its release and selected account/DEX census, record wallet-set SHA and selection_known_at privately. Historical backtest windows before that known_at must be marked EX_POST_SELECTION unless a separately frozen earlier cohort exists.
2. Build an exact object manifest **for `hyperliquid` and `xyz` only**, per UTC day. HEAD each existing S3 object with RequestPayer=requester and list the per-DEX snapshot keys separately. Treat missing dates or unequal snapshot state identities explicitly as BLOCKED evidence. No global/all-DEX fill glob or third-DEX wildcard.
3. Collect/cached footer metadata for new (source object SHA/version, schema, column chunk compressed bytes, row groups, stats bounds) once per object. Estimate transfer volume for the exact projected field list before initiating bulk requests.
4. Fail if expected daily/total projected scan exceeds the explicit user-approved cap. Record SQL/projection SHA, provider object metadata, estimated bytes, start/end date and requested scope. Never record private wallet lists in reports committed to Git.

**Completion:** Every requested date/DEX has either an explicit, budgeted object or an explicit MISSING_SOURCE_OBJECT status. Neither result implies whether the wallet traded.

### 4B. One DuckDB query for all selected wallets, one DEX and UTC day

The snippet below is a safe **template** for a preflight-approved scope, not an execution of another source acquisition:

~~~python
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, "/home/quant/tmp")
from reservoir_query import connect, load_credentials

DEXES = {"hyperliquid", "xyz"}  # Exact approved acquisition allowlist

# Obtain these privately from signed SQLite selections, not a hardcoded list:
selected_wallets = validated_private_registry_wallet_addresses
dex = selected_verified_dex
day = selected_utc_day

if dex not in DEXES:
    raise ValueError("UNVERIFIED_DEX")
date.fromisoformat(day)
wallets = sorted({str(w).lower() for w in selected_wallets})
if not wallets or any(len(w) != 42 or not w.startswith("0x") for w in wallets):
    raise ValueError("UNVERIFIED_WALLET_SET")

uri = (
    "s3://hydromancer-reservoir/by_dex/"
    f"{dex}/fills/perp/all/date={day}/fills.parquet"
)
placeholders = ",".join("?" for _ in wallets)

sql = f"""
SELECT
    address AS wallet,
    timestamp AS exchange_ts,
    coin,
    dex,
    side,
    size,
    start_position,
    trade_id,
    direction,
    is_liquidation
FROM read_parquet(?)
WHERE address IN ({placeholders})
"""

con = connect(load_credentials("default"))
try:
    con.execute("SET threads=4")
    con.execute("SET memory_limit='2GB'")
    # Returns only the selected wallet rows, preserving native
    # decimal(20,10), uint64 and timezone-aware Arrow data.
    result = con.execute(sql, [uri, *wallets]).to_arrow_table()
finally:
    con.close()

# Validate identity, event uniqueness, exact dtype and completeness
# before any immutable private Parquet publication.
~~~

The wallet predicate is a parameterized IN list. Do not interpolate raw addresses, dates or untrusted DEX names into SQL. Preflight should verify lower-case address representation; if not consistent, block/refine source normalization rather than silently lose mixed-case rows. **Do not ORDER BY on S3** solely for acquisition: sort extracted subsets in Polars only after determining defensible exchange-event ordering.

For same-Dex/day multiwallet extraction, one query should pay for the source column scan once, even if there are 14 selected wallets. The optimized scanner still may touch 9/9 row groups. Record the query’s explain plan; repeat under an uncached run and instrument actual S3 bytes if transfer efficiency is material.

**Completion:** The exact source object and schema are pinned, rows belong only to the selected DEX/wallet set, no unknown coercions or duplicates are silently dropped, and staged payload + manifest hashes match.

### 4C. Escalate columns only on evidence

**Core (10 columns):** wallet, exchange_ts, coin, dex, side, size, start_position, trade_id, direction, is_liquidation.

**Finance extension (6 additional):** price, fee, fee_token, realized_pnl, crossed, order_id.

**Exception-only:** tx_hash (151.75 MB compressed by itself in the sampled object), builder/deployer fees, TWAP identities, settlement/liquidation diagnostics, source-specific order provenance. Query them only for a justified wallet-DEX-day *exception cohort*, but budget any second scan of the source object.

Avoid adding fields to the first pass merely because they exist. Correctness beats a superficially small projection: preserve complete event semantics and promote to extended columns when continuity checks indicate they are needed.

### 4D. Position anchors: exactly the two allowed DEXes

**Future acquisition:** Use only the `by_dex/hyperliquid/snapshots/perp/` and `by_dex/xyz/snapshots/perp/` daily objects. Discover each DEX/date **exact key** by S3 listing. Keep the original `{block}_{timestamp_ms}` in each filename; verify the per-DEX state identities refer to compatible ABCI capture times before combining them. A missing/unsynchronized DEX snapshot is **UNKNOWN / BLOCKED**, never a zero position. The completed main-DEX pilot used the global snapshots, which remain historical evidence but do not justify broad future retrieval.

Read each allowed DEX snapshot with a prepared wallet predicate for the selected cohort:

~~~sql
SELECT user AS wallet, market, size AS signed_size, notional,
       entry_price, liquidation_price,
       leverage_type, leverage, funding_pnl,
       account_value, account_mode
FROM read_parquet(?)
WHERE user IN (/* prepared ?, ?, ... for selected wallets */)
~~~

**Do not infer a snapshot time from its folder date.** Do not use daily state as a fabricated 5-minute snapshot. A prior S3 HEAD found a 2026-09-29 global perp snapshot of 31,035,622 bytes. Per-wallet contents/position parity were not independently queried in that test.

**Completion:** Both allowed DEX snapshot keys have parsable block/UTC state timestamps, compatible capture identities, and complete selected-wallet market scopes **within `hyperliquid` and `xyz`**, or the corresponding interval is BLOCKED. A position on any unqueried DEX does not become zero; whole-wallet fidelity remains explicitly unqualified. No gap is filled with a future snapshot.

### 4E. Reuse existing account-value and 1m bar history

- **Mode-aware account values already acquired:** data/private/nav_hyperliquid_perp_daily, 418 published dates, 79,185 rows, 264 production wallets, 2025-07-29 through 2026-11-10, ~4.76 MB compressed reported in the private manifest. Verify SHA and per-mode interpretation; do not download it again. Its missing days/wallets are UNKNOWN, not zeros.
- **Market prices:** use existing ml4t-data Vike/CHD native 1m Parquet first. Reservoir 1s candles are an exceptional high-resolution or missing-market-day supplement, **not per-wallet data**. Their retrieval is per needed market/DEX/day; no guarantee each second traded.
- **Funding/collateral/ledger:** use independently paginated and verified per-wallet event APIs only where needed for leader accounting; do not infer funding cashflows from daily snapshot funding_pnl differences. Follower funding must be computed for actual follower positions/times under the approved economic model.

## 5. Versioned research evidence schema (do not mutate existing wallet store yet)

Keep canonical wallet-store source and immutable partitions intact until a reviewed schema migration; current source enum omits Reservoir, its Position/Equity models require fields absent in Reservoir snapshots, and existing scan() may expose competing immutable partition generations.

| Proposed dataset | Grain / identity | Mandatory fields and state |
| --- | --- | --- |
| acquisition_manifest | source_object_uri + version + projection_sha | S3 region/dex/date, object ETag/hash, schema hash, source bytes, projected compressed bytes, *measured* transfer bytes or NULL, request count, wallet_set_sha, status, query SHA, acquired_at |
| source_fills_v2 | wallet + dex + verified event identity | exchange_ts, coin, trade_id uint64, side, size decimal(20,10), start_position decimal(20,10), direction, liquidation flag, source_kind=RESERVOIR; optional verified fee/price/tx metadata |
| daily_position_anchors | snapshot_id + wallet + market | state_block, state_ts_ms, signed_size float64, entry/notional, leverage, account mode, source identity and coverage status |
| account_value_diagnostics | source state + wallet + dex + collateral | reuse native account mode, account_value float64, PM fields/branch scope; preserve unit and NULL unknown |
| coverage_evidence | wallet + dex + date + dataset + source-version | source object available, source rows, local rows, matched/unmatched trade IDs, completeness classification, reason and proof SHA |
| reconstructed_books | wallet + scope_sha + reconstructed_state_ts | per-native-market signed quantity, verified anchor and fill-chain evidence, status and gap bounds |
| modeled_cwsa_checkpoints | policy_sha + wallet + scope_sha + five-minute slot | reconstructed exchange state time, **modeled** availability/receipt time, latency model SHA, eligibility/rejection, NOT_PROSPECTIVE tag |

State types: VERIFIED_SOURCE, RECONSTRUCTED_CHECKED, MODELED_HYPOTHESIS, BLOCKED_GAP, BLOCKED_AMBIGUOUS_ORDER, UNKNOWN_SOURCE. Reserve authentic first-known local receipts for prospective telemetry. Use immutable zstd Parquet with SHA sidecars and a private manifest. Separate stable wallet IDs from vendor addresses; never put address lists or secrets in a tracked file.

## 6. Dependency-ordered execution plan (approval required before backfill)

| Order | Action | Acceptance |
| --- | --- | --- |
| 0 | Snapshot current private/dirty repo and read-only registry. Freeze sealed cohort as-of + native DEX universe; compare with already stored fills/snapshots and existing Vike wallet evidence | No unverified portfolio, address, or selection backdated |
| 1 | Keep completed seven-day selected-wallet **main-DEX** pilot as baseline; create a **new xyz-only** metadata/column-byte budget for the same cohort and dates | No new S3 fill acquisition until `xyz` costs are preflighted; exact allowed source keys, source-state times and budgets |
| 2 | Acquire missing **core 10-column** fills with one query per DEX/day for entire cohort, local zstd immutable staging | 100% returned rows schema/identity validated, per-source SHA, no overwrite, no duplicates |
| 3 | Cross-check source vs existing canonical store by wallet/day and trade identity; collect evidence that any supposed no-trade day is source-complete | Source-positive missing store entries reported; empty results never equated to inactivity |
| 4 | Acquire per-DEX daily position anchors for `hyperliquid` and `xyz`; validate same-state compatibility and replay fills between anchors in Polars | Both allowed DEXes reconciled independently; ambiguous same-ms ordering and missing events block |
| 5 | Complete **`xyz` only** after its cost preflight, then expand historical dates for **`hyperliquid` + `xyz` only** following benchmark and scientific validity review | Exact two-DEX scope; exclude other HIP-3 DEXes; no blind 264-wallet × day scans |
| 6 | Add finance/exception data only for specific failed checks or intended follower-economics studies | Need justified per market-day; tx_hash and extra columns not fetched indiscriminately |
| 7 | Produce retrospective five-minute modeled source books and compare with actual prospective CWSA timing distribution, using existing PM-03/PM-04 interfaces once wired | Historical modeled timing and genuine first-known stay separate; qualifications remain BLOCKED pending actual independent evidence |

**Deployment rule:** This document is not a backfill permit. A running source observer, paper strategy, Guardian or trading service must not be changed or authorized by any data-acquisition task.

## 7. Cost/efficiency decision gates

1. **Benchmark S3 input**, not output. Capture cold remote wall-clock duration, number of HTTP GET/range requests and actual bytes transferred where instrumentable; never substitute local filtered Parquet size or compressed-column metadata as measured transfer. ETag/revision and cache status must be recorded.
2. **Fan out by DEX/day, not wallet.** A selected cohort of 14 may cost similar source bytes to one wallet on a date whose address statistics cannot prune row groups. Reuse cached filtered day data for all subsequent research.
3. **Minimize the first projection**: 10 core columns ~183 MB compressed chunks in the tested 590.5 MB source object, 16-column diagnostic ~320 MB, +tx_hash ~472 MB. These are **single-object examples**, not universal daily estimates.
4. **Deduplicate source reads across datasets.** The all fill tape includes the liquidation, ADL, builder and TWAP subsets. Only use specialized subsets if validating a separate exceptional event family; never append them to all.
5. **Budget before full-history scan.** `hyperliquid` and `xyz` daily fill objects have separate transfer/storage profiles; the measured seven-day numbers refer **only to `hyperliquid`**. Apply separate `xyz` S3 budgets and frozen wallet scope before any longer-history or 264-wallet expansion.
6. **Use Tokyo EC2 only if measured transfer cost makes it advantageous.** Process object/column chunks in ap-northeast-1, export only filtered compressed Parquet; account for EC2, S3 requests, transfer back to VPS and failure recovery. Existing VPS is sufficient for the pilot unless measured otherwise.
7. **Research validity remains separate.** Historical fills identify the trader's execution time, not our first-known receipt. Snapshot books are once per day; reconstructing the intervening books is conditional on complete fills and independent anchor parity. Backtest net follower PnL requires independent costs, quotes, funding, risk and modeled vs actual timing labels.

## 8. Reporting and stop conditions

Every run must produce **private** as-of timestamps, cohort SHA, source object keys/versions, exact query columns, transfer-cost provenance, gap/error status, retained row counts, duplicated IDs, anchor parity and no-trade UNKNOWN counts. Public/committed reports may contain aggregated counts and SHA references, **not** addresses or credentials.

Stop immediately on: unauthorized portfolio/version, unavailable/changed source object, schema mismatch, session credential failure, cost cap reached, unexplained same-market duplicate, missing fill-chain event, snapshot state disagreement, collateral-unit ambiguity, or an attempt to promote modeled receipts as actual evidence.

No passing test, zero-source-row day, historical fill-parity sample, retrospective PnL or daily snapshot makes the system scientifically qualified or grants trading authority.
