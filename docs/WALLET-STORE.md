# Canonical Wallet Store Architecture & Guide

**Status:** OPERATIONAL
**Storage Root:** `data/private/wallet_store/` (Mode `700`, files Mode `600`)
**Catalog:** `data/private/wallet_store/catalog.sqlite`
**API Package:** `src/copytrade_pm/wallet_store/`

---

## 1. Executive Summary & Design Principles

The canonical wallet store consolidates historical and real-time wallet-level trading data (fills, positions, equity, funding, and ledger) into a single, immutable, Hive-partitioned Parquet storage engine.

### Core Tenets
1. **Immutable Partitions:** Once written, a partition file is never overwritten. Updates or collisions with different content append `data.<sha8>.parquet` alongside, recording both in the SQLite catalog.
2. **Crash-Safe Writes:** All writes go to `data.parquet.tmp`, undergo POSIX `fsync`, and are atomically renamed into place.
3. **Strict Permissions:** Directories are mode `700` (`rwx------`); every partition file and sidecar is mode `600` (`rw-------`). The entire `data/` directory is gitignored.
4. **Boundary Strictness:** Strict Pydantic models (`Fill`, `Position`, `Equity`, `Funding`, `Ledger`) enforce `Decimal` at ingest boundaries with `extra="forbid"`, preventing floating-point rounding errors and silent schema drift. Parquet files are written with explicit Polars schemas (`pl.Schema`).
5. **No Intra-Store Aggregation:** Exactly one row per event. Rollups, daily metrics, and cumulative exposure are computed on read using `scan()` lazy frames.
6. **Zero Guessing Adapters:** Distinct adapters handle source variance (`from_hyperx_camel`, `from_hyperx_snake`, `from_vike`). Ingestion fails closed upon unexpected schemas.

---

## 2. Canonical Layout

Partitions are structured by dataset, wallet address (lower-case 0x-hex), and UTC calendar date:

```
data/private/wallet_store/
  fills/
    wallet=0x<address>/year=YYYY/month=MM/day=DD/data.parquet
  positions/
    wallet=0x<address>/year=YYYY/month=MM/day=DD/data.parquet
  equity/
    wallet=0x<address>/year=YYYY/month=MM/day=DD/data.parquet
  funding/
    wallet=0x<address>/year=YYYY/month=MM/day=DD/data.parquet
  ledger/
    wallet=0x<address>/year=YYYY/month=MM/day=DD/data.parquet
  .metadata/
    <dataset>/<wallet>/<YYYY-MM-DD>.json
  catalog.sqlite
  dedup_report.json
  blocked.json
```

### Partitioning Rules
- **Date Boundary:** Partitioned by the UTC calendar day of the event timestamp (`ts` for fills/funding/ledger, `snapshot_ts` for positions/equity). A timestamp at midnight exactly (`00:00:00.000000+00:00`) belongs to that calendar day.
- **Compression:** Parquet with `zstd` compression.
- **Sidecar Metadata:** Every partition has a JSON provenance sidecar in `.metadata/<dataset>/<wallet>/<day>.json` recording `source`, `ingested_at`, `row_count`, `file_sha256`, and schema details.

---

## 3. Canonical Schemas

### 3.1 Fills (`fills`)
| Field | Type | Description |
|---|---|---|
| `ts` | `Datetime("ms", "UTC")` | Event execution timestamp |
| `wallet` | `String` | 42-character lowercase hex address (`0x...`) |
| `symbol` | `String` | Raw exchange symbol (`BTC`, `ETH`, `xyz:TSLA`, `@107`) |
| `dex` | `String` | `HL` for main DEX, `SPOT` for spot/numeric, else symbol prefix (`XYZ`) |
| `side` | `String` | `buy` or `sell` (normalized from `B`/`A` or `buy`/`sell`) |
| `size_token` | `Float64` | Executed quantity in base tokens |
| `price` | `Float64` | Execution price in USD |
| `size_usd` | `Float64` | Total notional executed (`size_token * price`) |
| `fee` | `Float64` | Execution fee paid |
| `fee_token` | `String` | Fee currency (e.g. `USDC`) |
| `is_maker` | `Boolean` | True if maker liquidity |
| `order_id` | `String` | Order identifier (stored as string; exceeds i64) |
| `trade_id` | `String` | Execution trade identifier (stored as string; exceeds i64) |
| `crossed` | `Boolean` | True if crossed book |
| `closed_pnl` | `Float64` | Realized PnL from position closure |
| `start_position` | `Float64` (Nullable) | Position size immediately prior to fill (if published) |
| `source` | `String` | Data provenance (`vike`, `hyperx`, `dextra`, `archive`) |
| `source_ts` | `String` | Raw verbatim timestamp string as received |

