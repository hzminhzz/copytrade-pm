# HL94: Gemini-inspired fixed-scale three-pod replay — executed 2026-11-02

**Disposition: EXECUTED HISTORICAL EXPLORATORY PROXY / ENGINEERING EVIDENCE, NOT SCIENTIFICALLY QUALIFIED.** No live orders, no broker/account mutations, no production deployment. The best observed candidate is **S048-BTC / S053-HYPE / S060-HYPE**, but its October result is small, cost-sensitive, uses incomplete source inventory, and leaves positions open at cutoff. No proven prop-firm challenge pass or genuine alpha.

## Scope and user-approved methodology change

The user waived **historical equity recovery as a prerequisite for exploratory selection**. This study therefore does **not** claim to replicate the source wallet's changing exposure relative to historical account equity. It deliberately follows the useful *screening* part of the Gemini PDF: trading-style/churn archetypes, maker dependence, tail-risk patterns, source-book continuity, avoid clones, native market availability, portfolio diversification and follower costs.

- New, versioned cohort from **94 JSON wallet files**, 500,168 raw fills / 500,131 validated distinct fills; each file read without mutation and hashed. [Raw integrity audit](HL94-RESEARCH-AUDIT-20261102.md).
- Source discovery window: **2026-08-01 00:00 UTC to 2026-09-30 00:00 UTC**, 60 days. Descriptive validation/stress window: **2026-09-30 00:00 UTC to 2026-10-30 00:00 UTC**, 30 days.
- Source first-known observation clocks are unknown: execution starts at vendor *event time + 300s*, not the actual receipt time. **Historical hindsight oracle**, even when market bars are SHA validated.
- 2026-10-30 Propr displayed-instrument snapshot is a **post-hoc static eligibility screen**, not dated proof of listing/acceptance for each August trade. For this study use only native displayed default-perp crypto instruments with local Hyperliquid native 1m market inputs; omitted HIP-3/hedge instruments remain an explicit fidelity limitation.
- No historical source equity required. Instead freeze **one quantity multiplier k per wallet**, calibrated only on discovery: `k=min(1, $2,000 / P95(observed source gross exposure at fill prices), $200 / |worst source realized-loss day|)`. A wallet with zero historical loss uses no loss-day upper bound. This is *not* equity-relative copying. The reported base 3-pod scenario conservatively multiplies these frozen k values by **0.5**.
- Position targets use every signed, observed source quantity from anchored partial position chains; additions, reductions and exits are batched into **one decision per source wallet per five-minute lag**. Trades missed by the follower change actual inventory and tracking error, not source signals.
- One real **PM03 Account** handles $10,000 consolidated synthetic cash, pod attribution, market netting, internal crosses, fees, intraday marks and contractual floors. PM04-style **gross caps**: pod $6k / account $18k / instrument $9k. Independent additional research-only **$200 per-pod loss latch** requests reduce-to-flat and blocks further new pod risk; execution can overshoot. The PM04 `pm04_shadow` supervisor was **not invoked as a separate runtime**; do not misstate this as end-to-end PM04 integration.
- Account policy: simulated +10% profit target, 3% daily loss, 6% static loss. **Not confirmed Propr contract terms**. Costs: 5bp taker fee, 3bp total spread, 5bp slippage, assumed 1bp funding cost per eight hours. Stale verified marks up to 180m are allowed for **holding valuation only**; order execution requires a fresh exact native minute open. Capacity enforcement uses **prior completed minute's** quote volume and 5% participation, not future current-minute volume.
- Discovery initially evaluated **455 cheap source-dependence combinations** from 15 eligible wallets (79 quarantined by this screen). The **10 highest source-screen combinations** and **3 explicitly Gemini-motivated alternatives** were passed through PM03: **13 distinct trios, 26 base account-window replays**. No brute-force PnL search over every possible trio.

**Selection leakage disclosure:** Gemini's attached report previously analyzed some of the same October dates. Moreover, the 0.5 risk scale was chosen during sensitivity work after inspecting validation failures at the unscaled setting. Therefore this 30-day window is **NOT an untouched holdout**, despite its chronological separation. The rankings and stress findings are exploratory.

## Recorded 13-portfolio ranking

**PnL USD at each simulated stop or window end; NOT comparable equal-horizon terminal returns.** Positive terminal mark-to-market includes open positions at the 2026-10-30 cutoff. Asterisk is omitted; interpret the `Open` and `Loss` outcome columns instead.

