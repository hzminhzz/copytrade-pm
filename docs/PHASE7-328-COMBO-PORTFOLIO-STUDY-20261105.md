# Phase 7 — 328 existing-data wallet-combination sensitivity study

**Date:** 2026-11-05 UTC. **Status:** COMPLETED HISTORICAL ORACLE SCREEN, **NOT** completed follower financial replay. **No fill acquisition or re-pagination.** No freezes, tracker subscriptions, broker, paper-worker or live trading changes.

## Decision first

**Retain frozen Gemini V2 `gemini.phase4/E6` five-wallet research primary and `gemini.phase4/E2` three-wallet challenger.** No proposed alternative has source-equity-faithful sizing, whole-account starting inventory, actual first-known receipts or certified follower outcomes.

The defensible new action is to nominate **two** relatively promising *conditional* portfolio comparisons for forward-paper registration *after* its independent engineering and source-identity gates, and keep **eight** alternatives as research controls. These ten are **not ten scientifically qualified portfolios**:

- **3-wallet research priority:** `ACT40 + S053-HYPE (registry W083) + ACT30` — sample intraday DD at 20bps is $807; 30bps proxy net **+$91.61** on 80 fully priced days, but 30bps intraday DD **$1,267** and worst BTC/ETH/HYPE shock **$860**. Marginal economics.
- **5-wallet research priority:** `ACT40 + S035-ENA (registry W016) + S053-HYPE (W083) + ACT30 + ACT33` — sample intraday DD at 20bps **$788**; 30bps proxy net **+$243.44** on only 76 fully priced days, 30bps intraday DD **$1,092**. Larger diversification sample, but not suitable for real funding yet.

A different three-wallet mix (`ACT40 + S035-ENA + ACT30`) has the **highest** 30bps proxy gain among these ten (**+$612.37**) but **fails the intraday 20bps $850 trailing reference** ($1,070). This is the difference between a profitable-looking return proxy and a drawdown-fit strategy.

**Decisive observation:** out of 328 tested configurations, **only 5 pass illustrative minute-level $450 daily-from-start and $850 trailing loss references at 20bps**, **only 1 at 30bps**, and **zero pass at 30bps with positive net proxy**. An incomplete-day sample is not the prop-firm's uninterrupted intraday risk clock; these passes are still not risk authorization.

## Universe and immutable input contracts

| Source | Verified cut |
|---|---|
| Registry research cohort | **158 canonical wallets**, exactly 108 + 20 + 30 |
| Versioned registry source generation | `e2836aab5ef6ef79306e9dfe732d8768c3b1ca6af29efbda066b37f03646a18f`; observed `2026-11-04T09:36:57.574969+00:00` |
| Existing Phase 7 union | 188 canonical source addresses, includes all 158 research addresses and 30 other source entries |
| Research members in union | 158, of which 56 retrospective provisional candidates; 77 WATCH; 25 REJECT |
| Eligible pool under frozen Stage-1 V5 source-position/churn/market gates | **10 canonical addresses**; exact-address verified against 158 research cohort and owner exclusion index |
| Previous Stage-1 V5 portfolio configurations | **118 three-wallet + 210 five-wallet = 328**; 1,875 cumulative earlier Stage-1 search trials, same overlapping 90-day period |
| Stage-1 V5 SHA-256 | `3c6d144d358fc3bca140e6fe8e008245915f11f549840ec610dfa26bc2a8732a` |
| Universe V2 SHA-256 | `2cef0d3a2c28de70a1991043a58de45fc226d6a8ec56b22960c5133909da45ff` |
| Source fill window | `2026-08-05T00:00:00Z` to `2026-11-03T00:00:00Z`, end exclusive |
| Native pricing authority | Local Hyperliquid full-day SHA-verifying 1-minute OHLCV provider, no Bybit/Binance substitutions |
| Added historical fills | **0** |

The 10-source pool is `N059-BNB, ACT40, S035-ENA, W030, S053-HYPE, ACT30, C021-NEAR, ACT33, ACT29, W017`. Note display aliases **S035-ENA = registry source alias W016**, **S053-HYPE = W083** via the private exact-address map. Comparing alias strings alone briefly gave a false outside-registry impression; the corrected exact-address audit confirms **10/10 membership**. ACT29 native full-position-chain-market coverage is only **90.22%**, below the model's 95% admission threshold. This study does not claim that the other 148 wallet histories are complete account-level economic inputs.

