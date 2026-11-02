# Nansen directional pod discovery and Gemini forensic extension — 2026-11-02

**Disposition:** 10 `SCREENED_RESEARCH_CANDIDATES` / **0** `FOLLOWER_REPLAY_QUALIFIED` / **0** live-authorized. **Independent judge:** `JUDGE_UNAVAILABLE` (no executable `judge` or `judge_batch` found in the project workspace). Research only. Owner-directed constraint: **exclude funding carry, market-neutral/basis strategies, and long BTC/HYPE or other majors against a broad altcoin short basket**. The stronger source-wallet *profitability* screen below is not proof of directional follower alpha.

**Read first:** [Wallet selection](WALLET-POD-SELECTION.md), [Gemini audit](GEMINI-REPORT-METHODOLOGY-AUDIT-20261102.md), [data acquisition](DATA-ACQUISITION.md), [equity-weight sizing](EQUITY-WEIGHT-SIZING.md), [qualification](QUALIFICATION.md), [PM-04](PM-04-shadow-hardening.md), and [index](INDEX.md). No frozen 36-wallet manifest or PM-02 interface was changed.

## Why this extends Gemini

Gemini's archetype-based screening, maker-to-taker cost recognition, clone detection, position-level adverse excursion, and portfolio co-loss analysis are useful. Its original 50–200 ms five-wallet scaling and 100% overlapping-window historical pass claim cannot qualify our **first-known +300 seconds, one-market-order, source-equity-relative** follower. See the independent source-CSV replication and limitations in [Gemini audit](GEMINI-REPORT-METHODOLOGY-AUDIT-20261102.md).

**New owner exclusions override the earlier permissive discussion of long/short baskets:** exclude deliberate long-major/short-alt relative-value, funding carry/basis, cross-venue hedge dependence and unreplicable market making from this *directional-only* intake. A mixed book is not "diversification" for this objective. Keep a separate future research universe for those strategies if desired; never quietly reclassify them as directional pods.

## Actual discovery and evidence sources

- **Nansen via Flovia, November 2, 2026:** `/api/v1/perp-leaderboard` pages 1–35 (top pages used both 50- and 20-result pagination), supplemental coin-specific `/api/v1/tgm/perp-pnl-leaderboard` for BTC/ETH/SOL/XRP/NEAR, and per-wallet `/api/v1/profiler/perp-pnl-summary` for **2026-08-01 through 2026-10-31** split by calendar month. Current all-DEX account books from `/api/v1/perp/account`. Reported PnL is source *realized* PnL, not the follower's PnL; leaderboard top positions are not the entire account.
- **Independent second provider:** public read-only Hyperliquid `POST https://api.hyperliquid.xyz/info` `type=userFunding`, each canonical address, `startTime=1785542400000`, `endTime=1793491199999` (Aug 1–Oct 31 UTC). Bounded pages of up to 500 events, advancing by the returned final timestamp and deduplicating `(time,coin,usdc,szi)`. All ten shortlisted wallet fetches ended with a non-full page; no pagination stall. Per-event `delta.szi` is a **signed funding-time position sample**, not a continuous position tape. Sum `delta.usdc` for wallet's historical *funding cashflow*; this may differ from current-position `cumFunding.allTime`, a lifetime summary with different bounds.
- **Independent repository data check:** locally retained `data/wallet_fills_90d/`, `data/nansen_smart_money_fills_90d/`, `data/broader_active_inventory_fills_90d/` were checked by full canonical `address`; **0 of 10** shortlisted addresses occurs in the 94 raw wallet files. The local data and existing native PM-01/PM-04 historical replay therefore **cannot yet replay these ten**. No fabricated equity/fills/prospective first-known timestamps.
- **Market-scope cross-check:** owner-private `PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json` reports the October 30 public Propr display list, including BTC/ETH/HYPE/ZEC/SOL/UNI/ZRO/LIT/PUMP/kPEPE/LTC/XRP. It does **not** prove that every historical leg, alternate-DEX symbol, or order ID is eligible or currently accepted on the specific challenge account.
- The Flovia provider's summaries, current-account figures, and public Hyperliquid funding may not cover other wallet/subaccount identities, spot hedges, off-Hyperliquid exchange positions, or changes in as-of account equity. Record these limitations instead of asserting proof of no carry.

