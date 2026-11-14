# Reservoir and vike as wallet-data sources (2026-11-12)

**Status:** source evaluation. Not a qualification, not a trading authorization.
Read [QUALIFICATION](QUALIFICATION.md) before interpreting anything built on this data.

Scope: what `s3://hydromancer-reservoir` (Hydromancer Reservoir) and the vike Data API /
Parquet archive provide, what each does and does not repair in the canonical wallet
store, and the access setup required to use them.

## 1. Verified source facts

### Reservoir (Hydromancer)

| Item | Value |
| --- | --- |
| Bucket | `s3://hydromancer-reservoir`, requester pays, region `ap-northeast-1` |
| Coverage | Hyperliquid markets from **2025-07-28**; each HIP-3 venue from its launch; updated daily |
| Fills | ~360 MB per day (vendor figure, 2026-10-18); liquidations ~1 MB/day |
| Candles | 1-second OHLCV from **2025-07-31**, ~44 MB/day; **all 1s candles ever ≈ 15.5 GB** |
| Snapshots | **daily, taken a few minutes after midnight UTC** — every trader's open positions, spot balances and account value; ~29 MB/day. Documented gap from late October to mid-December 2025 |
| Orderbook | **20 levels per side, every minute**, for perps, spot, HIP-3 and HIP-4, from **2025-12-15**; ~0.2–0.45 MB per market per day |
| Datasets | perp fills (`all`, `liquidations`, `adl`, `builder_fills`, `twap_fills`), spot fills, 1s candles, daily snapshots (`global/snapshots/{perp,spot,account_values}`), L2 orderbook |
| Dexes | `hyperliquid`, `xyz`, `flx`, `vntl`, `hyna`, `km`→`mkts`, `cash`, `para`, `io` |
| Fill schema | 27 columns incl. `realized_pnl`, `fee`, `fee_token`, `start_position`, `is_liquidation`, `liquidation_mark_px`, `twap_id`, `builder`, `deployer_fee` |
| Snapshot schema | `user`, `market`, `size`, `notional`, `entry_price`, `liquidation_price`, `leverage_type`, `leverage`, `funding_pnl`, `account_value`, `account_mode`, `date` |
| Access | no key; authenticated S3 GET with `s3_requester_pays=true` |
| Cost | requester pays egress: $0.114/GB after the 100 GB/month free allowance (vendor confirms the 100 GB); GET $0.0037 per 10,000 |
| Licence | CC BY 4.0 — commercial use with attribution to Hydromancer |

**Hydromancer REST API is separate from Reservoir.** Per-wallet history is served by
authenticated endpoints — `userFills`, `userFillsByTime`, **`userFunding`**,
`fundingHistory`, **`userNonFundingLedgerUpdates`**, `historicalOrders`,
`builderFills*`, `userTwap*` — with full time-range support and no 10,000-fill cap.
So Hydromancer does cover funding and ledger; the S3 archive simply does not carry
them.

Access is a **paid plan**, not a free key: Starter $300/month (500k tokens),
Growth $1,200 (3M), Scale $2,500 (15M), Enterprise custom; onboarding is by contact
(email/Telegram), and each request costs 1 token except the documented exceptions.
Some datasets are separate add-ons (e.g. `allFills` at $400, user-performance
endpoints, market-data snapshots). Requests authenticate with a Bearer token.

### vike