## Transparent scenario, not a follower P&L simulation

The model reuses the source fill `startPosition` adjacent-consistency validator: source coin exposure is included **only for complete one-minute intervals between two agreeing fills**. A later agreeing fill is required to corroborate historical inventory retrospectively; this is oracle reconstruction, **not** what a live follower knew at that time.

**Comparison design:**
- $10,000 **illustrative** account and **$6,000 total gross-notional** across observed source legs, equally allocated per pod: $2,000 per wallet for three, $1,200 for five. **These are gross caps, NOT the owner's $200 or $120 maximum realized-loss budgets**. They deliberately do not claim equity-faithful replication.
- Retrospective source position weights at the last completed 1-minute bar; **5-minute idealized delayed observation** plus next full minute, sampled on a 5-minute rebalance grid; historical event time is **not** real first-known follower receipt.
- At each simulated rebalance, observed source dollar-weights are gross-normalized to the stated per-pod cap. In later minutes the scenario marks the hypothetical weights against SHA-verified Hyperliquid next-minute close changes. **This is a factor-weight mark scenario**, not executed exchange contracts or source-wallet NAV.
- Hypothetical one-way composite 10/20/30bps of *weight-change notional* (fees/friction proxy). No L2, bid/ask, execution impact, size rounding, liquidation, funding, real cash transfers, broker order rejection or margin path.
- If an **included known source leg** lacks a native mark, the minute is invalid. **Any invalid minute excludes that entire calendar day** from sample P&L and drawdown. But source positions *outside known intervals* are also unavailable and omitted; they are **UNKNOWN, not verified flat**. Thus every reported P&L and drawdown is a conditional lower-information proxy with potential tail undercount.
- Loss references: $450 from daily opening equity and $850 peak-to-trough, both measured at **minute resolution over fully priced sample days only**. The 20bps daily-close-only gate is retained as an *initial shortlist heuristic*, and the stricter intraday gate is reported separately. **Neither is a real Propr evaluation**.

The combined 90-day sensitivity is hindsight-selected. Evaluation of the same 328 combinations with return and drawdown metrics adds further model-selection attempts beyond the earlier 1,875 coin-diversity trials. **No true holdout was left untouched**, and the last 30-day block is **negative for all ten** at 30bps.

## Ten proposed research experiments

The ten rows are the **top five for each pod size among 14 passing the weaker 20bps daily-close-only screen** after requiring ≥95% known-chain native pricing coverage per member and ≥75 complete priced days. They are deliberately presented with the **stricter minute-level 20bps outcome** so no weaker daily-close result is mistaken for prop-firm authorization.

| ID | Members (3 or 5) | 30bps known-leg mark proxy | 20bps **intraday** maximum DD | Worst 20bps intraday daily change | Complete days | 20bps intraday diagnostic |
|---|---|---:|---:|---:|---:|---|
| T3-01 | ACT40 + S035-ENA + ACT30 | **+$612.37** | $1,070.21 | −$367.59 | 76/90 | FAIL trailing |
| T3-02 | ACT40 + S053-HYPE + ACT30 | **+$91.61** | $807.46 | −$264.34 | 80/90 | PASS model-only |
| T3-03 | ACT40 + S035-ENA + ACT33 | **+$228.92** | $987.37 | −$414.30 | 76/90 | FAIL trailing |
| T3-04 | ACT40 + S053-HYPE + ACT33 | **−$324.50** | $719.32 | −$310.02 | 80/90 | PASS model-only |
| T3-05 | ACT40 + ACT30 + ACT33 | **−$465.19** | $741.31 | −$289.74 | 80/90 | PASS model-only |
| T5-01 | ACT40 + S035-ENA + S053-HYPE + ACT30 + ACT33 | **+$243.44** | $788.08 | −$338.30 | 76/90 | PASS model-only |
| T5-02 | ACT40 + S035-ENA + S053-HYPE + ACT30 + W017 | **+$349.86** | $1,009.02 | −$434.51 | 76/90 | FAIL trailing |
| T5-03 | ACT40 + S035-ENA + S053-HYPE + ACT30 + C021-NEAR | **+$41.02** | $977.25 | −$429.24 | 76/90 | FAIL trailing |
| T5-04 | ACT40 + S035-ENA + ACT30 + C021-NEAR + ACT33 | **−$336.31** | $1,036.85 | −$372.31 | 76/90 | FAIL trailing |
| T5-05 | ACT40 + S053-HYPE + ACT30 + C021-NEAR + ACT33 | **−$747.72** | $821.14 | −$302.44 | 80/90 | PASS model-only |

