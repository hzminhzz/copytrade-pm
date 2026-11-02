# Gemini wallet copytrading report: methodology audit (2026-11-02)

**Status:** PARTIALLY REPRODUCED, FOLLOWER ECONOMICS UNVERIFIED. **Decision:** ADOPT selected forensic techniques; EXPERIMENT with shortlisted addresses; REJECT the report as trading authorization or validated prop-challenge pass evidence. **Repository baseline:** `d11d754660714a2572ad1c6b91680a89b9d5e397`. **Independent judge:** `JUDGE_UNAVAILABLE` in this environment; the source-backed assessment below is not a simulated judge verdict.

This record documents the user-supplied four-page PDF, **Hyperliquid Perpetual Futures: Prop-Firm Challenge Copytrading Evaluation**, dated 2026-11-02 (PDF SHA-256 `b46e9c2d976e5d605923bbc64a5676bc27dbe1c93c9b3d2d48d12b7854dbc9b8`). The PDF is **not** committed; verify source identity before future reuse. Source spreadsheet exports existed as **untracked files in the owner's original VPS checkout**, not as part of this pull request. Check that they remain available before reproducing counts; their hashes below are snapshots, not permission to commit private raw data.

Source files used for the independent read-only checks:

- `docs/CONSOLIDATED_90D_FILLS_ALL_WALLETS_20261102.csv.gz` — SHA-256 `5c91a34500078a6b1fb963ca3008c349e29eca30cf372abcd1655eb24a4f6c2c`
- `docs/TOP_WALLETS_90D_FILLS_FOR_GEMINI.csv` — SHA-256 `cefbc2f8ad21cdc2bddad25a66f5580f8836d27fd251565f3583b7bebd985561`
- `docs/GEMINI_ARGON_PROMPT_BRIEF_20261102.md` — SHA-256 `6bf20c9249e6c616479ef26d9c0547a3f2978e44451b1abedcb1c6cbbbf7fa5d`

These files are **inputs or an assignment brief**, not the analysis script, execution receipt tape, broker record, full-equity history, verified output digest or OOS qualification artifact. Keep private exports and identities off Git.

## What Gemini did (with page references)

1. **Pages 1-2, forensic screening:** group wallets into low-churn swing (8), momentum/breakout (12), HFT/MM scalping (13), and specialized/HIP-3 (5); examine high fill churn, maker share, fees, liquidity and martingale/short-squeeze behavior.
2. **Page 1, clone hypothesis:** `C017-HYPE` and `N051-HYPE` reportedly have correlated PnL (`r=0.838` daily), the same 12 position exposures and an exact ~3:1 terminal book-size ratio. A copier pair should not occupy two risk seats.
3. **Page 2, execution model:** charge maker-to-taker fee conversion, an assumed passive-fill adverse-selection premium (1.5 bps), and fixed liquidity-tier spread/impact penalties (1.5/4.0/6.0/7.5 bps) under **50-200 ms latency**.
4. **Page 3, combination:** choose five source wallets and source-order scaling factors `k=(0.35, 0.10, 0.30, 0.70, 0.10)`. Reported scaled-source net `$47,346`; modeled follower net `$43,738.48`; daily worst loss `-$1,727.29`; max trailing DD `-$1,755.81`; 76 overlapping start dates reportedly pass.
5. **Page 4, shortlist/blacklist:** rank ten wallets (including S048-BTC, S060-HYPE, S053-HYPE, C017-HYPE, S058-PUMP) and flag suspicious underwater adds, passive HFT, HIP-3 microstructure, concentrated shorts, clone relationships and short/capped records.

The archetypes and screening methods are useful; the numbers have different evidentiary strengths.

## Independently reproduced from CSV (VERIFIED)