### 3.2 Positions (`positions`)
| Field | Type | Description |
|---|---|---|
| `snapshot_ts` | `Datetime("ms", "UTC")` | Snapshot timestamp |
| `wallet` | `String` | 42-character lowercase hex address |
| `symbol` | `String` | Instrument symbol |
| `dex` | `String` | DEX identifier (`HL`, `XYZ`, etc.) |
| `direction` | `String` | `long` or `short` |
| `size_token` | `Float64` | Unsigned position size in base tokens |
| `size_usd` | `Float64` | Unsigned notional USD |
| `entry_price` | `Float64` | Average entry price |
| `mark_price` | `Float64` | Snapshot mark price |
| `liquidation_price`| `Float64` (Nullable) | Estimated liquidation price |
| `unrealized_pnl` | `Float64` | Unrealized PnL at mark |
| `leverage` | `Float64` | Effective or configured leverage |
| `leverage_type` | `String` | Margin mode (`cross` or `isolated`) |
| `margin_used` | `Float64` | Margin allocated to position |
| `opened_at` | `Datetime("ms", "UTC")` (Nullable) | Timestamp position was initiated |
| `pnl_cohort` | `String` (Nullable) | PnL cohort classification |
| `size_cohort` | `String` (Nullable) | Size cohort classification |
| `liq_progress` | `Float64` (Nullable) | Proximity metric to liquidation |
| `source` | `String` | Source provider |

