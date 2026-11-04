# Phase 7 — native-minute observed exposure, first bounded result

**UTC date:** 2026-11-04. **State:** PARTIAL / RESEARCH_ONLY / NO_ACCOUNT_PNL.
**Base:** `origin/main` 29156de99cd2a670f48757fea283bc6a5aa109d5.
**Private immutable result:** `/home/quant/.local/share/copytrade/reports/phase7_native_exposure_20261104_v1.json` SHA-256 `28acb92b37936888339304109963d6c14911055b0492ad65c07bca7ca7379713`.

## Actual execution

Run from the isolated research worktree, using the original owner-private source JSON, SHA-checked native per-day Parquet sidecars, and Polars 2.x. No historical reacquisition, brokerage action, live service mutation or portfolio activation. The raw wallet addresses and private evidence are not committed.

```bash
uv run --extra market --group dev python scripts/phase7_native_exposure.py --cap-coins 30
uv run --extra market --group dev python -m pytest -q tests/test_phase7_native_exposure.py
uv run --group dev ruff check scripts/phase7_native_exposure.py tests/test_phase7_native_exposure.py
```

The built-in frozen 94-wallet 90-day oracle job was also executed independently using the merged milestone-2 CLI. It returned the unchanged sealed report SHA `3141e4acb2df842025f880403d9dd4be2702c6811917bcb7949546dbdc6cbd1a`, 450,172 eligible source fills, 377,130 five-delay batch candidates, 322,970 native matched batches; finance explicitly BLOCKED.

## First reconstructed source-position diagnostics

For each coin, a signed position interval is accepted **only between two consecutive historical fills with mutually consistent `startPosition`**. Equal-millisecond intervals, discontinuous chains, source events outside 2026-08-05 to 2026-11-03 UTC, missing native days, bad SHA, non-1440-bar daily partitions and HIP-3 namespaces are not silently valued. The trailing interval after the last fill is censored. Only verified minute *closes* are used. This is a **partial known-leg source-risk proxy**, not independently first-known source state, true initial whole-book, follower order or equity accounting.

| Wallet | SHA-verified native-marked minutes | Maximum observed source gross notional | Worst consecutive-minute hold-only source mark change |
| --- | ---: | ---: | ---: |
| ACT04 | 68,268 | $12,506,512.92 | -$113,386.54 |
| Whale_0x5f94 | 116,694 | $8,951,141.93 | -$71,413.27 |
| S051-BTC | 73,983 | $160,712.24 | -$3,089.29 |
| S035-ENA | 113,533 | $127,678.61 | -$1,659.34 |
| S053-HYPE | 105,927 | $69,441.48 | -$1,198.99 |
| S064-xyz:BRENTOIL | 96,921 | $84,315.17 | -$1,830.00 |
| CM-002 | **UNKNOWN** | **UNKNOWN** | **UNKNOWN** |

S064 is observed **only for supported main-perp coins**, not its HIP-3 oil portfolio. Source notional cannot be converted to $600 risk-budget follower losses without verified as-of source equity, sizing, margin, complete books, costs and fills. Hold-only minute changes exclude entries/exits, gaps, funding, fee/slippage and within-minute path; they are *not* a wallet's worst true minute account P&L. Do not compare raw dollar magnitudes as if pod sizes were identical.

## Portfolio overlap — observed coin-minute-pair diagnostic

The denominator is the number of supported *same-coin, concurrently marked wallet-pair minutes*, not all minutes in 90 days. Each coin-minute pair is counted once for each overlapping pair. Different-coin correlation and omitted intervals remain unmeasured. The statistic is not a risk-budget weighted correlation, diversification ratio or probability of loss.

| Frozen identity | Pair comparisons observed / expected | Same-direction fraction of observed same-coin pair-minutes |
| --- | ---: | ---: |
| E2 (ACT04, S051, S053) | 3 / 3 | 86.07% |
| E6 (E2 + CM-002 + Whale) | 6 / 10 | 63.79% |
| P1 (S035, S051, S053) | 3 / 3 | 81.14% |
| E3 (ACT04, CM-002, S053) | 1 / 3 | 100% — insufficient |
| P14 (S035, S051, S053, S064, Whale) | 8 / 10 | 77.62% — incomplete HIP-3 |

New observed overlap diagnostic: S053-HYPE and Whale_0x5f94 had 138,910 supported same-coin pair-minutes, 72,251 same-direction and 66,659 opposite-direction (including multiple coin intervals per UTC minute). This suggests **some complementary positions**, but does not establish a stable hedge or lower E6 risk. The raw source position size and timing must be normalized to the same total nominal $600 and CM-002 must be reconstructed before E6-vs-E2 risk comparisons are decision-grade.

## Evidence comparison with Gemini

- **PARTIALLY SUPPORTED:** E6 adds an economically distinct whale exposure, with substantial opposite-direction same-coin overlap against S053. More wallets do not automatically mean lower drawdown.
- **NOT INDEPENDENTLY TESTABLE:** Gemini E2/E6 pass probabilities, 90-day return projections, exact source-equity-relative sizing, maximum daily/trailing drawdown and full portfolio survival.
- **CONFIRMED:** Reusable 1m native close context and five retrospective timing policies exist; the same 90-day oracle SHA was reproduced.
- **NOT CONFIRMED:** 5m execution advantage over 0m/1m/2m/10m after executable costs and complete follower fills. Market-context matches are not executable fills.
- **NOT CONFIRMED:** CM-002 full source-risk contribution or HIP-3 oil sleeve risk.

## Decision / not yet completed