| Test | Result | What it actually proves |
| --- | --- | --- |
| Consolidated rows | **306,452** data rows | PDF file count is correct; not complete all-position coverage |
| Distinct source addresses | **38** (`20 Nansen / 18 Primary`) | Do **not** group Nansen by generic `wallet_label`; only 23 distinct text labels |
| Top-wallet file rows | **123,433** data rows | PDF subset count is correct |
| Missing `closedPnl` in Nansen | **96,374**, including **49,207** on opening rows and **47,167** on non-opening rows | Missing on opening fills can be legitimate; missing on closing/nonopening records needs separate provenance and opening inventory |
| Time-window mismatch | **15,816** data rows dated before 2026-08-01, including some from 2025 | The file is **not entirely a 90-day Aug-Oct panel**; restrict/version intended windows before any PnL or sample-size claim |
| Equity vintages | **Exactly one distinct `equity` string per address across all 38 wallets** | CSV provides a repeated wallet-level point estimate, **not** historical as-of account equity; never use as if live follower-known NAV in the past |
| Primary-source realized net | S048-BTC **$32,270**, S060-HYPE **$126,024**, S053-HYPE **$34,179**, C017-HYPE **$10,048**, S058-PUMP **$61,622** (rounded) | These are `sum(closedPnl - fee)` on source fills, not executable follower PnL |
| Five chosen weights | `sum_w k_w * sum_fills(closedPnl - fee) = $47,346.25` | Reproduces reported **scaled leader realized PnL**; `k` values selected by Gemini are assumed, not qualified |
| Clone-like association | `corr(C017-HYPE, N051-HYPE) = 0.8311` | Reproduced using daily source realized PnL minus fees on 2026-08-01 through 2026-11-01, filling no-fill dates with 0; close to PDF daily `0.838`, **not** a proof of same owner/exact book ratios |
| Same weighted portfolio, **without** Gemini's extra follower friction | Worst realized day **-$1,649.07** (2026-10-08); maximum daily-close cumulative drawdown **-$1,661.01** | Supports that report magnitudes are close to a realized-PnL-only series; this **does not** independently reproduce full intraminute MTM or actual stop-safe DD |

Reproduction logic: per address + UTC date, sum `float(closedPnl or 0) - float(fee or 0)`; for the five wallets, multiply those per-wallet profits by the report's `k` and sum; align the clone pair's daily PnL across Aug 1-Nov 1, including zero-fill calendar dates, before Pearson correlation. Keep a per-address key; leader "labels" in the Nansen input are not unique. These checks are direct read-only calculations from the stored CSV. Rounding and cutoff differ slightly from the PDF's unprovided analysis script.

## What remains unsupported / is not transferable (DO NOT PROMOTE)

| Claim / risk | Audit decision |
| --- | --- |
| **Follower net $43,738.48 / +43.74%, 12.42 Sharpe** | NOT VERIFIED as a causal follower result. The PDF publishes the fee/impact assumptions but **not the exact executable script, per-fill output, market marks, or order receipt tape**. Its extra friction of ~$3,608 relative to reproduced scaled-source $47,346 is a modeled assumption, not observed follower execution. |
| **50-200 ms modeled latency** | WRONG execution horizon for our **first-known +300-second batch and one market order**. Do not treat 50-200 ms retention as the five-minute counterpart or multiply each source partial-fill return to simulate batched target positions. Run 0/5/15min sensitivity separately, with real 1m marks. |
| **Historical source-equity-relative intent** | NOT RECONSTRUCTED. Repeated `equity` per address is a point observation; using it as past equity creates potential lookahead and sizing bias. Source order-size ratio `k` alone does not replicate `source signed position / source available equity`. |
| **Maximum trailing DD ~-$1,756 / 0% challenge violations** | NOT VERIFIED for continuous MTM. Fill CSV lacks full historical source equity/initial inventory, minute marks for every carried leg, complete funding and simultaneous risk accounting. A daily-close realized PnL DD cannot certify intraminute or firm daily/trailing floors. |
| **"100% pass" over 76 rolling dates** | IN-SAMPLE, HIGHLY DEPENDENT. Dates substantially overlap the same profitable 90-day path, while the five wallets and `k` were chosen using that period. No untouched out-of-sample period, experiment-family selection count, uncertainty bound or independent prospective follower outcomes. Do not quote as calibrated pass probability. |
| **"Five orthogonal" wallets / average r=0.098** | INSUFFICIENT. Different source PnL dates or weak linear daily correlation do not establish downside independence. Inspect simultaneous gross asset exposure, left-tail co-loss, factor concentrations, conditional regimes and actual broker netting. HYPE appears in several members. |
| **Clone "proven" by r and terminal inventory** | INVESTIGATE. Daily `r≈0.83` is reproduced, but exact **3:1 across 12 positions** and leader/follower causality cannot be verified from the CSV alone. Obtain independently timestamped account position histories. |
| **WAC reconstruction of 96,374 blank `closedPnl` records** | NOT ACCEPTED for scientific PnL without initial position/cost basis. Some missing opening-fill `closedPnl` is expected. Non-opening blanks, page caps, inventory restarts, realized-vs-unrealized and funding require reconciliation. Annotate reconstructed values as modeled, never native source truth. |
| **Huge leverage/DD relative to current/ending equity** | DESCRIPTIVE ONLY. Dividing past notionals/daily loss by one **terminal** `equity` value (possibly after withdrawals) is not leverage or DD at historical time. Reconstruct as-of equity, withdrawals and funding. Still investigate underwater-add/tail-risk patterns. |
| **Propr/FTMO 5%-daily/10%-trailing common rule** | UNCONFIRMED. Rule definitions are firm- and challenge-specific, often static vs trailing and balance-vs-equity dependent. Use dated official **account-specific** rule snapshot per [QUALIFICATION](QUALIFICATION.md); do not adopt this generic combined model. |
| **"Copy immediately" ranked top ten** | UNAUTHORIZED. Source-backed **candidate discovery**, not account compatibility, 5-minute economic qualification or trading authorization. Report addresses are mostly shortened; resolve exact canonical addresses from independently audited aliases. |