| Item | Value |
| --- | --- |
| Archive | `data.vike.io` Parquet, one file per stream per UTC day |
| Coverage | **from 2026-05-01**; position snapshots retained 1 year |
| Datasets | `fills`, `positions` (5-min snapshots, ~120M rows / ~1.6–2.2 GB per day), `positions_hourly`, `cohorts_hourly`, `wallets_hourly`, `latest` (current positions, ~32 MB, refreshed ~5 min); funding and ledger via API (`/v1/hyperliquid/wallets/{address}/funding`, `/ledger`), not in the archive |
| Fill schema | `wallet`, `fill_ts`, `coin`, `side`, `price`, `size`, `size_usd`, `fee`, `fee_token`, `is_maker`, `order_id`, `trade_id`, `crossed`, `closed_pnl`, `dex_name`, `start_position` (**NULL before 2026-09-29**) |
| Position schema | `snapshot_ts`, `state_ts`, `wallet`, `asset`, `direction`, `size_token`, `size_usd`, `entry_price`, `mark_price`, `liquidation_price`, `unrealized_pnl`, `leverage`, `margin_used`, `size_cohort`, `leverage_type`, `dex_name`, `liq_progress`, `account_value`, `pnl_cohort` |
| Access | free API key; archive links valid 7 days, downloads do not count against the 20,000 req/hour limit |
| Licence | personal use under vike Terms |

**PIT caveats that matter:** vike `snapshot_ts` is the *write* time of the ingestion
cycle; `state_ts` is the instant the state describes (typically 5–10 min earlier).
`account_value` is the **native perp account** value — it excludes builder-DEX equity
and money outside the perp account (`spot_usdc` is separate), and is `NULL` (never 0)
where no reading exists.

## 2. Access setup

### Reservoir

The account's managed SCP `AdvancedModeRegionRestrictionSecurityControlPolicy`
(`p-6c5l0t8b`) originally limited `aws:RequestedRegion` to
`{ap-southeast-2, us-east-1, us-west-2, unspecified}`, which denies
`ap-northeast-1`. `ap-northeast-1` was added to the `RegionFloor` statement on
2026-11-12; member accounts can now read the bucket. No other statement changed.

The wallet store already uses the same Hive convention
(`fills/wallet=<addr>/year=/month=/day=/data.parquet`), so both read the same way:

```sql
SELECT * FROM read_parquet('data/private/nav_hyperliquid_perp_daily/**/*.parquet',
                           hive_partitioning = true);
```

```python
import duckdb
con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute("SET s3_region='ap-northeast-1';")
con.execute("SET s3_requester_pays=true;")
con.execute("CREATE SECRET s (TYPE S3, KEY_ID ?, SECRET ?, SESSION_TOKEN ?)",
            [KEY, SECRET, TOKEN])   # from `aws configure export-credentials`
```

Working helper: `/home/quant/tmp/reservoir_query.py` (`--profile`, `--date`).

### vike

Free key from `vike.io/account?tab=api-keys`. Archive: resolve a signed link with
`GET /v1/hyperliquid/archive/url?dataset=<fills|positions|positions_hourly|cohorts_hourly|wallets_hourly>&date=YYYY-MM-DD`,
then download the returned URL. No download quota.

**Call REST directly.** The vike MCP server is not mounted in this environment
(removed 2026-11-12): its 74 tool schemas sat in the agent context on every turn.
The `vike-data` CLI is installed and convenient, but it speaks the same MCP
endpoint, so the direct REST call is the default for anything scripted or bulk.

| Call | Path |
| --- | --- |
| Wallet fills | `GET /v1/hyperliquid/wallets/{address}/fills?start=&end=&limit=5000` |
| OHLCV | `GET /v1/hyperliquid/ohlcv?symbol=&interval=1m&start=&end=&limit=5000` |
| Archive link | `GET /v1/hyperliquid/archive/url?dataset=&date=` |

Authenticate with header `X-API-KEY` (never a URL query token, never a CLI flag
that lands in `ps`). The dedicated key lives at
`/home/quant/.local/share/copytrade/vike-dedicated.env` (`0600`, parent `0700`):
source that file for the invocation and nothing else. Do not run
`vike-data login --api-key`, which puts the key in process arguments and
persists a second copy.

For one-off reads the CLI is fine once the env file is sourced:
`vike-data hl wallet <address> --view summary --json`,
`vike-data hl wallet-activity <address> --view fills --limit 5000 --json`,
`vike-data candles hl BTC --interval 1m --json`. It prints the tool's raw JSON
with no output cap (a 520-row fills page measured 220 KB whole).