| Rank | Wallet trio | Discovery PnL | Oct validation PnL | Validation max observed DD | Outcome |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | **S048-BTC / S053-HYPE / S060-HYPE** | +$470 | **+$111** | $358 | Open book at cutoff |
| 2 | S035-ENA / S051-BTC / S060-HYPE | +$837 | −$49 | $330 | Open book at cutoff |
| 3 | NANSEN-5af052556 / S035-ENA / S051-BTC | +$1,002 | −$181 | $428 | Open book at cutoff |
| 4 | NANSEN-32b9e4d3b / NANSEN-5af052556 / S035-ENA | +$1,002 | −$249 | $681 | Open book at cutoff |
| 5 | S035-ENA / S048-BTC / S051-BTC | +$840 | −$330 | $427 | Open book at cutoff |
| 6 | NANSEN-5af052556 / S035-ENA / S060-HYPE | +$691 | −$139 | $410 | Account loss-floor breach |
| 7 | NANSEN-5af052556 / S048-BTC / S060-HYPE | +$387 | −$143 | $377 | Account loss-floor breach |
| 8 | NANSEN-5af052556 / S035-ENA / S048-BTC | +$694 | −$193 | $411 | Account loss-floor breach |
| 9 | C017-HYPE / S048-BTC / S060-HYPE | +$302 | −$211 | $334 | Account loss-floor breach |
| 10 | S035-ENA / S048-BTC / S060-HYPE | +$598 | −$221 | $368 | Account loss-floor breach |
| 11 | NANSEN-32b9e4d3b / S035-ENA / S060-HYPE | +$684 | −$240 | $471 | Account loss-floor breach |
| 12 | C017-HYPE / S035-ENA / S048-BTC | +$609 | −$267 | $372 | Account loss-floor breach |
| 13 | NANSEN-32b9e4d3b / S035-ENA / S048-BTC | +$686 | −$311 | $488 | Account loss-floor breach |

Ranks are convenience groupings by modeled censor/outcome and validation mark, not evidence of a calibrated chance of passing. All discovery figures are from the separate first 60 days; none is an independent OOS alpha estimate.

### Best exploratory trio: S048-BTC / S053-HYPE / S060-HYPE

`0.5 × discovery-frozen k`, $10k account, $200 stop per pod, five-minute batching:

| Pod | Discovery-only base k | Actually replayed k | Observed source median completed hold |
| --- | ---: | ---: | ---: |
| S048-BTC | 0.0129828818 | **0.0064914409** | 24.49 h |
| S053-HYPE | 0.0466330930 | **0.0233165465** | 3.35 h |
| S060-HYPE | 0.0038870487 | **0.00194352435** | 4.44 h |

These are fixed source-position quantity multipliers, not account-equity ratios. Their size reflects the $10k account and conservative exposure limits, unlike Gemini's $100k example. The 0.5 factor was inspected against October results, so it is not independently validated. The shorter-horizon S053/S060 wallets were included as testable trend candidates rather than excluded by a blind ten-hour hold rule.

| October 30-day scenario | Partial validation PnL |
| --- | ---: |
| Base cost, five-minute delay | **+$111.19** |
| Double modeled costs | +$30.22 |
| Triple modeled costs | **−$53.59** |
| Immediate event-time oracle, base costs | +$116.38 |
| 15-minute delay, base costs | +$100.29 |
| 5% prior-completed-minute capacity enforced | +$112.17 |

Account-level base maximum observed drawdown **$357.58**, worst daily PnL **−$259.70**; no observed account-floor breach in this selected scenario. PM03 recorded **362 hypothetical net orders**, **$66,862.92** modeled cumulative turnover, **$33.43** modeled fees and **$30.93** assumed funding debits. Gross exposure is limited by the PM03 replay's research overlay; no exchange fill book or Propr capacity is verified. Capacity stress blocked **4 hypothetical orders**, with measured S053 exposure deviation ~0.36% in that scenario.

Base pod attribution: S048-BTC **−$204.17** (stopped after crossing $200 due to price/execution overshoot), S053-HYPE **+$238.65**, S060-HYPE **+$76.72**. S048 base action-weighted target/actual exposure deviation **4.14%** after risk stop; other two reconstructed observed targets tracked at the measured decision points. Zero measured tracking error does **not** prove complete original source wallet inventory.

This is a weak economic result: net PnL is smaller than a plausible additional stress-cost increase, $200 pod stops can overshoot, and terminal inventory remains open.

### Alternative experimental portfolios

- **S035-ENA / S051-BTC / S060-HYPE:** +$837 over discovery, then **−$48.79** over the full October window. No observed account-floor breach, but it did not deliver a profitable validation period.
- **S035-ENA / S048-BTC / S060-HYPE:** +$598 discovery, then **contractual loss-floor breach** on October 13 with −$221 at stop. It is an instructive negative comparator, not a recommended deployment.

**W042/W044/W028 Q3 comparison:** The previous 92-day equity-weighted sparse-NAV oracle had different wallets, source windows, denominators, scenario stop times and conditional source-chain coverage. There is no defensible numerical apples-to-apples superiority claim. The new trio is an exploratory candidate to compare in **the same future frozen research period and execution contract**.

## Exact private evidence, hashes and reproduction