## Adopt into the evergreen wallet-selection procedure

**ACCEPT:**
- Per-wallet **maker/taker forensic split**: fee bps, passive share, expected maker-to-taker conversion, taker order cost, post-entry market markout, liquidity tiers including HIP-3; report gross edge, net follower retention and sensitivity *by separate decision episode*.
- **Linked-wallet detection** before seat allocation: address/subaccount and common funding linkage when accessible, normalized signed position trajectories, matching time-bucket additions/reductions, correlation of synchronized net follower PnL; a suspected clone shares risk until disproved.
- **Blow-up signatures**: underwater adds and accelerating notional, correlated position increases in falling prices, short-squeeze risk, tail MAE by coin, margin spikes, stop-out overshoot. Require actual economic path, not terminal-equity denominators.
- **Archetype-first triage** across low-churn multi-day swing, directional momentum/breakout, maker-dependent HFT, illiquid specialized/HIP-3. Use order IDs and reconstructed episodes, not fill/day hard cutoffs; many partial fills are one decision.
- **Portfolio-level diagnostics**: co-loss correlation conditioned on high-volatility regimes, marginal risk utility, overlapping coin factors, time to target, daily/overall/trailing floors and rolling-start outcomes as *descriptive* (not independent samples).
- Compare 3-pod and 5-pod proposals on the **same** $200-per-pod experimental risk objective, account rules, first-known five-minute batching, cost/latency controls and held-out periods. Keep 3 pods the default unless 5 improves OOS utility.

**EXPERIMENT:** Gemini's ten shortlist wallets and five selected labels, after canonical address reconciliation and separate frozen cohort/version. We may prioritize **S048-BTC** (low frequency), **S060-HYPE** (trend), **S053-HYPE** (long/short), **C017-HYPE** (multi-leg), **S058-PUMP** (alt breakout) for screening. These are **not** a recommendation to copy immediately. Explicitly test C017/N051 joint exposure as a clone hypothesis and the reported S054/S065/S049/S059 failure pattern, without silently blacklisting data based on an unverified endpoint. Recheck account activity/equity and Propr compatibility at evaluation time.

**REJECT as acceptance criteria:** raw realized net PnL alone; in-sample `k` from hindsight worst-day; 50-200 ms retention at a five-minute horizon; Sharpe/Sortino/equity R² without full equity accounting; a 100% overlapping-window pass rate; terminal equity used for historical exposure or loss denominator; "orthogonal" based only on average correlations.

## Required follow-on evidence before comparing with our existing candidate set

1. Freeze an **unseen research cohort** and selection procedure; preserve the existing 36-wallet PM-01 manifests. Save report/csv hashes, 90-day membership and source-generation provenance.
2. Fetch/reconcile full historical source book, equity/collateral/withdrawals and first-known receipts. Treat incomplete/truncated Nansen fill chains as blocked, not zero loss.
3. Resolve confirmed Propr-instrument membership and account-specific rules; fail closed for omitted required hedge legs.
4. Replay source-equity-normalized **target positions** with five-minute batching and one market order, not individual 50 ms copied fills. Use continuous native 1m marks and adverse intraminute stress, fees/spread/slip/funding and separate pod/account ledgers.
5. Freeze `k` or risk scaling using training-only data, $200 **nominal** stop budgets, account-level margin to firm daily floor and force-stop overshoot. Evaluate portfolio 3 vs 5, plus leave-one-out ablation, co-loss stresses and explicit missing/censored starts.
6. Require untouched forward or reserved OOS matched follower outcomes for any qualification claim. Reconcile against [EQUITY-WEIGHT-SIZING](EQUITY-WEIGHT-SIZING.md), [QUALIFICATION](QUALIFICATION.md) and [PM-04](PM-04-shadow-hardening.md).

**Bottom line:** The forensic framework is stronger than a PnL leaderboard. The reported five-wallet performance is an **in-sample, source-fill-derived, fee-assumption sensitivity scenario**, not a verified $100,000 challenge replay, not a 5-minute follower, and not a reason to increase live risk.