The `copytrade-pm-vike-fills` CLI is a **live WebSocket subscription** with a
`--seconds` window, not a historical backfill — its REST recovery repairs gaps
inside a run and is not an arbitrary date-range client.

## 3. What each source changes for this repository

| Gap named in QUALIFICATION | Reservoir | vike | Status |
| --- | --- | --- | --- |
| No historical NAV tape | daily account values | `wallets_hourly.account_value`, hourly, native perp account only | **Partial** — not full wallet NAV (excludes builder-DEX equity and `spot_usdc`); `NULL` where unmeasured |
| No atomic whole-account book | daily position snapshots | `positions`, every 5 min, one row per (wallet, asset, direction) | **Partial** — observed at snapshot time, not a guaranteed-complete atomic book; anything opened and closed between snapshots is invisible |
| Position continuity (D2) | `start_position` per fill, from 2025-07-28 | `start_position`, NULL before 2026-09-29 | **Partial** |
| Look-ahead in cohort selection | — | `pnl_cohort` graded on fills strictly before the row's hour | **Improvement** for screening only |
| Unresolved intrabar order | 1-second candles | 1m–1d candles | **Unresolved** — finer bars narrow the window; they do not establish which side filled first inside a bar |
| PIT depth for participation sizing | 20-level L2 @ 1-min cadence | — | **Unresolved** — not executable depth: 1-min gaps, no queue position. Acceptable for small clips only as a coarse proxy that fails closed on gaps |
| History before 2026-05 | fills from 2025-07-28 | — | **Improvement** in coverage |
| Zero-fill / unreadable wallets | market-wide fills | market-wide fills | **Improvement** in acquisition reliability |

**Non-claims.** Neither source establishes causal first-known timing (D4), matched
follower outcomes (D5), executable follower economics, or any qualification state.
Fills carry the trader's execution time, not our receipt time. A replay built on
either source remains `HISTORICAL_ORACLE` / hindsight proxy under
[QUALIFICATION](QUALIFICATION.md).

## 4. Production state at 2026-11-12 (from SQL, not from documentation)

**Authoritative production inventory** — traced from the deployed systemd units and
their environment files, not from the research catalog:

| Source | Path | Count |
| --- | --- | --- |
| Deployed watchlist | `~/.local/share/copytrade/watchlist.db` (`subscriptions`, `TRACKER_DB_PATH`) | 264 |
| Deployed desired wallets | `~/.config/copytrade/tracker.env` → `TRACKER_DESIRED_WALLETS` | 264 |
| Ensemble cluster manifest | `release-backups/roster-20261104T073314Z/expert-universe-264.json` (`ENSEMBLE_CLUSTER_MANIFEST`) | 264 |
| Observation ledger | `~/.local/share/copytrade/observation.db` (`TRACKER_LEDGER_PATH`, `ENSEMBLE_LEDGER_DB`) | 259 distinct addresses in `position_checkpoints` |

The three production lists agree exactly (env-only 0, watchlist-only 0).

### The "~208" figure: two different filters

`projection.db: expert_equity` holds the live account value per wallet
(`wallet_id`, `account_value`, `observed_at`). 329 rows total: all 264 production
wallets plus 65 non-production rows.

**Freshness (as of 2026-11-12T05:02Z):** all 264 production rows were observed
between 04:44 and 05:02 UTC — under 20 minutes old. The 65 non-production rows are
stale (2026-11-04, ~189 h). Do not mix the two when counting.

| Filter on `account_value` (production only) | Wallets |
| --- | --- |
| **> 0** — the operator's "zero-equity excluded" count | **228** |
| **> $1,000** — the 2026-11-04 roster equity gate | **204** |
| == 0 (explicit zero, not missing) | 36 |
| < 0 | 0 |
| Missing row | 0 |

