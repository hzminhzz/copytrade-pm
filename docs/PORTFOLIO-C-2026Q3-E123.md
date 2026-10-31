# Portfolio C — $10,000 historical E1/E2/E3 research (2026 Q3)

**2026-10-31, research branch `research/portfolio-c-e123-2026q3`.** Not a complete follower backtest, a Propr-executable portfolio, an independently known-first signal, or an OOS scientific result. All 12 account paths were **interrupted by exact native 1m price/exit-evidence gaps** before 2026-10-01. The equity/PnL shown below are *interim marked synthetic account balances at their different stop dates*, not final quarter outcomes or a method ranking.

## Fixed universe and input lineage

- Portfolio C wallet identities are **CO-001** (commodity, `xyz:CL`), **W015** (index, `xyz:XYZ100`), **VS066** (conditional HIP-3/mixed candidate); no wallet replacements.
- Study window **2026-07-01T00:00:00Z inclusive to 2026-10-01T00:00:00Z exclusive** (92 days).
- Original 36-wallet vendor provenance and four independently audited overlay generation SHAs are verified using the existing frozen loaders. The retained input contains **1,628 historical source fill transitions**, **63 eligible completed source episodes** (CO-001 21, W015 20, VS066 22), **16 distinct native Hyperliquid markets** and **1,241 consumed market-day hashes**. They are hindsight-selected *sub-books*; position-chain breaks, source carry-in/out and unmapped hedges are not reconstructed. HIP-3 data is not interchangeable with CFD or broker identifiers.
- Frozen private input: `/home/quant/.local/share/copytrade/reports/portfolio-c-e123-20261031/portfolio-c-input-202b6b46a7116ae8751e.json`.
- Input raw SHA-256: `202b6b46a7116ae8751e3bf39c0d756cf0e125ba463c865731dcf3e583496e4e`.
- Vendor fill audit raw SHA-256: `57f4eb4e6b5abdb755a4ee599ba224d5e451e240dd2c78cf202cd764f17a93e9`.
- Episode audit raw SHA-256: `0f10be09d577bfef9e749f258e34fe00acc2f13667c2e9180671dda8da66732b`.
- The two original source reports' SHA and cohort/overlay contracts were cross-checked against private immutable pages. **No prospective first-known receipts** exist in this study.
- The public Propr display snapshot is dated **2026-10-30**, i.e. after the study period. Tentative `xyz:` symbols can enter this **native historical research** only with exact SHA-verified market data; their actual Q3 Propr broker IDs, permission, minimum lots and copying legality remain **UNKNOWN**. Strict native-crypto Propr scope elsewhere is not relaxed.

## Single-account economic model

All three pods share **one** $10,000 PM-03/PM-04 synthetic account, profit objective $1,000, initial daily floor allowance $300, static loss allowance $600, three independently funded $60 pod daily/$60 pod stress/$120 pod cumulative drawdown envelopes, $50 central reserve and $3,000 aggregate modeled gross cap. The nominal pod stress budget stays $60; the research sizing adapter targets **at most $57**, a 5% safety margin inside that budget.

- **E1**: start $200 gross notional per eligible independently anchored episode, clip the pod's combined book to the same stress budget.
- **E2**: start the source ratio at $2,000 notional per episode, proportionally size all concurrent pod positions to $57 effective target stress (never beyond $60).
- **E3**: E2 permitted targets reduced by strictly prior 7-day hourly volatility versus the preceding 28-day window. No session-gap zero returns; insufficient history blocks a new factor.
- Execution alternatives: **IMMEDIATE** vs **ASYMMETRIC_5M** (only increases queued 300 seconds, reductions can bypass). Modeled 1×/2× fees (5bp), full spread (3bp) and slippage (5bp); carry is conservatively modeled at 1bp every 8 hours, charged using the pre-decision book at the current verified mark and posted after the PM-03 daily reset. Liquidity uses no more than 5% of *previous completed minute* quote-volume proxy. No L2/broker quote or actual Propr fills.
- Internal quantity grid **1e-12 base units** is a synthetic Decimal reproducibility rule, **not** a documented minimum broker lot size.
- If a scheduled non-action hourly mark is missing, the driver can censor a gap of up to 6 hours *only* if no signal, queued batch or outstanding exit is due. No mark, order or funding fill is fabricated in that gap. Missing risk/floor observations mean the full-period equity/floor path is **NOT VERIFIED**. A new action, exit requirement or longer gap blocks the scenario.
- All PM decisions pass through the same `ShadowRun` / `PM04_CONFIG` / `PM04_SIGNAL` / `PM04_TICK` and PM-03 account, funding, fill, reconciliation and persistent HALT path. The offline shadow mode is `RESEARCH_SYNTHETIC`; source classification `HISTORICAL_ORACLE_NOT_FIRST_KNOWN`. No broker adapter exists here.