The above proxy gain/loss does **not** include unpriced missing calendar days. The worst minute-level drawdown is on the sampled portfolio *known-leg* equity curve, not the source account's margin NAV or the follower's executable book.

### Detailed evidence and intended role

**T3-01 — highest 3-pod modeled return; research stress challenger, NOT loss-qualified.** ACT40's broad BTC/HYPE/PONS/alt activity, S035-ENA's ENA-driven book and ACT30's HYPE/BTC profile diversify nominal coin exposure, but same-coin source-turnover overlap is still **0.2911**. The 30bps proxy is +$612 across 76 days, while 20bps minute-level DD is **$1,070**, already above the $850 reference; the last 30-day in-sample block is **−$387**. Shock: BTC/ETH −10% plus HYPE −20% produces a *hypothetical* known-leg worst **$538** loss. Treat the return as attractive *only before* risk qualification.

**T3-02 — preferred three-pod defensive comparison; not approved for funding.** ACT40 and ACT30 both trade majors, while S053 provides more HYPE focus; consequently coin turnover overlap is **0.4125**, higher than T3-01. Despite that exposure overlap, the modeled 20bps intraday DD is **$807** and worst intraday daily loss **$264**, so it clears these two illustrative checks. The 30bps return collapses to **+$92**, intraday DD rises to **$1,267**, and the joint BTC/ETH/HYPE shock reaches **$860**. Only the first of three 30-day blocks is positive at 30bps; sizing and HYPE beta are the primary concerns.

**T3-03 — ENA/BTC rotation experiment, weaker tail protection.** Replacing ACT30 with ACT33 sharply reduces gross traded-coin overlap to **0.1492** and source same-coin co-directional fraction to **0.4432**, but ACT33's observed top source turnover is roughly 90% BTC. 30bps modeled net **+$229** with 76 priced days; 20bps intraday DD **$987**. The last 30-day block is **−$548**. Coin diversification did **not** translate into a loss-compliant scenario.

**T3-04 — HYPE/BTC low-DD but net-negative comparator.** S053 focuses HYPE, ACT33 focuses BTC, ACT40 supplies mixed coins. Coin turnover overlap **0.1654** and 20bps intraday DD **$719** look defensively useful, but the 30bps proxy is **−$325**, with only one positive 30-day block; 30bps minute DD **$1,309**. Joint BTC/ETH/HYPE shock is **$940**, the largest among these ten. Keep as a negative control to test whether apparent low-cost diversity masks a dangerous common beta.

**T3-05 — lowest common-direction exposure, but negative expectancy.** ACT40/ACT30/ACT33 have the lowest observed source same-coin co-directional ratio among the ten (**0.3649**). It is the **only** configuration among all 328 that passes the 30bps *sample-only intraday* $450/$850 reference: minute DD **$848.76**, worst daily-from-start **−$297.68**. However its 30bps net is **−$465**, with **all three 30-day blocks negative**. Model-risk controls alone do not create alpha. **Do not promote this portfolio.**

**T5-01 — preferred five-pod forward-paper research comparison; not qualified.** ACT40+ACT30 supply multicoins, S035 brings ENA, S053 HYPE, and ACT33 BTC; source-turnover overlap **0.2184** across ten pairs. At 20bps, minute DD **$788** and worst day **−$338**; 30bps proxy net **+$243** on 76/90 priced days. But its 30bps minute DD **$1,092**, and the final 30-day block is **−$641**. This has better broad-component representation than T3-02, but still fails higher-cost risk robustness.

**T5-02 — highest five-pod modeled return; weakest daily-loss cushion.** W017 adds a broader multi-coin position-chain record (100% native match of reconstructed leg-minutes) instead of ACT33; positive 30bps proxy **+$350**. Yet its 20bps minute DD is **$1,009**, worst daily-from-start **−$435** (only $15 from the reference), and at 30bps worst daily **−$452** (breach). Last 30-day block **−$653**. The apparent profit is not sufficient compensation for tail fragility.