Both filters are fresh, so neither is a stale snapshot. They answer different
questions: 228 wallets hold *any* equity; 204 clear the $1,000 threshold used when
the current roster was screened. State which one a backfill targets.

Coverage of each set in the research store:

| Set | In store | `fills > 0` | Missing | `fills = 0` | `positions = 0` |
| --- | --- | --- | --- | --- | --- |
| > 0 (228) | 227 | 225 | 1 | 2 | 4 |
| > $1,000 (204) | 203 | 201 | 1 | 2 | 4 |

### The zero-equity wallets: a native-perp measurement gap, not empty wallets

`projection.db.expert_equity` holds the **native perp account** value. In unified and
portfolio-margin modes that account can read 0 while the money sits in spot collateral
or other portfolio branches.

Reconciled **simultaneously** on 2026-11-12 (07:27:59–07:28:24 UTC) against the
official Hyperliquid API (`clearinghouseState` + `spotClearinghouseState`) for all 35
production wallets whose live equity reads 0:

| Official state at the same instant | Wallets |
| --- | --- |
| perp account 0, spot USDC > 0 | **33** |
| perp account 0, spot USDC < 0 (borrowed against other collateral) | **2** |
| perp account > 0 | 0 |
| perp 0 and spot 0 | 0 |
| errors | 0 |
| open perp positions | 0 |
| spot USDC held by the 33 | **$1,578,134** |

The two negative-USDC wallets are `0xf0394ffb…` (−$306,155) and `0xff2c7c7e…`
(−$160,191) — portfolio-margin accounts borrowing USDC against other collateral, which
matches their Reservoir `portfolio_margin` rows (`pm_total_account_value` $290,780 and
$121,375 on 2026-11-10).

So the live zero is a native-perp-only measurement gap: 33 hold spot USDC, 2 borrow
against other collateral, none is an empty wallet, and none shows perp equity.

Reservoir's `global/snapshots/account_values` is the archive-side equivalent. Shape on
`date=2026-11-10`: 810,617 rows, 752,104 users, 8 dexes, 4 modes — `standard` 379,920
rows / 376,519 users, `dex_abstraction` 316,798 / 302,415, `unified` 112,486 / 72,446,
`portfolio_margin` 1,413 / 724. **Do not sum `account_value` across rows**: unified
values repeat on every dex row, portfolio-margin values are single-collateral balances
(negative when borrowed), and collateral tokens differ per row.

**Aggregation rules (per the schema):**
- `unified`: `account_value` is perp equity across every dex using that collateral plus
  its spot balance, and is **identical on each such row** — do not sum across dexes.
- `portfolio_margin`: `account_value` is that collateral token's balance, negative when
  borrowed; use `pm_total_account_value` for the account total.
- `standard` / `dex_abstraction`: `account_value` is equity on that dex; sum across dexes.
- `account_value` is denominated in the row's `collateral_token`, never converted to USD.

**What this is and is not worth.** These are **daily** snapshots at ~00:00 UTC, so they
give book state at a fixed clock once per day, not intraday. Under the default fixed-k
sizing, leader whole-account NAV is optional; this dataset improves selection and
capacity context, and it does not by itself qualify any backtest.

`data/private/wallet_store/catalog.sqlite` (492 wallets, 19,519 partitions) is the
**research canonical store**, not the production inventory. Overlap with production:

| Fact | Value |
| --- | --- |
| Production ∩ store | 261 |
| Production wallets **missing** from store | 3 |
| Production wallets with `fills=0` | 5 |
| Production wallets with `positions=0` | 5 |
| Store datasets | `fills`, `positions`, `equity`, `funding`, `ledger` (schema 1.0.0) |

Derive the missing addresses with SQL rather than copying them into tracked files
(see the repository rule against committing private wallet mappings):