## 12 executed scenarios (all blocked; do not rank across different stop dates)

*Net PnL is the marked **interim** hypothetical consolidated equity change from $10,000 at the interruption. USD rounded to two decimals. DD and worst daily loss are **sampled observed**, not intraminute extremes. Fees are separately modeled; funding amounts shown below are signed charges. Spread/slippage drag is also included in interim net PnL.*

| Sizing | Policy | Costs | Stop date, UTC | Interim net $ | Sampled DD $ | Worst day $ | Peak gross $ | Fees $ | Funding $ |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| E1 | Immediate | 1× | Sep 05 | +85.06 | 110.67 | 71.01 | 1061.16 | 9.35 | -14.33 |
| E1 | Immediate | 2× | Sep 05 | +63.07 | 111.53 | 71.04 | 1041.94 | 18.46 | -14.13 |
| E1 | Asymmetric 5m | 1× | Jul 07 | +16.51 | 35.14 | 29.57 | 572.78 | 0.70 | -0.27 |
| E1 | Asymmetric 5m | 2× | Jul 07 | +15.24 | 35.93 | 30.12 | 568.03 | 1.40 | -0.27 |
| E2 | Immediate | 1× | Jul 28 | +126.35 | 54.51 | 21.99 | 1129.49 | 3.19 | -6.28 |
| E2 | Immediate | 2× | Jul 28 | +117.01 | 55.95 | 22.43 | 1109.29 | 6.32 | -6.18 |
| E2 | Asymmetric 5m | 1× | Jul 07 | +46.57 | 51.20 | 29.69 | 845.28 | 1.11 | -0.50 |
| E2 | Asymmetric 5m | 2× | Jul 07 | +43.48 | 52.48 | 30.45 | 835.78 | 2.20 | -0.49 |
| E3 | Immediate | 1× | Jul 28 | +113.15 | 54.51 | 21.99 | 1129.49 | 3.11 | -6.23 |
| E3 | Immediate | 2× | Jul 28 | +104.13 | 55.95 | 22.43 | 1109.29 | 6.17 | -6.13 |
| E3 | Asymmetric 5m | 1× | Jul 07 | +55.65 | 46.03 | 23.70 | 780.07 | 1.06 | -0.45 |
| E3 | Asymmetric 5m | 2× | Jul 07 | +52.58 | 47.27 | 24.44 | 771.30 | 2.09 | -0.45 |
All 12 have `BLOCKED_DATA_OR_ENGINE` **specifically due `MISSING_EXACT_1M_BAR`**, with individually SHA-addressed private reports containing pod PnL, costs, gross/equity samples, pending positions, decision/exit rejections and sealed ledger provenance. The run that looks longer/better is not a winning method. Six scenarios also include risk-clock-censored quiet gaps when no action could safely occur. None demonstrated completion of the quarter or the $1,000 profit target.

The [sealed 12-run index](../research/portfolio-c-e123-runs.json) lists each exact report SHA/path, sampled average gross notional, minimum floor headroom, pod-attributed interim PnL, outstanding position count, rejected/expired targets and pending pod/broker reductions. In the **1× immediate** subsets: E1 averaged **$760.10** sampled gross, with **11,249 PM-03 revision/internal-cross events** and **zero pending reductions** at its Sep 05 cutoff; E2 averaged **$854.63**, with **1,460 revisions and two pending pod-reduction slots** at Jul 28; E3 averaged **$849.48**, with **1,460 revisions and two pending pod-reduction slots**. These are *not* broker order counts or risk-comparable turnover due different cutoffs. No modeled route had independently authenticated actual broker fills; the shared historical blocker is missing native marks, not a success or failure of a real exit order.

Private result root: `/home/quant/.local/share/copytrade/reports/portfolio-c-e123-20261031/`, subdirectories `v6-e1-immediate-1x` through `v6-e3-asymmetric_5m-2x`. **Never commit these private reports or address mappings.**

## Three focused stress diagnostics

