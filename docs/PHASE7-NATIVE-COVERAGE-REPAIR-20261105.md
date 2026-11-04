# Phase 7 native-minute coverage repair — 2026-11-05

**Scope:** Retrospective Phase 7 source-position-chain *market-data coverage*, 2026-08-05 00:00 to 2026-11-03 00:00 UTC (exclusive). Corrects the **dated** Stage-1 2026-11-04 evidence in [the native interval report](PHASE7-NATIVE-MINUTE-EXPOSURE-20261104.md) and [Phase 7 conditional decision report](PHASE7-FINAL-RESEARCH-REPORT-20261104.md). No historical first-known receipt, complete source account NAV/book or follower economics was recovered.

## Root-cause finding: S035-ENA 22.88% was an audit artifact

The denominator always meant **792,866 reconstructed, nonoverlapping-within-coin position-chain leg-minutes across 26 main-perp coins**, not 792,866 distinct wall-clock minutes or fills. It is not continuous whole-wallet market coverage: unknown pre-first/after-last fill holdings, same-millisecond ambiguity, HIP-3, collateral/funding and vendor data limitations remain excluded.

1. **Unjustified five-coin scan cap.** The initial audit read only the top five source-interval coins (330,081 of 792,866 leg-minutes, or **41.63%**), then divided by **all 26 coins**. The other 21 coins were silently counted as missing, even where canonical native bars existed. A bounded 40-coin default now scans all 26 for S035-ENA, reports omitted leg-minutes explicitly, and allows a targeted wallet audit without making false claims about unscanned peers.
2. **Cross-partition Polars schema incompatibility hidden as missing market.** The legacy `native_marks()` scanned all Parquet day files together, even though some days have seven canonical columns and others have nine enriched columns (and time units vary). A broad exception handler returned `None` for the *entire coin*. For example, CHIP, ZRO, NIL and ETHFI had valid source days but failed the monolithic scan. The repaired reader uses the **existing** `copytrade_pm.pm_offline_market._verified_day` independently per UTC day: verifies venue, DEX, symbol, Parquet SHA-256, sidecar provenance, OHLC consistency, time alignment and uniqueness. Only complete **1,440-minute** source-backed days pass. No fill-forward and no future-bar substitution.
3. **Real source-day gaps.** Existing CHD 1m candle manifests support historical PENDLE, PAXG, WIF, LDO, FIL and TRB. A bounded backfill produced **102 strictly complete candle days** for those six default-perp markets. Trade archives independently supplied **15 more complete days** in PENDLE/PYTH, while one already-installed PYTH day was left intact. The two incomplete PENDLE trade-derived days (2026-10-24 and 2026-10-25, each **1,439** of 1,440 minutes) were **not** admitted. Neither existing native market days nor wallet fill JSONs were overwritten.

### S035-ENA same-denominator reconciliation

| Distinct frozen research evidence cut | Native-verified source leg-minutes | Source leg-minutes in denominator | Verified fraction |
|---|---:|---:|---:|
| Prior 2026-11-04 V2 five-coin audit | 181,390 | 792,866 | **22.88%** |
| All 26 coins; repaired reader, before market acquisition | 663,715 | 792,866 | **83.71%** |
| Above + 102 complete CHD candle days | 776,931 | 792,866 | **97.99%** |
| Above + 15 complete CHD trade-derived days | **789,986** | **792,866** | **99.64%** |

**Unverified remaining:** **2,880 (0.36%)** source-chain leg-minutes, entirely PENDLE during Oct 24–25. Both trade-derived days lack one native one-minute observation. We exclude each incomplete *day* under the conservative complete-day contract rather than infer zero-volume candles or interpolate missing prices. These are valid unknowns; the precise two missing individual minutes should not be confused with 2,880 minutes lacking raw trades.

The original S035 raw-fill source hash remains `c86377cca8fce3c3e8cbd0de84063b427273d0959903bf0f7616da9d41b4d772`; **no fill download/reconstruction source was changed**.