```sql
-- in the store
SELECT address FROM wallets;
-- compare against TRACKER_DESIRED_WALLETS from tracker.env, or watchlist.db subscriptions
```

The "208" question is resolved: the operator's figure is the **non-zero-equity set**
(228 wallets with `account_value > 0`), not a separate roster. The $1,000 gate gives
204. Backfill scope must state which threshold it uses and record that choice before
any bulk pull.

### Absent partitions are not missing data

A wallet with no fills partition on a day may simply not have traded that day.
Presence counts cannot be turned into a coverage ratio without an independent
source. What is verifiable from the store alone:

| Measure | Value |
| --- | --- |
| Active wallets (> 0 equity) | 228 |
| Active wallets with any fills partition | 225 |
| Fill-days present | 6,429 |
| Days absent inside each wallet's own `first_ts → last_ts` span | 10,418 |
| Active wallets with > 10 absent days in span | 75 |

Those 10,418 absent days are **not** 10,418 missing days. Sampling 7 absent
(wallet, day) pairs against vike's independent fill tape (2026-11-12):

| Outcome | Count |
| --- | --- |
| Source returned fills → real store gap | 2 |
| Source returned no fills | 5 |

So 2 of 7 sampled absent days are real gaps. The other 5 returned an empty page,
which is **not** proof of inactivity: an empty response only shows no fills were
served for that window, and source coverage for that wallet-day was not separately
verified. n = 7 is too small to extrapolate a total; measure per wallet against a
source tape (vike `fills` for the wallet and day, or a completeness manifest) before
sizing any backfill. A wallet's `first_ts → last_ts` span is itself only a lower
bound on its true history.

## 5. Daily observed account equity (Hyperliquid dex)

Downloaded 2026-11-12 from `global/snapshots/account_values`, filtered to
`dex = 'hyperliquid'` and the 264 production wallets. **This is not "perp NAV":**
unified rows include that collateral's spot balance and repeat across dexes, and
portfolio-margin rows are single-token balances. Report the mode with any number.

| Item | Value |
| --- | --- |
| Output | `data/private/nav_hyperliquid_perp_daily/` — Hive layout `date=YYYY-MM-DD/data.parquet` (same convention as `wallet_store/fills` and `positions`, filename `data.parquet`), 418 partitions; `nav_hyperliquid_perp_daily.manifest.json` beside it records dir sha256, source, filter, counts, semantics and the not-covered list |
| Downloader | `/home/quant/tmp/download_nav.py` — writes the Hive dataset directly (staging dir → rename), monthly globs, per-month credential refresh, atomic per-month writes, resumable with date-set + roster validation |
| Rows | **79,185** |
| Days | **418** — exactly the 418 dates published by the source, no missing, no extra |
| Wallets | 264 (all production) |
| Span | 2025-07-29 → 2026-11-10 |
| Source gaps | 2025-08-01 (1 d) and 2025-10-25 → 2025-12-14 (51 d) — absent at source, not download failures |
| Duplicates | 0 `(date, wallet)` pairs |
| Collateral | USDC only on the `hyperliquid` dex |
| Wallets per day | min 112, mean 189.4, max 264 |
| Validation | every month checked against the source date list for that month (0 missing, 0 extra) and its wallet set against the current 264-wallet roster (0 outside) — 16/16 parts OK |
| Zero rows | 0 — every published row has a non-zero `account_value` |
| Columns | `date`, `wallet`, `dex`, `collateral_token`, `account_value`, `account_mode`, `is_unified`, `pm_ratio`, `pm_total_account_value` |

**A missing wallet/day row does not mean the wallet had no account value.** It means the
source published no row for that wallet on that day; whether that is an empty account, an
uncaptured account, or a source gap is **unverified** and must be reported as unknown.

Mode mix across the series: `unified` 37,077 rows / 233 wallets, `standard` 18,513 / 175,
`dex_abstraction` 18,110 / 152, `portfolio_margin` 5,485 / 40. A wallet can change mode
over time, so the mode is per row, not per wallet.