Owner-only source/evidence files are **not committed**. This directory contains SHA-addressed JSON reports. Market report binds consumed native-market day hashes, subject to provider source.json SHA checks.

```text
Private report directory:
  /home/quant/.local/share/copytrade/reports/hl94-gemini-replay-20261102/

Frozen discovery manifest:
  hl94-screen-341018dceb7fb00b3e06.json
  sha256 341018dceb7fb00b3e0651a4d93b908fca4f380344dfcd46f585e181057eb03b

13 portfolio base replay, group 8:
  hl94-pm03-c81b6ebb7b5658062685.json
  sha256 c81b6ebb7b5658062685f3264299f8a82767216a78beb8aae13778a69a7a3a04

13 portfolio base replay, remaining group 5:
  hl94-pm03-756174199cc1ff7a2f95.json
  sha256 756174199cc1ff7a2f95ed3d7f615e101a6c0b23cda3712891cbb4a2a5860662

Consolidated comparison:
  hl94-summary-a7ad4d5a1bf0aab7ed04.json
  sha256 a7ad4d5a1bf0aab7ed04b6b5de1f220f6de592b17f64959161ba95ee0fae9bc9

Selected trio sensitivity:
  2x costs: hl94-pm03-a7a07051dceff2212c27.json
  3x costs: hl94-pm03-4474a1eda2f0cb3c7731.json
  0min:     hl94-pm03-e540cf47a2d4ed3abce1.json
  15min:    hl94-pm03-dedb768eb8d03923fe8b.json
  capacity: hl94-pm03-e0624b7184bfb425ec8f.json
```

The exact research CLI commands executed (shell variables only abbreviate paths):

```bash
DATA=/home/quant/dev/copytrade-pm/data
MARKET=/home/quant/dev/quant/ml4t-data/.data/store
SCOPE=/home/quant/.local/share/copytrade/reports/five-pod-20261029-research/PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json
OUT=/home/quant/.local/share/copytrade/reports/hl94-gemini-replay-20261102
SCREEN=$OUT/hl94-screen-341018dceb7fb00b3e06.json

uv run --frozen --group dev --extra market python -m copytrade_pm.pm_hl94_research \
  --phase screen --data-root "$DATA" --market-root "$MARKET" \
  --propr-snapshot "$SCOPE" --out "$OUT"

uv run --frozen --group dev --extra market python -m copytrade_pm.pm_hl94_research \
  --phase replay --screening-report "$SCREEN" \
  --offset 0 --count 8 --risk-scale 0.5 --stale-mark-minutes 180 \
  --data-root "$DATA" --market-root "$MARKET" --propr-snapshot "$SCOPE" --out "$OUT"

uv run --frozen --group dev --extra market python -m copytrade_pm.pm_hl94_research \
  --phase replay --selection top10 --screening-report "$SCREEN" \
  --offset 5 --count 5 --risk-scale 0.5 --stale-mark-minutes 180 \
  --data-root "$DATA" --market-root "$MARKET" --propr-snapshot "$SCOPE" --out "$OUT"

uv run --frozen --group dev --extra market python -m copytrade_pm.pm_hl94_summary \
  --screen "$SCREEN" --replays \
  "$OUT/hl94-pm03-c81b6ebb7b5658062685.json" \
  "$OUT/hl94-pm03-756174199cc1ff7a2f95.json" --out "$OUT"

# For selected frozen row index 5 (S048/S053/S060), replay five additional
# scenarios by appending --costs 2, --costs 3, --delay 0,
# --delay 15 or --capacity to the same --phase replay ... --offset 5 --count 1 command.
```

## Evidence hierarchy and conclusions

| Gate | Result |
| --- | --- |
| Source read-only audit | COMPLETE; raw files hashed, invalid rows isolated |
| Research implementation and PM03 account replay | IMPLEMENTED; reused merged PR20/21 engine |
| Engineering tests / Ruff / source identities | See exact latest test outputs in PR |
| Historical experiment with modeled costs | EXECUTED (13 portfolios + best-trio sensitivities) |
| Faithful whole-wallet historical equity replication | **NOT ATTEMPTED in this user-approved proxy path** |
| Full PM04 independent coordinator/runtime | **NOT RUN** (PM03 ledger + PM04-style limits only) |
| True independent OOS follower economics | **NOT VERIFIED** |
| Scientifically qualified challenge selection | **NO QUALIFIED PORTFOLIO** |
| Live trading / Propr order authorization | **NONE** |

**Decision:** Experiment further in offline/paper shadow with **S048/S053/S060** and retain two negative alternatives for comparison. Do **not** infer a +10% challenge pass probability from this snapshot or Gemini's in-sample 76 overlapping starts. A new forward-known, genuine OOS monitoring period is necessary before capital exposure. The historical-equity reconstruction is *not* a blocker to this completed exploratory research stage.