### Eight wallets: superseding original 10 + 10 shortlist *data coverage* conclusion

| Wallet | Old top-five coverage | All-main-perp, strict native complete-day coverage |
|---|---:|---:|
| ACT33 | 100.00% | **100.00%** |
| C021-NEAR | 47.22% | **100.00%** |
| S053-HYPE | 93.97% | **99.87%** |
| S035-ENA | 22.88% | **99.64%** |
| ACT40 | 60.59% | **93.97%** |
| N059-BNB | 47.77% | **93.20%** |
| W017 | 26.00% | **89.25%** |
| W030 | 69.96% | **86.13%** |

The **earlier claim that none of the 10 three-wallet and 10 five-wallet shortlist combinations has all members above an illustrative 80% known-chain-native-data threshold is superseded**. With the corrected bounded full-coin read and new source days, **all 20 pass that *coverage-only* diagnostic**. Do not reinterpret it as 80% continuous wallet-book coverage, a new qualification rule, independent discovery, predictive skill or a portfolio recommendation. Their screen ranks are still hindsight-derived from at least 1,875 exploratory combinations and are *not* OOS economic evidence.

## Immutable owner-private evidence and reproducibility

| Evidence path (under `/home/quant/.local/share/copytrade/reports/`) | SHA-256 |
|---|---|
| `phase7_s035_full_coin_native_chain_20261105_v1.json` — code-only repair | `432e2859786d0b465a6fbab43e1f3e0037fa3fe7523e5d7eebf96093f8c02327` |
| `phase7_s035_full_coin_native_chain_20261105_v2.json` — complete candle backfill | `7242127f195fffa476ad829fc84920629fd2a7a3f1f7176de8eea9ec1b712322` |
| `phase7_s035_full_coin_native_chain_20261105_v3.json` — full remediation | `1e6ccf9b55fbacc16196e7c23b4de0d78c1a9059326a14e2a4f1fba4e600b275` |
| `phase7_shortlist_native_chain_20261105_full_v1.json` — complete eight-wallet audit | `c31d4aed34ce04d424aeda92fa9395ea893191897c84f4625698341f63e19c19` |
| `phase7_chd_market_admission_20261105_v1.json` — 102 full candle days, zero overwrites | `67840b51bc357484d3480e8e58994faa83d993283a038e512ee80aca5cba8ebb` |
| `phase7_chd_trade_admission_20261105_v1.json` — 15 full trade-built days, one pre-existing day preserved | `e13c6a418cb4dc02297a1bd23c9fc8af483b05fddac535fd85738d86ca30c306` |

No on-chain address list, raw vendor fills, credential or market Parquet is committed to Git. Admission adds only SHA-verified canonical daily leaves to the **local shared `ml4t-data` market lake** through the existing CHD source reader and trade-to-bar builder; it does **not** change that repository's dirty tracked files or any running execution services. Local data-lake writes are not deployment of a paper worker, release or broker capability.

Reproduce from the Phase 7 PR checkout with **new** nonexisting output filenames:

```bash
uv run --frozen --group dev --extra market python scripts/phase7_shortlist_native_audit.py \
  /home/quant/.local/share/copytrade/reports/phase7_candidate_screen_20261104_v5.json \
  --wallet-alias S035-ENA --max-coins 40 --output /home/quant/.local/share/copytrade/reports/phase7_s035_new_immutable_version.json

uv run --frozen --group dev --extra market python scripts/phase7_shortlist_native_audit.py \
  /home/quant/.local/share/copytrade/reports/phase7_candidate_screen_20261104_v5.json \
  --max-coins 40 --output /home/quant/.local/share/copytrade/reports/phase7_all_eight_new_immutable_version.json
```

The audit's SHA-verified UTC market close is a **retrospective mark**, not the price available at follower decision time, a realized executable bid/ask, or actual source-account equity. New historical bars do not repair PIT first-known receipt evidence, complete initial books, subaccount netting, correlated losses or costs. Keep E6 primary / E2 challenger/P1 baseline **research-only**, unqualified and unauthorized for real trading.