Read-only stress analysis replays each 1× immediate scenario's **sealed PM-03 event stream**, checking exact account snapshot parity before computing hypothetical shocks on observed signed positions. It is not a substitute execution engine or observed PnL.

| Stress | E1 1× immediate through Sep 05 | E2 1× immediate through Jul 28 | E3 1× immediate through Jul 28 |
|---|---|---|---|
| S1 adverse CL/XYZ100 simultaneous shock | Worst sampled loss $41.81 | $27.87 | $27.87 |
| S2 ±10% common-market shock | Worst account loss $106.12, 3 losing pods | $112.95, 3 losing pods | $112.95, 3 losing pods |
| S3 zero-capacity exit and 2× adverse per-instrument moves | $165.07 stress loss vs $228.99 daily headroom | $170.22 vs $278.02 | $170.22 vs $278.02 |

**Important limits:** For E1, CL appeared in 320 of 2,092 observed nonflat portfolio samples and XYZ100 in 1,881, with 311 simultaneous CL/XYZ100 samples. E2/E3 were cut off in July before any CL execution: **0 CL samples** among 758 marked nonflat samples in each; their S1 result is XYZ100-only, not a genuine joint commodity/index validation. Common shock losses can hit all three pods at once, so no portfolio-independence claim is supported. The 2× theoretical exit shock did not exceed sampled daily headroom on these particular snapshots, but **absence of a breach in a censored sample is not a stop guarantee or zero risk**.

A separate adversarial PM-03 integration test proves: with a long CL position marked near the daily floor, a zero-volume exit produces `NO_EXECUTION_CAPACITY` and **retains actual inventory**; a further adverse mark latches `CONTRACTUAL_EQUITY_FLOOR` while that position remains open. Never assume a stop can guarantee a maximum realized loss.

The private stress report roots are `stress-v6-e1/`, `stress-v6-e2/`, `stress-v6-e3/` under the same owner-only result directory. All three check the source result SHA and replayed PM account snapshot.

## Disposition and next evidence

**ENGINEERING VERIFIED only for tested account integration and sealed source provenance. SCIENTIFICALLY QUALIFIED: NO. LIVE AUTHORIZED: NO.** No genuinely matched prospective first-known follower outcomes; incomplete source hedges/book; post-period market scope; Propr contract, minimum lots, real costs and HIP-3 sessions unconfirmed.

- **CO-001:** RETAIN as an exploratory candidate; validate its exact CL fill/quote availability, missing hedge exposures and account diversification before any rank/promotion.
- **W015:** RETAIN as an exploratory candidate; XYZ100 was actually held on the partial paths, but its signed exposure often shared the common downside with other pods.
- **VS066:** CONDITIONAL / NOT QUALIFIED; incomplete HIP-3 coverage and source strategy independence remain unresolved.
- **E1/E2/E3 winner:** **UNKNOWN**. These runs have mismatched/censored windows. Do not compare their marked interim profits as if all were 92-day ROI or prop pass probability.
- **Highest-value next work:** reconcile *exact native Hyperliquid HIP-3 1m* sessions and executable exit capacity at **2026-07-07 00:00 UTC**, **2026-07-28 00:00 UTC**, **2026-09-05 00:00 UTC**, preserving source-day SHAs and the existing gap exclusions; then re-run a *new versioned* coverage experiment. Do not splice prices from CME/Binance/CFD and do not silently change frozen 12-run results. Only after executable coverage and independent prospective receipts are proven should a future OOS qualification attempt be proposed.

## Commands and proof contract

The reproducible CLI is `uv run --frozen --group dev --extra market python -m copytrade_pm.pm_portfolio_c_driver`; use `--prepare` with all original SHA-verified sources to generate the private, versioned manifest, then invoke one method at a time using `--input <SHA-addressed-file> --market-root <native-store> --method E1|E2|E3 --execution IMMEDIATE|ASYMMETRIC_5M --cost-multiplier 1|2 --out <unique-private-directory>`. Output/ledger directories are private, exclusive and never overwritten. For stress analysis use `python -m copytrade_pm.pm_portfolio_c_stress --input <same-manifest> --result <exact-SHA-result> --out <new-private-directory>`. For synthetic regression, `uv run --frozen --group dev --extra market python -m pytest -q tests/test_pm_portfolio_c_driver.py`. Actual verification counts belong in commit/PR checks, not a fabricated claim inside this dated report.