**Semantics — `account_value` is not uniformly "perp only":**

| `account_mode` | What `account_value` on the `hyperliquid` row means |
| --- | --- |
| `standard`, `dex_abstraction` | equity on this dex |
| `unified` | perp equity across every dex using this collateral **plus that collateral's spot balance** |
| `portfolio_margin` | that collateral token's balance, negative when borrowed; `pm_total_account_value` is the total across collateral tokens |

So the series is "Hyperliquid-dex account equity", which equals perp equity for
`standard`/`dex_abstraction` and includes spot collateral for `unified`. Report the mode
alongside any NAV number; do not present a mixed-mode series as pure perp equity.

**Not covered by this file:** vault equity, staked HYPE, intraday values. A wallet whose
capital sits in those reads lower here than its true NAV, and this file cannot tell you
by how much.

## 6. Store layout for backfill work

```
data/private/wallet_store/
  catalog.sqlite            # datasets, partitions, wallets
  fills/wallet=<address>/year=YYYY/...      # canonical fill partitions
  positions/wallet=<address>/year=YYYY/...  # canonical position partitions
```

Partition rows carry `sha256`, `fetched_at`, `source`, `source_cmd` — every backfilled
file must record its source and command. `blocked.json` records rejected rows; a
non-zero rejection count is a defect to investigate, not a number to suppress.

## 7. Open items

**Independent follow-up (2026-11-12 06:12 UTC):** See [the consumer/source investigation](DATA-SOURCE-INVESTIGATION-20261112.md). A read-only query of the local canonical catalog found 18,989 fills partitions / 6,408,133 rows and 530 positions partitions / 1,292,390 rows, with **zero registered equity, funding or ledger partitions**. The current-day projection returned 228 positive-equity and 36 zero-equity rows. These are as-of observations, not historical completeness measurements. The required 228-wallet-day source parity, account-mode census, position-book reconciliation and numeric funding semantics tests remain unresolved; **no new gap or inactivity total is claimed**. The vike archive index did independently return 288 five-minute position snapshots for 2026-11-10, and its BTC 1m query returned five consecutive minute bars. Do not reinterpret these as causal source receipts.


- Whether vike `positions` reconstructs a complete account book at snapshot time, or
  only the positions it observed. Unverified.
- Reservoir's daily `snapshots/perp` is taken **a few minutes after midnight UTC**
  (vendor documentation), so it is a daily book at a known clock, not an arbitrary-time
  one. Whether each file is atomic/complete is still unverified; row counts and
  non-null `account_value` do not establish it. A documented coverage gap exists from
  late October to mid-December 2025.
- Whether the 100 GB/month free egress allowance offsets requester-pays downloads.
  The vendor confirms the 100 GB allowance applies to AWS egress generally; check the
  first bill's `APN1-DataTransfer-Out-Bytes` line.
- Funding: **both vendors serve it, by different routes.**
  - Hydromancer REST API: `userFunding`, `fundingHistory` (paid endpoints, full time
    range). Not in the S3 archive — the immediate dataset prefixes under `by_dex/`
    (each of the ten dexes) and `global/` were enumerated with delimiter listings and
    none carries funding. Prefixes nested below dataset level were not enumerated, so
    this is evidence about the archive's dataset layout, not a full key scan.
  - vike: `hl_wallet_activity view=funding` (`GET /v1/hyperliquid/wallets/{address}/funding`)
    returns payment events with `ts`, `symbol`, `payment_usd` (signed from the
    wallet's side), `position_size`, `funding_rate`, `dex_name`. A query for
    2026-05-04 returned rows; earlier dates were **not** tested.
  - Reservoir's perp snapshot schema carries `funding_pnl` per position. Its semantics
    — cumulative since position open, reset on position change, or per-day — are
    **unverified**, so it must not be treated as a daily payment series by differencing
    until that is established against a funding event tape.
