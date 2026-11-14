# Data-source adequacy investigation — 2026-11-12

**Status: PARTIAL INVESTIGATION; NO QUALIFICATION / NO TRADING AUTHORIZATION.**
**Inspected at:** 2026-11-12 06:10–06:12 UTC (VPS clock); source archive/API observations in this session. **Checkout:** `6c07cc6d36099135881be27a072c426a52a24f24`, `main` 63 commits behind `origin/main`, dirty. This is an inspection of this checkout, **not** an audit of the remote HEAD or proof of the installed runtime. Existing untracked files were preserved. No ingestion/backfill was performed.

Evidence conventions: **VERIFIED** means observed in code, SQLite, files, or an API response here. **INFERRED** is a reasoned interpretation, not measured. **UNKNOWN** means no sufficient independent test. A missing partition is not inactivity. An empty API page is not proof of a source-complete day. Historical fill timestamps are **source executions**, not our first-known receipts.

## 1. Actual consumers versus canonical schema

**Critical architecture finding (VERIFIED):** repository search of `src`, `scripts`, and `dashboard` found the new canonical-store `scan` API used by `scripts/spot_check_wallets.py`; `scripts/backfill_zero_fills.py` and `scripts/migrate_wallet_store.py` use `ingest`, while `scripts/audit_and_remedy_wallets.py` reads catalog metadata. **No direct import of `copytrade_pm.wallet_store` was found in replay, PM-03, PM-04, forward-paper, dashboard or registry runtime modules.** Their native evidence contracts are *different*. Do not describe a store dataset as directly consumed by those services without an identified adapter/read path. Repository grep is not a live-process tracing result.

| Consumer | Dataset / exact fields inspected | Cadence | Mandatory? | Missing-data behavior |
| --- | --- | --- | --- | --- |
| Canonical store `scan`, audit | Catalog `partitions(kind,wallet,day,path,rows,bytes,sha256,fetched_at,source,source_cmd)`; Parquet columns as listed below | Partition/day | Mandatory for requested complete coverage | `scan` returns an empty typed frame when catalog absent; this **is not proof of inactivity**. Unknown schema version raises. No row cannot certify complete coverage |
| Replay, historical oracle (`pm_offline_oracle.py`, `pm_fill_replay`) | Original source fill time/identity/symbol/side/size/price, separately verified native 1m OHLCV (timestamp, symbol, OHLC, volume) | Fill event + 1 minute | Source and market mandatory for an admitted exact-minute study | Missing source, market day, atomic book or genuine first-known prevents contractual/financial promotion; historical oracle remains SCREEN_ONLY |
| PM-03 shadow account (`pm03_account.py`, `pm03_run.py`) | **Own** account event ledger: initial balance, targets, marks, executions, fees, funding, realized PnL, account risk; `Account.post_funding` books supplied amount/allocation | Event-driven; marks/risk at scenario timestamps | Supplied account/contract/risk evidence mandatory | Does not query canonical source wallet store; absent genuine evidence blocks real financial certification. It does not need historical leader L2 as an account-ledger column |
| PM-04 execution (`pm04_shadow.py`, `pm04_broker.py`) | PM-03 account state, pod targets, exposure, budget, quote/fill/broker reconciliation, fee/funding totals | Event/decision/fill, fresh quote | Mandatory for admission | Uses same PM-03 ledger, not a new wallet-store funding/ledger reader. Unreconciled or stale broker/market evidence blocks |
| Forward paper / V4 position-first | Authenticated selected-account complete perp position books including native DEX/asset, signed native quantity, mark; source event + **local receipt** clocks; independent market quotes/candles; frozen k, follower account and risk | Source transition and due T+300 seconds, fresh quote/decision | Complete position book and independent first-known essential; wallet fills optional consistency evidence | Baseline, gaps, unverifiable flat or incomplete scope do not generate valid entry. Missing book/quote/finance blocks; reductions and protective exits follow their separate policy. See `AGENTS.md` and `docs/decisions/2026-11-08-position-first-t300.md` |
| Dashboard (`scripts/dashboard_server.py`) | `projection.db` `expert_equity(wallet_id,account_value,observed_at)` and registry/ops DB, plus independent source metrics | Read-time, bounded by source freshness | Optional for display, **not** production finance | Must label unavailable/stale data; this dashboard is **not** a direct `wallet_store.scan` consumer |
| Registry | Private metadata DB: wallet identity, membership, exclusions, signatures and portfolio seals; not source OHLCV | Selection/read-time | Mandatory for selection validity | Provenance/integrity failure blocks selection; registry is not a historical funding/equity tape |

### Exact canonical-store field definitions (VERIFIED in `src/copytrade_pm/wallet_store/schema.py`)