## Style veto: auditable definitions

**Hard exclusion from this directional cohort when verified:**
1. **Explicit long-major/short-alt basket:** simultaneous positive signed position(s) in BTC/ETH/HYPE/SOL and negative signed position(s) in other alts at a common timestamp **and** persistent corroboration from position or funding history. One day containing both signs is weaker, because a trader may have reversed intraday; do not conflate daily union with simultaneous positions.
2. **Persistent mixed-direction basket / hedge:** repeated timestamps with both positive and negative instrument exposures, especially in many assets or across many days, unless full books explain isolated transitions and establish an independently replicable *directional* thesis. Never use current single-sided positions to erase prior basket behavior.
3. **Funding-carry dependence:** demonstrate significant net funding *credits* driving account returns, or a reproducible exposure structure mechanically targeting funding/basis, including missing external hedge legs. **Negative net funding alone is not proof of no carry**: off-venue offsets and spot portfolios remain unknown.
4. **HFT or maker/rebate dependence, unbounded losing-side averaging, clone identity, excluded Propr symbols, or unreconciled source book:** fail closed per canonical [wallet selection](WALLET-POD-SELECTION.md). High raw fill count by itself is not proof of HFT; group orders and distinct five-minute decision windows.

**Sample diagnostics (not permanent proof):** `mixed_same_timestamp_count`, `mixed_calendar_day_count`, `major_long_alt_short_count`, `funding_net_usdc`, `funding_credit_usdc`, `source_realized_usd`, `net_funding / realized`, `source_trade_count`, `distinct_order_ids`, `median_flat_to_flat_hold_hours`, `maker_fraction`, `source_equity_asof_coverage`, `active_coin_count`. Nonzero mixed sample may reflect a short-lived one-off hedge; repeated common-timestamp samples across a period imply a strategy incompatible with this intake. **Do not mark a wallet carry solely from its `cumFunding` field.**

## Ten directional research candidates, not ranked by return

Nansen realized PnL shown in **USD thousands**; amounts rounded to nearest $1k and per-month results can have small rounding differences. Funding shown in **USD thousands of net signed cashflow**, all negative; it was independently retrieved from Hyperliquid for the same period. `gross/equity` uses the **November 2 current** account snapshot, not as-of historical leverage. **All ten had 0 observed simultaneous mixed-direction `userFunding` timestamps**, but the sample does not rule out intra-funding hedges. Priority is audit order, not an alpha claim.