**T5-03 — NEAR/diverse-alt diversification experiment with negligible cost margin.** C021-NEAR spans NEAR, DOT, ICP, INJ, ONDO and SOL as observed in prior source turnover, reducing single-coin reliance relative to all-HYPE variants. But the 30bps proxy yields only **+$41** across 76/90 priced days, while 20bps intraday DD **$977** and 30bps DD **$1,363**. Last 30-day block **−$889**. Diversification should be validated through actual coincident loss, not coin names.

**T5-04 — low-overlap defensive control, still loss-ineligible.** Replacing S053 with ACT33 reduces turnover overlap to **0.1768**, and source co-directional share to **0.4971**. It also removes some HYPE concentration. Nonetheless 30bps proxy **−$336**, 20bps minute DD **$1,037**, and final block **−$759**. The lower overlap lacks evidence of superior prop-firm outcomes.

**T5-05 — relatively calm at 20bps, but fails economic robustness.** ACT40/S053/ACT30/C021/ACT33 achieve 20bps intraday DD **$821** and worst daily **−$302**, yet 30bps proxy is **−$748** with intraday DD **$1,432** and a **−$918** third block. This configuration tests whether diversification through BTC/NEAR/HYPE withstands real follower friction. It does not in this modeled cut; keep only as a cost-sensitivity control.

## Robustness: why none is qualified

- **In-sample selection contamination:** At least 1,875 earlier combinations, the same 328 additional mark/path comparisons, and prior Gemini searches all used overlapping historical evidence. The 30-day blocks were observed, not preregistered holdouts.
- **Cost sensitivity:** Only **1 of 328** passes sample-only *intraday* $450/$850 references at 30bps, and that one has negative proxy P&L. `0` passes with positive net proxy. The actual broker/venue spread, impact, funding and fees remain absent.
- **Native coverage versus whole-book coverage:** The modeled source chains are strong on market-data integrity but do not prove positions outside their validated adjacent-fill intervals. Excluding unpriced complete days (76 or 80 of 90 for these choices) can conceal losses.
- **Source sizing fidelity:** Gross-normalizing the known-source mixture to $2,000/$1,200 per pod does **not** match source equity/leverage/capital behavior. The scenario cannot answer exact follower sizing or real loss budgets.
- **No first-known or matched executed outcomes:** The model is delayed historical-oracle, not a captured follower decision and broker fill. Historical success is not real forward P&L.

**Consequence:** All 10 are candidate research designs for *controlled shadow experiments only*. **Do not deploy, adjust owner freezes, assign A/B qualification grades, or claim prop challenge pass probabilities.** E6/E2/P1 remain independent frozen historical reference portfolios and cannot be numerically compared to these gross-normalized mark proxies as if the performance metrics were equivalent.

## Reproduction and code verification

Script: `scripts/phase7_combo_328_native_sensitivity.py`; tests: `tests/test_phase7_combo_328_native_sensitivity.py`.

Private immutable report:

```
/home/quant/.local/share/copytrade/reports/phase7_combo328_sensitivity_20261105_v3.json
SHA256 bf4009dfe72a65ecab663ff5508aa81631971064ea710a71d26c08a38be44f13
```

Earlier V1 and V2 reports are retained in that private directory and are superseded by the V3 strict intraday/registry-bound audit. The V3 output includes **all 328 individual scenario rows**, all three fee environments, one-minute drawdown, three 30-day block results, and SHA-pinned source wallet diagnostics. No wallet addresses or raw provider fills are included in Git.

```bash
uv run --frozen --group dev --extra market python scripts/phase7_combo_328_native_sensitivity.py \
  /home/quant/.local/share/copytrade/reports/phase7_candidate_screen_20261104_v5.json \
  /home/quant/.local/share/copytrade/reports/phase7_universe_20261104_v2.json \
  --source-root /home/quant/dev/copytrade-pm/data \
  --output /home/quant/.local/share/copytrade/reports/phase7_combo328_sensitivity_REPRO_UNIQUE_VERSION.json
```

The `--output` path must **not already exist**. The tool refuses to overwrite immutable reports and requires the locally current 158-wallet private research registry. Inputs, source market days and private fill files were not modified.

**Future economic task:** genuine source-equity snapshots, complete opening positions, first-known receipts, source-faithful follower orders and matched control outcomes. The expected result may be negative; do not tune costs, omit lost days or select portfolio variants to manufacture a positive conclusion.