- `fills`: `ts,wallet,symbol,dex,side,size_token,price,size_usd,fee,fee_token,is_maker,order_id,trade_id,crossed,closed_pnl,start_position,source,source_ts`; `start_position` nullable.
- `positions`: `snapshot_ts,wallet,symbol,dex,direction,size_token,size_usd,entry_price,mark_price,liquidation_price,unrealized_pnl,leverage,leverage_type,margin_used,opened_at,pnl_cohort,size_cohort,liq_progress,source`; several diagnostic fields nullable.
- `equity`: `ts,wallet,account_value,perp_account_value,margin_used,cash_balance_usd,total_unrealized_pnl,account_mode,source`; strict schema has non-null numeric fields, so unknowns may not silently become zero.
- `funding`: `ts,wallet,symbol,payment_usd,rate,source`.
- `ledger`: `ts,wallet,event_type,amount_usd,fee_usd,counterparty,tx_hash,source`.

This is the *storage/write schema*, not evidence that each consumer reads all fields. **UNKNOWN:** an exhaustive dynamic trace of fields read by all deployed processes; the six consumer boundaries are not direct canonical-store readers.

## 2. Source adequacy and measured local inventory

Read-only SQL executed:

```sql
SELECT kind,COUNT(*) AS partitions,SUM(rows) AS rows,
       ROUND(SUM(bytes)/1e9,3) AS gb,COUNT(DISTINCT wallet) AS wallets,
       MIN(day),MAX(day)
FROM partitions GROUP BY kind ORDER BY kind;
```

`data/private/wallet_store/catalog.sqlite` yielded (2026-11-12 06:12 UTC):

| Dataset | Partitions | Rows | GB | Wallets | Recorded day range |
| --- | ---: | ---: | ---: | ---: | --- |
| fills | 18,989 | 6,408,133 | 0.388 | 485 | 2025-05-25 to 2026-11-11 |
| positions | 530 | 1,292,390 | 0.026 | 469 | 2026-08-01 to 2026-10-01 |
| equity | 0 | 0 | 0 | 0 | missing |
| funding | 0 | 0 | 0 | 0 | missing |
| ledger | 0 | 0 | 0 | 0 | missing |

The three missing dataset directories were independently checked and absent. **IMPORTANT:** 2025-05-25 local fill history predates vike's stated May 2026 archive start and Reservoir's July 2025 history; provenance must be checked partition by partition. No source-wide completeness claim is justified by local row totals.

| Required dataset | Reservoir | vike | Gap / confidence |
| --- | --- | --- | --- |
| Raw fills / trade IDs / start position | **Available in documented S3 fill schema**, historical from 2025-07-28 | **Available** in archive, 2026-05-01 onward; `start_position` null before 2026-09-29 | Both historical-oracle timestamps; neither supplies first-known receipt. Full-dex and wallet-day parity untested in this run |
| Open positions | **Partial:** daily perp snapshots | **Partial:** 5-minute position snapshots (independent archive index confirms 288 snapshots on 2026-11-10) | Both too coarse for intermediate transitions; neither independently proven complete atomic selected-account book |
| Equity / mode | **Partial:** daily account/snapshot fields incl. mode | **Partial:** hourly `wallets_hourly.account_value` is native perp only | Neither supplies independently reconciled total wallet collateral/account-mode history |
| Funding payments | **Absent from documented Reservoir prefixes**; `funding_pnl` snapshot semantics UNKNOWN | **Available as per-wallet payment event API** by published contract | Earliest complete funding history, zero-hour semantics, event pagination and per-wallet coverage unverified |
| Nonfunding ledger | UNKNOWN / absent documented canonical ledger | **API exists**, `hl_wallet_activity(view=ledger)` | Pagination and scope reconciliation unverified |
| Native market OHLCV | **1-second documented candles** | **VERIFIED 1-minute BTC**: `hl_ohlcv(symbol=BTC,interval=1m,start=2026-11-10T00:00:00Z,end=2026-11-10T00:05:00Z,limit=5)` returned five ascending contiguous minute bars | Need matching instrument/DEX/day completeness; a candle is not an executable quote |
| Historical L2 orderbook | **Documented 20 levels/one-minute snapshot** | UNKNOWN/absent in inspected archive | Not a stated input requirement for fixed-k target *calculation*; not proof of market impact or fill capacity |
| Causal first-known receipt | **Absent** | **Absent** | Historical sources cannot backdate a local receipt |

vike archive index response independently listed on 2026-11-10: fills 14,945,580 rows / 467,087,544 bytes, positions 119,650,759 / 1,624,280,801 bytes and 288 snapshots, `positions_hourly` 350,104,749 bytes and `wallets_hourly` 105,271,307 bytes. These are provider-wide file sizes, **not downloaded data**.