| Priority | Canonical wallet address | Current/recent archetype | Aug / Sep / Oct realized ($k) | Net funding ($k) | Current gross/equity | Key blocker / follow-up |
| --- | --- | --- | --- | ---: | ---: | --- |
| 1 | `0xaac091f502a773498fb9336f41500fd13098245b` | BTC+HYPE directional longs | +1,281 / +340 / +86 | -149 | 7.91x | Source gross notional large; verify max adverse excursion and drawdown stop overshoot |
| 2 | `0x1d74a7760df9d563d0b6610b1705266c4e2fdb26` | ETH/ZEC directional episodes | +465 / +8 / +96 | -9 | 2.06x | Strong August dependence; distinguish independent episodes from few large exits |
| 3 | `0xabdbca561f51626a217cbacdd95fcbd95b6484ac` | UNI/ZRO/ZEC directional | +1 / +150 / +47 | -30 | 2.85x | Aug profit near zero; historical `xyz:SP500` and source symbol scope require mapping |
| 4 | `0xdbe0780a5c5a0e3b345101bbc01ac2218196d6d5` | LIT/PUMP/ZEC momentum | -18 / +832 / +28 | -182 | 1.40x | Strong September concentration; funding debit ~22% of realized profit |
| 5 | `0x51f3a19c1dfd8d7fe670e43ce0f66648789c8b34` | HYPE directional | +691 / +557 / -4 | -161 | 6.74x | HYPE concentration and material funding expense; October near flat |
| 6 | `0x1bbfb3a33600338d5a948618189649a4588d5fc4` | BTC/SOL directional | 0 / +3,049 / +1,652 | -194 | 1.98x | Nansen reports **100% closed-fill win rate**: audit open-loss inventory, episodes and source cost basis |
| 7 | `0x24d8969e2bd6aabb6c4dfe042ef8b2cd8085217e` | BTC/HYPE/LTC/XRP one-sided | 0 / +590 / +143 | -31 | 1.56x | **100% closed-fill win rate**: audit historical positions; only two profitable observed months |
| 8 | `0x5a98c4f011e62cf3e188e4396d18a75c19b4af12` | BTC directional | +482 / +143 / -36 | -38 | 8.55x | High current gross leverage and October loss; risk resizing may eliminate follower edge |
| 9 | `0x17f0361771a9042d816cd007c731be15f05b094f` | ZEC/NEAR/BTC, now ZEC | +102 / +518 / -90 | -34 | 4.64x | Material October loss, 5 traded coins historically; direction and coverage per episode |
| 10 | `0x4b67337795c5e1ca1aaea307f57b79419c632c88` | kPEPE directional | 0 / +116 / +459 | -17 | 4.81x | **100% closed-fill win rate**, concentrated meme coin; check 5m impact and liquidity |

The explicit denominator for R in the $10,000 experiment is **$200 nominal pod loss budget**, not a $200 position size. For $100,000 it is **$2,000 per pod**. All future sizing must use the source **signed position notional / as-of available source equity**, scaled and guarded by PM-04; a source equity snapshot fetched November 2 is not a valid denominator for August.

**Do not automatically use all ten in one portfolio.** BTC/HYPE wallets may share beta, ZEC/LIT/PUMP wallets may crash together, and several carry very high notional exposure or suspicious reported win rates. Candidate count says nothing about independent strategy count.

## Clear exclusions and conditional alternates

The following are examples of **actual historical style-veto evidence**, not speculative classification from a single current screenshot. Values are common-timestamp mixed *funding position* samples between August 1 and October 31.

| Wallet | Mixed same-timestamp samples | Disposition |
| --- | ---: | --- |
| `0x054a01da80ee37d5220af5471b1eedbdcd2cdb2f` | 203 | **EXCLUDE** persistent BTC/HYPE mixed book, despite positive BTC realized PnL |
| `0x230963164d9637a4c536270a06b4e3636d44a2d9` | 49 | **EXCLUDE** mixed directional book; 11 sampled timestamps included major-long/alt-short |
| `0x597568694fe6ee1b701ec8578bd57102c9a29abd` | 21 | **EXCLUDE** recurrent mixed-direction / correlated alt legs |
| `0xfb941d2344b72ea9101400392b818173772d0ddf` | 15 | **EXCLUDE** recurrent mixed and major-long/short-alt samples |
| `0x8455193b0490ad091819000b01cd9bb833ac974b` | 20 | **EXCLUDE pending full-book defense** |
| `0xd6e56265890b76413d1d527eb9b75e334c0c5b42` | Not re-fetched in this round | **EXCLUDE** from this mandate based on previously verified HYPE-long/broad-alt-short current book; new verification needed for historical quantification |
| `0xac26cf5f3c46b5e102048c65b977d2551b72a9c7` | Not re-fetched in this round | **EXCLUDE** based on previously verified major-long/multi-alt-short current book |

**Next alternate:** `0xaecfe4eff84a1cd9a24accc1914ac537af7f6e1b` (PUMP): August +$1.369m / September +$433k / October +$120k Nansen realized, **one** mixed funding sample, net funding -$100,863; requires episode verification to distinguish an isolated transition from a hedge. **Further alternate:** `0x744a26a3e5a56efb7d95119752a63183c236bbd0` (PUMP): three positive months, one mixed funding sample, but ~99.6% reported win rate is a major accounting red flag. Neither can silently replace a failed top ten without running the full checks.