**Retain the currently approved E6 primary / E2 challenger / P1 baseline. No changes or activation.** The new evidence is not sufficient to replace a frozen portfolio, choose a superior five-wallet combination, or certify source/follower economics.

The **10+10 Stage-1 candidate shortlists** and 188-address source inventory below are now completed as **screen-only** results. A financially evaluated 10+10 ranking, full risk-quality scoreboard, cost/delay economic sweeps, 14 contractual shock tests, completeness-adjusted portfolio ranking, independent effective bets, and robustness are **not completed** in this result. Neither missing values nor incomplete coverage have been converted to zeros or synthetic PASS outcomes. Phase 6B private risk artifacts and open PR #74 are separate existing work and are not merged/overwritten.

To reproduce, execute the script above with the same immutable source inputs. Compare the resulting JSON hash before drawing conclusions; never insert the owner-private addresses into a public research summary.

## Bounded Stage 1 — 188-wallet address-canonical source inventory

The separate first-stage scan combines original 94-source JSON files, the HL108 report with 108 addresses, and the Phase5 50-address cohort, deduplicating **by 42-character address**, not by display alias. There are **188 distinct addresses**: 56 provisional source/activity candidates, 77 WATCH and 55 REJECT under the **screen-only** rules. This inventory is an independent research source view, not a claim that the authoritative installed SQLite registry has 188 members. The latter has a separate 158-wallet research cohort and 264-monitor roster at its verified generation.

The screen accounts for 40 distinct days, retrospective last-fill age, main-perp fraction, churn, and the 47-address private prop-firm denylist (22 owner research exclusions + 25 additional model-conditional prop restrictions, **not 47 permanent research exclusions**). It flags missing as-of current equity, incomplete source books and absent native-market per-wallet coverage. `CANDIDATE_UNVERIFIED` is **not** a risk-quality grade or account-eligibility certificate. Static vendor `equity` fields are not historical NAV; no alternative manager has been promoted.

Private SHA-sealed inventory: `/home/quant/.local/share/copytrade/reports/phase7_universe_20261104_v2.json`, SHA256 `2cef0d3a2c28de70a1991043a58de45fc226d6a8ec56b22960c5133909da45ff`.

## Bounded Stage 1 — 10 + 10 screen-only combination candidates

The bounded screen selects 13 of the provisional candidates for low-same-coin **gross traded notional composition**; removes rejected wallets, any unsupported HIP-3/spot namespace and hardcoded retrospective frozen benchmark overrides; and enumerates 285 three-wallet + 1,242 five-wallet combinations (fixed 90-day history, known from Gemini: **not OOS**). `score_screen_only` is a transparent heuristic favoring heterogeneous traded coins and manageable churn; **do not interpret the numbers as portfolio downside risk, effective independent bets, alpha or follower economics.** In particular source **fill turnover does not equal actual simultaneously held exposure** and may reward missing inventory or market-risk correlation. The exact frozen E2/E6/P1/E3/P14 are evaluated separately as mandatory controls, regardless of the screen result.

| Rank (screen only) | 3-wallet aliases | 5-wallet aliases |
| --- | --- | --- |
| 1 | C021-NEAR, ACT34, ACT39 | C021-NEAR, VS030, ACT34, N19, ACT39 |
| 2 | ACT34, N19, ACT39 | C021-NEAR, ACT34, N001-HYPE, N19, ACT39 |
| 3 | ACT34, N001-HYPE, ACT39 | C021-NEAR, VS035, ACT34, N19, ACT39 |
| 4 | C021-NEAR, ACT34, W031 | C021-NEAR, ACT34, H23, N19, ACT39 |
| 5 | C021-NEAR, VS035, ACT34 | C021-NEAR, VS030, ACT34, N001-HYPE, ACT39 |
| 6 | VS030, ACT34, ACT39 | C021-NEAR, ACT34, H23, N001-HYPE, ACT39 |
| 7 | ACT34, H23, ACT39 | C021-NEAR, VS035, ACT34, N001-HYPE, ACT39 |
| 8 | C021-NEAR, VS030, ACT34 | ACT34, H23, N001-HYPE, N19, ACT39 |
| 9 | VS035, ACT34, N19 | C021-NEAR, ACT34, N19, ACT39, W031 |
| 10 | C021-NEAR, ACT34, N19 | VS030, ACT34, N001-HYPE, N19, ACT39 |

Private immutable candidate result: `/home/quant/.local/share/copytrade/reports/phase7_candidate_screen_20261104_v4.json`, SHA256 `f36d0fa4ac807d8d570cffb76387e990a6bb62073541fbd5dd3cce1190e3547f`.

Existing frozen controls from this same cheap screen: E2 mean pair gross fill-turnover overlap 0.2445; E6 0.2487. **These near-equal retrospective fill-turnover scores do not overturn either portfolio or establish a better alternative**. Missing historical source-equity, risk-budget scaling, mark-to-market comparison for shortlisted candidates, costs, and stop conditions are still gating.

Reproduce first-stage inventory and cheap combination shortlists:

```bash
uv run --extra market --group dev python scripts/phase7_universe_screen.py --output /home/quant/.local/share/copytrade/reports/phase7_universe_YOUR_NEW_VERSION.json
uv run --extra market --group dev python scripts/phase7_candidate_screen.py /home/quant/.local/share/copytrade/reports/phase7_universe_YOUR_NEW_VERSION.json --output /home/quant/.local/share/copytrade/reports/phase7_candidates_YOUR_NEW_VERSION.json
```

Use fresh, nonexisting output paths; both entrypoints refuse immutable report overwrites. No owner-private rows or address mappings are added to the PR.