## 3. Open questions: evidence, result, conclusion

### (a) Reservoir `funding_pnl` semantics

- **Test required:** choose one wallet and market whose notional changed on multiple days; query consecutive Reservoir `snapshots/perp` `(date,user,market,size,funding_pnl)`, then sum vike wallet funding `payment_usd` over each corresponding UTC interval. Record differences against event sums and detect reset.
- **Result:** **UNKNOWN — no numeric matched-position test completed.** Prior schema inspection confirms the field exists, not its cumulative/daily/reset interpretation.
- **Conclusion:** Never difference `funding_pnl` as an hourly/daily payment without independently proven semantics.

### (b) vike zero-payment funding hours and earliest date

- **API contract verified:** `hl_wallet_activity(view=funding,address,start,end,limit,cursor)` supplies signed `payment_usd` payment rows. An earlier inspection found rows dated 2026-05-04, but that is **not proof of earliest historical availability**.
- **Attempt 1:** the installed vike CLI response failed local `jq` parsing (`NO_PARSE`) for all three tested days; this was an output parsing failure, not evidence of zero events.
- **Attempt 2 — VERIFIED direct MCP API results** (one wallet chosen from the 2026-11-10 local fill partition; wallet identity not printed): `hl_wallet_activity(view=funding,address=<private>,start=YYYY-MM-DDT00:00:00Z,end=next-dayT00:00:00Z,limit=5000)` returned **0 rows / null nextCursor** on **2026-05-04**, **0 rows / null nextCursor** on **2026-08-04**, and **25 rows / null nextCursor** on **2026-11-10**. The latter includes an event stamped **2026-11-11T00:00:00Z** (the endpoint appears to include the upper boundary). The top three descending payment records were `2026-11-11T00:00:00Z: -$0.817999, size 62.61`; `2026-11-10T23:00:00Z: -$0.812713, size 62.61`; `2026-11-10T22:00:00Z: -$0.828721, size 62.61`. All returned 25 rows are **served events**, not proof of zero-filled hours. This also demonstrates that API time-bound semantics need explicit end filtering before wallet-day joins.
- **Conclusion:** Funding **is demonstrably served for this wallet on 2026-11-10**; the two empty responses prove only no rows served for this wallet/window. Whether zero-payment hours are omitted and the true earliest funding service date remain **UNKNOWN**.

### (c) vike position snapshot completeness

- **Source evidence:** vike archive advertises every 5-minute snapshot of observed open positions and the 2026-11-10 index reported 288 snapshots.
- **Missing test:** align one vike `state_ts` to a contemporaneous native `allDexsClearinghouseState` / complete DEX census, or authoritative same-time store book; compare all `(dex,asset,direction,quantity)` keys, including zero-position absence semantics.
- **Conclusion:** **UNKNOWN** whether an archive time slice is an independently complete account book. The 5-minute cadence alone cannot establish completeness.

### (d) Native perp zero versus unified/portfolio-margin equity

```sql
SELECT
  SUM(CAST(account_value AS REAL)>0) AS positive,
  SUM(CAST(account_value AS REAL)=0) AS zero,
  MIN(observed_at),MAX(observed_at)
FROM expert_equity WHERE observed_at >= '2026-11-12';
```

- **VERIFIED:** 228 positive and 36 zero in the current-day projection; observed times range 2026-11-12T05:35:57Z to 06:12:37Z. This is a projected expert-equity count, not a verified account-mode classification.
- **VERIFIED:** canonical-store `equity` has **zero partitions**, thus no stored equity rows for these wallets.
- **UNKNOWN:** number of 228 active wallets whose *vike native perp value* is zero while collateral lives in unified/portfolio margin. Requires joining account-mode evidence and time-matched vike hourly values; cannot infer it from 36 projected zeros.

### (e) Real fill gaps among 228 positive-equity production wallets

- **Required denominator:** all wallet-days in a **declared checked interval** for the 228 production wallet IDs, not just days with local partitions.
- **Method:** validate complete vike day index and pagination, filter archive fills for those IDs, dedupe by venue/dex/trade identity, compare per `wallet,UTC date` against full local canonical IDs. Source-positive/store-absent is a real gap. Both source and store empty is `NO_ROWS_SERVED`, **not certified inactivity** without verified complete tape. Record unmatched rows, duplicates, and source-only/store-only counts.
- **This session:** **0 wallet-days independently compared** against fully fetched vike fills. **0 newly verified real gaps; inactive days UNKNOWN.** This is not a zero-gap finding. The earlier report's sample of 7 absent days with 2 source-positive store gaps is prior evidence, not a 228-wallet census.
- **Conclusion:** The requested full-wallet-day coverage census is **not completed**; no percentage or inactive-day count is defensible.