## Local system and operational verification gate

The primary VPS checkout (2026-11-02 inspection) has **94** existing immutable raw wallet files across three folders; **none** matches these ten canonical addresses. There is therefore **no matched 90-day HyperX fill inventory and no source-equity-as-of series in the local cohort** for these ten. The source `2026-11-02` current Nansen margin snapshot and `userFunding` do not repair missing first-known historical data. We **have not executed** the native 5-minute source-equity-relative portfolio replay, pod $200 stops, market impact, stressed coin caps, or three-pod first-passage outcomes for the ten. That is a documented data dependency, **not** a scientific pass or failure.

**Continuation order for an autonomous agent:**
1. Freeze this ten-address intake in a **new** `NANSEN_DIRECTIONAL_20261102` cohort; preserve original 36 and 94 manifests. Keep raw provider responses, key material and detailed per-account mapping in approved private paths, never Git.
2. Recover **complete HyperX GET /fills** per address/instrument with paging, event-chain continuity, `oid`/`tid` dedup, position-before/after, starting inventory and coin funding, using authorized existing API cache and rate limits. Verify instrument scope for all historical positions including if single-sided now. If API access is unavailable, continue other wallets rather than claiming fill-complete.
3. Recover historical **as-of leader equity** and first-known snapshots. The official `perpAllTime` retrospective sparse history can supply exploratory denominators but not a genuine first-known live follower. Do not backfill future-known numbers, omit losing opens or convert missing equity to zero.
4. Reuse the existing `copytrade-pm` **equity-normalized whole-book** follower, first observed change +300s one-market-order batching, true Hyperliquid 1m marks, fees/slippage/funding and account-level supervision. Run 0/5/15-minute and 1x/2x/3x cost sweeps; minimum three-pod comparisons. Do **not** import 50–200ms Gemini assumptions as executable results.
5. Score **net follower R per $200 budget**, source fidelity, loss-stop frequency/overshoot, MAE, tail co-loss, active decision episodes and target-before-account-breach; require all starting windows, censored outcomes and held-out/reliable prospective evidence. Abnormal 100% per-fill win rate must be reconciled against open PnL and full episode outcomes.
6. Compare clustering, linked wallets, simultaneous co-loss and combined gross coin exposure. Do not combine three BTC/HYPE directional whales and call them independent; enforce a portfolio-level veto even if each pod passes its individual screen. Keep **NO TRADE** until separate scientific and account authorization gates.

## Reproduction / integrity checklist

- [x] Nansen cross-checked per-wallet monthly source *realized* PnL and historical traded-coin breadth.
- [x] Nansen current **whole public account** books rather than single-token top-position results.
- [x] Hyperliquid 2026-08-01..2026-10-31 **bounded, deduplicated, complete-to-short-page** funding observations for each of the ten; no simultaneous opposing signs observed in sampled timestamps; all ten net funding cashflow negative.
- [x] Verified each main current instrument in the dated 2026-10-30 public Propr universe list. **Not** account-specific execution authorization.
- [x] Queried all 94 local raw wallet files by canonical address: no overlap.
- [ ] Full historical source fill / position and equity reconciliation for these ten.
- [ ] Full historic no-hedge/cross-venue evaluation and clone clusters; userFunding samples alone are not proof of no external carry.
- [ ] Whole-position, source-equity-relative five-minute follower replay for these ten and full risk-normalized challenge comparison.
- [ ] Genuine forward first-known observation, OOS qualification, broker/account authorization.

**Research verdict:** **TEN PROVISIONAL DIRECTIONAL-SCREENED WALLETS FOUND. ZERO SCIENTIFICALLY QUALIFIED.** Do not promote estimated $ gains, reported win rate, current leverage or negative funding into verified follower pass probabilities. All numbers are snapshots and historical source-level observations as of November 2, 2026.
