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

The requested 10+10 ranked candidate study, full candidate-universe risk scoreboard, cost/delay economic sweeps, 14 contractual shock tests, completeness-adjusted portfolio ranking, independent effective bets, and robustness are **not completed** in this result. Neither missing values nor incomplete coverage have been converted to zeros or synthetic PASS outcomes. Phase 6B private risk artifacts and open PR #74 are separate existing work and are not merged/overwritten.

To reproduce, execute the script above with the same immutable source inputs. Compare the resulting JSON hash before drawing conclusions; never insert the owner-private addresses into a public research summary.