### (f) Reservoir L2: depth/cadence/necessity

- **Previous documented S3 schema evidence:** 20 levels at 1-minute snapshot cadence; **not independently requeried in this run**.
- **Code evidence:** fixed-k target sizing uses native quantity times source mark and independent follower quote; historical replay uses 1-minute native bars. No direct canonical-store L2 consumer was found in the searched modules.
- **INFERRED:** L2 is **not a mandatory input to calculate fixed-k target or an OHLCV screening replay**. For certified executable fills/market impact, minute-sampled depth is inadequate by itself. Exact runtime L2 dependence still needs a call-site audit of active quote adapters.

## 4. Concrete gaps and blocked claims

| Dataset/evidence | Consumer | Missing | Blocks |
| --- | --- | --- | --- |
| Complete position books / DEX scope | Forward paper | Independent atomic completeness at receipt time | Entry/source admission |
| Source receipts | Forward paper, qualification | Independent first-known receive/commit clocks | Any causal historical first-known claim |
| Historical funding payments | PM-03/04 finance and matched follower economics | No canonical partitions; API completeness unverified | Reconciled account/follower returns |
| Historical collateral/account-mode | Equity-relative legacy replay, historical account attribution | No equity partitions; native perp hourly insufficient | Whole-account NAV fidelity |
| Historical ledger flows | Account reconciliation | No canonical ledger partitions | Reconcile deposits/transfers and PnL |
| Per-wallet-day fill parity | Historical replay/source reliability | Full 228-wallet comparison incomplete | Defensible backfill scope/coverage |
| Market identity/quotes/depth | Execution economics | Matching DEX and independently attainable follower fill evidence | Certified slippage/capacity/market impact |
| Snapshot funding semantics | Funding analysis | Reservoir cumulative/reset/day test incomplete | Any numeric differential based on `funding_pnl` |

## 5. Recommended investigation/acquisition order (NOT authorized backfill)

1. **Index and provenance only**: freeze live 228-member set/as-of, catalog hashes and the vike per-day completeness manifest. Very small metadata; vike API metering applies, archive downloads unmetered by described provider terms. Do not count absent rows as inactivity.
2. **Verify fills** using one vike market-wide UTC-day archive at a time and only extract target wallet records. **Measured example:** 2026-11-10 0.467 GB/provider-wide fills. A 30-day planning extrapolation at that day's size is **~14.0 GB**, not an estimate grounded in 30 observed day sizes; actual daily archive volumes vary. No download yet.
3. **Position completeness proof** using a narrowly chosen current `latest` sample and native same-time book; then selected 5-minute daily archives. **Measured example:** 2026-11-10 1.624 GB/day; 30 times that day **~48.7 GB** (scenario only).
4. **Wallet-hourly account-value and account-mode audit**. **Measured example:** 2026-11-10 `wallets_hourly` 0.105 GB; 30 times **~3.16 GB**. Do not label native-perp equity whole-account NAV.
5. **Per-wallet funding and ledger API** with paginated proof and native reconciliation; byte budget **UNKNOWN** until bounded sample. Do not fill missing intervals with zero.
6. **Reservoir historical fills/1s bars** only for proven pre-May-2026, schema or intraminute gaps. Existing source evaluation measured ~0.221 GB/day of all-perp fills on 2026-03-22; 30 days at that measured day's size is **~6.63 GB**. 1-second candles and L2 have no measured daily GB in this investigation; **UNKNOWN** rather than fabricated cost estimates.
7. **Reservoir L2** only if an explicit execution-economics test demonstrates need. Snapshot depth is not a transaction/queue tape.

**Cost:** Reservoir is requester-pays, region `ap-northeast-1`; the source evaluation quotes **~$0.114 per GB after 100 GB/month** and GET **$0.0037/10,000 requests**. Actual free-tier applicability/billing **unverified**, so do not treat the allowance as guaranteed. For an illustrative **120 GB** billable transfer with 100 GB actually free, marginal transfer estimate is **20 × $0.114 = $2.28**, excluding other costs. vike archive signed-link downloads are described as unmetered; API calls may still be rate-limited.

## 6. Explicit nonclaims

- No historical vendor fill timestamp is a local receipt timestamp.
- No positive scientific qualification, authenticated follower PnL, contract PASS/BREACH, deployment or trading authority follows from this investigation.
- The report is **incomplete on requested matched-source experiments (a–e)** and a full field-level dynamic runtime audit. Its unknowns must remain unknown.
- No raw wallet address list, credentials, private files, or account-specific details are included.