### 3.3 Equity, Funding & Ledger
- **`equity`:** `ts`, `wallet`, `account_value`, `perp_account_value`, `margin_used`, `cash_balance_usd`, `total_unrealized_pnl`, `account_mode`, `source`.
- **`funding`:** `ts`, `wallet`, `symbol`, `payment_usd` (signed from wallet's perspective), `rate`, `source`.
- **`ledger`:** `ts`, `wallet`, `event_type`, `amount_usd`, `fee_usd`, `counterparty`, `tx_hash`, `source`.

---

## 4. SQLite Catalog Specification

Located at `data/private/wallet_store/catalog.sqlite` (Mode `600`), the catalog provides fast query routing and indexing without filesystem scanning:

### Tables (verified against the live catalog 2026-11-12)

1. **`datasets`** — `kind` (PK), `schema_version`, `schema_sha256`, `description`.
   Registered kinds: `fills`, `positions`, `equity`, `funding`, `ledger`.

2. **`partitions`** — `kind`, `wallet`, `day`, `path`, `rows`, `bytes`, `sha256`,
   `fetched_at`, `source`, `source_cmd`; PK `(kind, wallet, day, path)`.
   Note the column names: `kind` (not `dataset`), `path` (not `file_path`),
   `rows` (not `row_count`), `sha256` (not `file_sha256`), `fetched_at`
   (not `ingested_at`).

3. **`wallets`** — `address` (PK), `first_ts`, `last_ts`, `fills`, `positions`, `sources`.

> **Registered is not populated.** `equity`, `funding` and `ledger` exist in `datasets`
> but had **zero partitions** on 2026-11-12; only `fills` and `positions` hold data.
> Check `SELECT kind, count(*) FROM partitions GROUP BY kind` before assuming coverage.

---

## 5. Python API Usage

The canonical interface is located in `copytrade_pm.wallet_store`:

```python
from copytrade_pm.wallet_store import scan, coverage, verify, ingest
```

### 5.1 Scanning Data (`scan`)
Scans partitions via catalog filtering and returns a Polars `LazyFrame`:

```python
# Scan fills for a specific wallet across a date range
lf = scan(
    kind="fills",
    wallets=["0xe2823659be02e0f48a4660e4da008b5e1abfdf29"],
    start="2026-08-01",
    end="2026-08-31",
)

# Collect or filter lazily
df = lf.filter(pl.col("symbol") == "BTC").collect()
```

### 5.2 Checking Coverage (`coverage`)
Returns a summary DataFrame with min/max timestamps and row counts per wallet:

```python
cov_df = coverage()
print(cov_df)
```

### 5.3 Physical Store Verification (`verify`)
Audits all registered partitions on disk for file existence, POSIX `600` permissions, row count matches, and SHA-256 integrity:

```python
problem_count = verify()
assert problem_count == 0, f"Found {problem_count} integrity errors in wallet store"
```

---

## 6. How to Ingest a New Wallet

To fetch and ingest real-time activity for a new wallet using `vike-data`:

### Step 1: Extract Activity via CLI
```bash
# Fetch fills in JSON format
/home/quant/.hermes/node/bin/vike-data hl wallet-activity 0x<address> --view fills --limit 5000 --json > /tmp/fills.json
```

### Step 2: Normalize and Ingest in Python
```python
import json
import polars as pl
from copytrade_pm.wallet_store.adapters import from_vike
from copytrade_pm.wallet_store.schema import FILLS_POLARS_SCHEMA
from copytrade_pm.wallet_store.store import ingest

wallet_addr = "0x<address>".lower()

with open("/tmp/fills.json") as f:
    raw_data = json.load(f)

# Parse through strict model
fills = [from_vike(row, wallet=wallet_addr, source="vike") for row in raw_data["fills"]]

# Group by UTC day and write partitions
day_groups = {}
for fill in fills:
    day_str = fill.ts.strftime("%Y-%m-%d")
    day_groups.setdefault(day_str, []).append({
        "ts": fill.ts,
        "wallet": fill.wallet,
        "symbol": fill.symbol,
        "dex": fill.dex,
        "side": fill.side,
        "size_token": float(fill.size_token),
        "price": float(fill.price),
        "size_usd": float(fill.size_usd),
        "fee": float(fill.fee),
        "fee_token": fill.fee_token,
        "is_maker": fill.is_maker,
        "order_id": fill.order_id,
        "trade_id": fill.trade_id,
        "crossed": fill.crossed,
        "closed_pnl": float(fill.closed_pnl),
        "start_position": float(fill.start_position) if fill.start_position is not None else None,
        "source": fill.source,
        "source_ts": fill.source_ts,
    })

for day_str, rows in day_groups.items():
    df = pl.DataFrame(rows, schema=FILLS_POLARS_SCHEMA)
    ingest("fills", wallet_addr, day_str, df, source="vike")
```

---

## 7. Migration Provenance & Audit

All 11 historical source datasets across the workspace were migrated and reconciled with 100% exact row accountability:

- **Fills Reconciled:**
  - `vike`: 20,736 read == 20,736 loaded + 0 dupes + 0 rejected
  - `archive`: 1,860,206 read == 1,860,020 loaded + 186 dupes + 0 rejected
  - `hyperx`: 813,606 read == 775,896 loaded + 37,710 dupes + 0 rejected
  - `dextra`: 3,872,284 read == 3,743,888 loaded + 128,396 dupes + 0 rejected
  - **Total Fills Loaded:** 6,400,540 (169,198 duplicate rows deduplicated by provenance priority `vike > archive > hyperx > dextra`).
- **Positions Reconciled:**
  - `vike`: 170,449 read == 170,352 loaded + 97 dupes + 0 rejected
  - `archive`: 1,124,847 read == 1,122,038 loaded + 2,809 dupes + 0 rejected
  - **Total Positions Loaded:** 1,292,390 (2,906 duplicates removed).
- **Store Scale:** 19,261 partition files spanning 480 unique wallets.
- **Physical Verification:** `verify()` verified all 19,261 partitions: **0 errors**.
