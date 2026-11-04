# Phase 7 — Gemini-versus-native-OHLCV portfolio decision report

**Study cut:** 2026-08-05 00:00 through 2026-11-03 00:00 UTC, end exclusive (90 days).
**Prepared:** 2026-11-04 UTC. **Repository:** `hzminhzz/copytrade-pm`.
**Report classification:** **FINAL AVAILABLE-EVIDENCE / CONDITIONAL**, not a certified whole-account historical replay.
**Decision state:** RESEARCH ONLY; existing Gemini-V2 E6/E2 freeze **PRESERVED**, no worker activation, no broker orders and no scientific qualification.

## Executive decision

**E6 remains the conservative five-pod paper-research primary; E2 remains the conservative three-pod challenger. P1 remains the historical reference, E3 the defensive reserve and Phase 5 B a separate, unqualified five-pod challenger.** The relative ordering is **Gemini-model-derived**, not independently confirmed by a complete source-equity-faithful follower replay.

The native Hyperliquid one-minute data support a narrower but material risk finding: the frozen Gemini position coefficients allow **high transient gross exposure** despite a nominal $600 total pod-risk calibration, especially from ACT04. A fast jump in major markets can create conditional known-leg stress losses well above the illustrative $450 daily or $850 trailing protection thresholds. Those **instantaneous shock calculations are not historical realized losses or valid first-passage outcomes**. Historical E6 coverage omits CM-002 and part of the coin/DEX inventory; its lower measured losses cannot certify that it dominates E2.

Gemini's 5m delay likely reduces order churn, but **fee dollars depend on traded notional**, not merely order count. In a simple 10bps, last-leader-price proxy, E2's 5m netting reduces order count ~91% and its notional-cost estimate only ~11%; no follower-price or market-impact benefit is proven.

**Recommendation:** preserve E6, E2 and P1/E3 controls for an independently witnessed, prospective paper comparison. Freeze all policy and k values as research assumptions, not live order multipliers. Do not promote Phase 5's spectacular model returns or tiny modeled drawdowns on the strength of retroactive data.

## I. Historical Gemini benchmark (prior research)

The following numbers are **Gemini Phase 6A P2_flatten modeled outputs** imported from the approved [Gemini Freeze V2](decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.md). They are not measured native-OHLCV follower returns.

| Approved historical control | Members | Simulated return | Modeled max daily DD | Modeled max trailing DD | Worst 5-day loss |
|---|---|---:|---:|---:|---:|
| P1 / 3-wallet historical baseline | S035-ENA, S051-BTC, S053-HYPE | +22.24% | 2.42% | 6.81% | 9.90% |
| **E2 / 3-wallet challenger** | ACT04, S053-HYPE, S051-BTC | **+18.92%** | 2.42% | **4.31%** | 7.64% |
| P14 / 5-wallet archived challenger | P1 trio + S064-BRENTOIL, Whale_0x5f94 | +15.77% | 1.98% | 4.06% | 7.13% |
| **E6 / 5-wallet primary** | E2 trio + CM-002, Whale_0x5f94 | **+14.76%** | **1.48%** | **2.73%** | **5.43%** |

All are historically explored, not true untouched OOS confirmation. Note the frozen historical E6/E2 coefficients in Gemini V2 are **illustrative**; those are *not* verified source-equity-relative live sizing. The 0.35× versus 1.5× cap conflict, and the earlier report's duplicated P1/P2 stop results, prevent trusting stop efficacy as settled.

A distinct **Phase 5 B 1×** alternative (N01/N07/N02/N05/ACT08) reported +31.42% return and 0.46% trailing DD in its original Gemini CSV. Independent Phase 6B captured historical source-book, NAV and market gaps; its known-leg shock analysis produced >$10k worst-modeled squeeze exposure and **zero complete source-account stress runs**. Therefore Phase 5 B's tail-risk claim is NOT independently confirmed; do not replace E6 with it on model returns.

## II. Audited data and research universe

- Official versioned wallet registry: **158 unique research-cohort wallets, 22 owner exclusions** and 264 monitored/subscribed in the inspected source generation (2026-11-04 09:36:57 UTC, SHA `e2836aab5ef6ef79306e9dfe732d8768c3b1ca6af29efbda066b37f03646a18f`). This is **registry authority**, not 158 raw complete source books or 264 paper accounts.
- Independent source union: **188 canonical distinct address records** deduplicated across original 94 private fill JSON files, HL108 report (108 source addresses), and Phase 5 new50 CSV (50 addresses). Some cohorts overlap. Stage-1: 56 provisional source/activity candidates, 77 WATCH, 55 REJECT from the illustrative screen. These statuses are NOT professional eligibility grades.
- Owner-private prop-firm selection denylist: **47 unique addresses** = 22 owner research exclusions + 25 additional Gemini Phase 5 *prop-firm allocation only* restrictions. Do not inflate permanent owner exclusions to 47.
- Original 94-source collection: 500,168 raw fill rows; strict frozen 90-day native main-perp source screen uses **450,172 valid eligible fills**, 216 instruments and SHA `1deefe08279936770e896f0521664cf0ee1976bc0eecec78d5c615cb8799117d`.
- Re-executed merged Polars 2.x oracle: **377,130** five-delay prospective-eligibility *oracle candidates*, **322,970** native matched *market-context screens*, report SHA `3141e4acb2df842025f880403d9dd4be2702c6811917bcb7949546dbdc6cbd1a`. No first-known receipt or real PM-03 accounting certification.
- Phase 6B independently audited 95 native markets (26 with whole-window coverage) and 5,239,441 native instrument-minutes out of 12,312,000 expected. These **Phase-5-specific coverage counts must not be substituted for E6 coverage**.

### Independent anchored source-chain coverage

Only intervals bounded by two chronologically consistent adjacent `startPosition` fills were reconstructed, using SHA-verified daily native close bars. Equal-timestamp and discontinuous intervals, end-censored holdings, HIP-3 and unsupported instruments remain **UNKNOWN**, not flat. Metrics are **source-wallet dollars before Gemini k**, not hypothetical follower dollars.

| Manager | Native marked minutes | Peak observed source gross | Worst consecutive-minute hold-only source mark change |
|---|---:|---:|---:|
| ACT04 | 68,268 | $12.51M | −$113,387 |
| Whale_0x5f94 | 116,694 | $8.95M | −$71,413 |
| S051-BTC | 73,983 | $160,712 | −$3,089 |
| S035-ENA | 113,533 | $127,679 | −$1,659 |
| S053-HYPE | 105,927 | $69,441 | −$1,199 |
| S064-BRENTOIL | 96,921 of supported main-perp coins only | $84,315 | −$1,830 |
| CM-002 | UNKNOWN — source lacks an independently anchored position chain | UNKNOWN | UNKNOWN |

These one-minute changes exclude entries, exits, fees, funding, unobserved minutes, other-DEX positions and unknown source account NAV. Source position notional alone is **not** a pod $200/$120 realized risk loss.

## III. Economic diversification: overlapping market risk, not pod count

For the supported source-position intervals, **same-coin concurrent wallet-pair minutes** have these directional agreements; each pair/coin/minute is a separate observation, not an independent trade or account-loss sample:

| Portfolio | Observed pair comparisons | Same-direction share | Interpretation |
|---|---:|---:|---|
| E2 | 3/3 | 86.07% | Substantial same-coin co-directional overlap |
| E6 | 6/10 | 63.79% | Some opposing positions, but CM-002 pairs missing |
| P1 | 3/3 | 81.14% | High same-direction overlap |
| E3 | 1/3 | 100% | Uninformative because CM-002 missing |
| P14 | 8/10 | 77.62% | Partial main-perp coverage; HIP-3 oil omitted |

In the observed S053-HYPE versus Whale_0x5f94 supported overlaps, **72,251 pair-minutes were same direction** and **66,659 opposing**. The whale has *some* marginal exposure diversification, **but is not an always-on hedge**. Different-coin common BTC/ETH/HYPE market beta, conditional cross-loss in crisis regimes and entire-book overlap remain unknown.

## IV. New native-minute frozen-k stress (conditional, not financial replay)

**Contract:** Use the frozen Gemini V2 10k coefficients, *not* inferred current equity; source-consistent known main-perp position intervals, 1m verified closes and **no account stop**, overnight funding, executable depth or price-gap liquidity assumptions. This is an instantaneous hypothetical position shock applied to every observed minute as a *separate* snapshot; no one is claiming these shocks all occurred historically. A missing wallet or coin contributes **UNKNOWN** rather than a modeled flat.

Fixed `k` research reference: E2 ACT04 0.00428, S053 0.04708, S051 0.04847; E6 ACT04 0.00257, S053 0.02825, S051 0.02908, CM-002 0.00231, Whale 0.00029. Same total **nominal** risk calibration: three pods $200 each, five pods $120 each, $600 total on hypothetical $10k initial equity. Risk-budget dollars are not guaranteed maximum realized loss.

| Conditional known-leg metric | E2: 3/3 source files, partial coins | E6: **4/5 observed**, CM-002 missing |
|---|---:|---:|
| At least one supported source leg observed | 122,690 minute instants | 125,843 minute instants |
| Peak scaled gross before net | **$59,603** | **$36,360** |
| P95 scaled gross | $10,899 | $7,437 |
| Median effective marked-coin bets (instantaneous HHI proxy) | 1.99 | 3.47 |
| Observed active-minute fraction exceeding hypothetical $20k gross cap | 2.30% | 1.71% |
| Max ACT04 contribution to gross | $53,528 | $32,142 |
| Max whale contribution to gross | n/a | $1,804 |
| Hypothetical BTC −10% worst loss | $1,300 | $780 |
| Hypothetical ETH −10% worst loss | $4,171 | $2,504 |
| Hypothetical HYPE −20% worst loss | $1,145 | $688 |
| Joint BTC/ETH −10%, HYPE −20% worst loss | $4,955 | $2,975 |
| All tracked market coins −10% worst loss | **$5,960** | **$3,521** |
| All tracked coins +10% (short squeeze) | $498 | $327 |
| All-correlated adverse sign, 10% | $5,960 | $3,636 |
| Worst two pods losing together, 10% gross adverse | $5,853 | $3,514 |
| Largest pod doubles before 10% adverse shock | $11,313 | $6,850 |
| Whale doubles before 10% adverse shock | n/a | $3,693 |
| Remove largest gross pod, all-market −10% | $726 | $472 |

For E6 the **missing CM-002 source position does not mean a zero position**. Nor do the modeled raw `k` multipliers preserve source-equity fidelity. The table is useful to identify *risk concentration and potential size of jump risk*, not to prove E6 is 41% safer. Likewise an instantaneous 10% gap can outrun a daily hard stop; a purported P2 flatten strategy does not imply a hard loss bound without executable order constraints.

**Temporal robustness (three 30-day blocks):** the worst modeled −10% market shock was E2 **$5,960 / $1,245 / $1,114**, E6 known legs **$3,521 / $711 / $698**. The worst first-month source exposure dominates. These are overlapping with previously examined Gemini history, not fresh OOS estimates.

### 14 failure modes requested — observed or conditional disposition

| Failure mode | Evidence status | Result or limitation |
|---|---|---|
| 1. BTC/ETH sharp moves | CONDITIONAL modeled | Single-coin shocks and joint BTC/ETH −10% modeled above |
| 2. HYPE −20% | CONDITIONAL modeled | E2 −$1,145; E6 known-only −$688 |
| 3. Five wallets all long | HYPOTHETICAL bounded | All gross sign-aligned at −10%: E6 known-only −$3,636 |
| 4. Two correlated losers | HYPOTHETICAL bounded | Worst two known pods −$5,853 E2 / −$3,514 E6 |
| 5. Whale doubles position | HYPOTHETICAL bounded | E6 known-leg gross-direction loss bound −$3,693 |
| 6. Averaging down / size drift | HYPOTHETICAL bounded | Largest-pod-double scenario; actual path/stop behavior not reconstructed |
| 7. Partial follower fills | UNKNOWN | No real executable follower book, adverse selection, partial receipt or residual |
| 8. Execution 2×/3× cost | CONDITIONAL modeled | Separate batch-notional cost table below |
| 9. Market-data outage/stale | UNKNOWN for survival | Missing native days and unsupported contracts fail closed |
| 10. Daily/trailing DD thresholds | NOT CERTIFIED | Shock dollars can exceed $450/$850, but no real account first-passage |
| 11. Per-pod/portfolio HALT | NOT CERTIFIED | Existing PM03 synthetic tests do not prove this historical source path |
| 12. Remove historically best wallet | UNKNOWN | Real whole-account source and follower performance unavailable |
| 13. Remove historically worst wallet | UNKNOWN | Largest-gross-pod removal is a *different* known-leg diagnostic |
| 14. Change position-sizing behavior | CONDITIONAL bounded | Largest-pod-size-double scenario, not calibrated behavioral probability |

Observed market OHLCV and retroactive source position paths do not verify executable hard-stop or daily first passage. Never interpret `shock_crosses_450` counts as realized stop breaches or failure probabilities.

## V. Follower delay, batching and friction sensitivity

**Separate policy from merged Polars per-fill eligibility:** an independent non-resetting, first-source-event window per wallet/coin was applied to past leader fills (0/1/2/5/10m) purely to count net hypothetical orders. Source timestamps are **not follower first-known receipts**. The notional cost uses the *last leader fill price* within each batch, not the future native next-minute fill, L2 depth, realized spread or impact.

| Delay | E2 modeled orders | E2 traded-notional proxy | E2 10bps cost | E6 modeled orders, **CM-002 excluded** | E6 10bps cost |
|---|---:|---:|---:|---:|---:|
| 0m | 8,787 | $883,286 | $883 | 17,838 | $537 |
| 1m | 940 | $852,296 | $852 | 1,154 | $518 |
| 2m | 878 | $837,921 | $838 | 1,044 | $509 |
| 5m | **784** | **$789,274** | **$789** | **905** | **$480** |
| 10m | 732 | $770,257 | $770 | 832 | $468 |

- E2's 5m window compresses modeled orders approximately **91.1%** versus 0m, but model-valued traded notional and 10bps fees only approximately **10.6%**. E6 partial compresses modeled orders approximately **94.9%** and gross notional approximately **10.6%**.
- At the 5m frozen-k event timing, **E2** hypothetical notional friction = **$789 / $1,579 / $2,368** for 10/20/30bps. **E6 partial known legs** = **$480 / $959 / $1,439**. These are total modeled bills, *not* Gemini modeled return adjustments: subtracting them from Gemini net PnL would double count any already-included fees.
- Price movement caused by waiting, market impact, per-market trading constraints and participation capacity remain unmeasured; therefore neither 2m nor 5m is scientifically proven economically optimal from these outputs. A slightly lower 10m modeled turnover cost does not prove better 10m execution.
- Compare to the original frozen 94-wallet job: its delay cases are **per-fill retrospective eligible next-minute screens**, not these non-resetting batches. The two results must not be conflated.

### V.a — SHA-verified next-minute open, rather than leader-price proxy (Phase 7 continuation)

A separate versioned research result now joins the *same retrospective first-event batch deadlines* to the repository's existing SHA-verifying native daily market adapter. Execution-clock policy is **strict next complete UTC minute after first-event eligibility**. The reported `next_open_float_screen_only` is a native OHLCV minute **open**, never a bid/ask trade or first-known follower receipt. The prior completed minute's base volume, not the current/future bar's volume, supplies a conservative 5% **screening** participation comparison.

Across the wallet sources actually available, the run generated **21,773 batch candidates across all five delays and 351 unique instrument-day keys**, including 327 SHA-verified complete native days, 3 declared partial days and 21 unavailable days. Candidate rows are never populated from missing days. The original E6 CM-002 source remains unobserved and excluded from all complete-economics claims.

| Frozen-k retrospective delay | E2 matched / total | E2 matched notional | E2 native 10bps | E6 known legs matched / total | E6 known-legs native 10bps |
|---|---:|---:|---:|---:|---:|
| 0m | 8,527 / 8,787 | $874,740 | $874.74 | 15,393 / 17,838 | $529.42 |
| 1m | 922 / 940 | $843,695 | $843.69 | 1,099 / 1,154 | $510.79 |
| 2m | 860 / 878 | $829,206 | $829.21 | 997 / 1,044 | $502.11 |
| **5m** | **767 / 784** | **$779,883** | **$779.88** | **864 / 905** | **$472.21** |
| 10m | 715 / 732 | $760,778 | $760.78 | 796 / 832 | $460.70 |

**Capacity-specific audit at the frozen 5-minute policy:** E2 has **60** matched orders above 5% of the completed *previous-minute base volume*, and **3** matched orders with zero prior-minute volume. The corresponding E6 **known-leg-only** counts are **49** above threshold and **6** with zero prior-minute volume. The values refer to *model-k-scaled follower base quantity*, not unscaled leader order size. These conditions are research feasibility warnings; actual participation capacity requires reliable quote-side spread, depth, impact and order-book trades.

**Unmodeled / not proved:** full execution cost, broker fee tiers, funding, first-known receipt delay, true next-minute bid/ask liquidity and partial-fill probabilities, protective stop-order first passage, and CM-002's remaining execution orders. The matched notional *excludes missing-day candidates*, so the figures are not complete-portfolio lifetime costs and should not be subtracted from already net Gemini results. A 5m window can reduce order count sharply while still leaving material gross traded notional and high same-minute liquidity participation.

Source evidence: owner-private immutable `/home/quant/.local/share/copytrade/reports/phase7_native_open_20261104_v1.json`, SHA256 `03f6f91dcf2f6a061aa79ce776ffd53575abbc802f64cef0c66b53ae69047076`. The included native-market fingerprint is `1fb1b8df8c2286df4ca5d2d4092a75ecc7926be96ca7713e733884a06c960df7`. Reproduce with `uv run --frozen --group dev --extra market python scripts/phase7_native_open_screen.py` from this research branch; this is a separate read-only **SCREEN_ONLY** path, not a version of the mainline full-account replay or a source for scientific qualification.

### V.b — CM-002 historical CSV salvage (strictly secondary evidence)

The original Phase-4 **HL108 CSV already contained 7,202 CM-002 rows**, although no exact `startPosition` chain or exchange trade IDs were available. To avoid silently omitting a selected E6 member, a **separate opt-in research job** now reads this existing, SHA-pinned file without calling a provider. It validates CM-002's exact owner-private address against the versioned roster. It retains all rows as independent *CSV observations* because same-second rows cannot be deduplicated against native trade IDs.

Of these 7,202 source rows, **5,887** are supported 90-day default-perp second-precision event records; **1,305** are outside default-perp DEX scope and **10** fall outside the requested study window. The 1,305 unsupported DEX fills (not necessarily zero exposure) are excluded from all calculations; **none** may be interpreted as flat.

**What changes with these lower-confidence observations:**

| 5m retrospective native-open screen | E2 (stronger raw-TID source) | E6 with second-precision CM-002 supplement |
|---|---:|---:|
| Candidate batches | 784 | **2,012** |
| Matched exact native opens | 767 | **1,826** |
| Matched coverage | 97.83% | **90.76%** |
| Matched follower-notional proxy | $779,883 | **$487,235** |
| Illustrative matched-only 10bps fee | $779.88 | **$487.24** |
| Above 5% previous-minute participation | 60 | **72** |
| Zero previous-minute volume | 3 | **13** |
| Missing exact native day / partial day | 14 / 3 | **178 / 8** |

**Interpretation:** CM-002 may contribute many small batches and significantly more missing-market cases even though its frozen `k=0.00231` makes its *modeled notional* contribution modest. These are separate **coverage tiers**; a second-precision CSV event is not a certified exchange fill, source holding, time-known follower intent or economic return. **E6 remains scientifically incomplete**, and Phase 6A's optimistic stop/DD claims remain unverified. Do not use this secondary tape as a substitute for real CM-002 initial books, funding, NAV or first-known receipts.

Private SHA result: `/home/quant/.local/share/copytrade/reports/phase7_secondary_cm002_native_open_20261104_v1.json`; SHA256 `a9d3ecb7c711fc92bb01b4a56e1d35b6d91e2083a5ccd9fca4624be6b193c1a6`. Reproduce separately using `uv run --frozen --group dev --extra market python scripts/phase7_secondary_cm002_screen.py`; the primary `phase7_native_open_20261104_v1.json` remains unchanged and never mixes weak-source rows.

## VI. Additional candidate investigation and exclusions

The existing bounded 13-wallet *Stage 1* source-turnover screen evaluated **285 three-wallet** and **1,242 five-wallet** combinations with top-ten tables in [the Phase 7 stage report](PHASE7-NATIVE-MINUTE-EXPOSURE-20261104.md). Those rankings measure **gross traded coin composition**, not holding risk, source-equity fitness, matched losses or actual available liquidity. The first-ranked three-wallet screen was `C021-NEAR + ACT34 + ACT39`; the first five-wallet screen was `C021-NEAR + VS030 + ACT34 + N19 + ACT39`. **No selection from these lists is promoted to a recommended alternative.** In particular, a wallet trading one asset with little overlap may *appear* diversified just because its coin is different; that is insufficient to establish economic independence.

Phase 5 B is worth an **independent five-pod paper comparison**, but the Phase 6B source/instrument coverage and conditional shock results make its Gemini 0.46% trailing DD **not independently testable**. P14 remains archived, particularly because the HIP-3 BRENTOIL leg is not in this main-perp-only analysis. Keep previously owner-rejected 22 and currently prop-firm-disallowed additional 25 excluded from allocation.

## VII. Answering the ten research questions directly

1. **Is E6 genuinely better diversified than E2?** **PARTIALLY SUPPORTED**: more observed coin bets (HHI proxy 3.47 vs 1.99), somewhat more opposing same-coin exposures and lower Gemini-modeled P2 DD. **NOT VERIFIED** due to missing CM-002, incomplete books and differing k scalars; lower shock numbers are not a clean causal diversification test.
2. **What did native OHLCV add?** Real observed source-position gross path and actual market-close pricing; ACT04 transient concentration, high hypothetical jump losses, and selected opposite-direction source overlap. Gemini's modeled flatten DD is not a hard gap-risk bound.
3. **Which wallet contributes the most observed tail concentration?** **ACT04**, by peak original gross and frozen-k scaled peak known gross. This does not prove ACT04 is the poorest discretionary trader or that CM-002 cannot dominate an unobserved interval.
4. **Greatest marginal diversification?** Whale_0x5f94 is the strongest *observed conditional* contributor relative to S053. It has mixed same-/opposing-direction exposures. Its net contribution to portfolio expected shortfall cannot be certified.
5. **Any materially stronger alternatives?** **NONE INDEPENDENTLY ESTABLISHED**. The 10+10 new screens are insufficient to supplant frozen E6/E2; Phase 5 B's reported metrics are not independently verified.
6. **Does 5m change outcomes?** Yes for modeled order count; economically, the 10bps notional cost reduction is much smaller, and delay slippage and true follower prices remain UNKNOWN.
7. **Sensitivity to costs and missing books?** High. Cost 2×/3× can be material on a $10k account; E6 is incomplete, HIP-3 excluded and current vendor equity is not historical NAV.
8. **Next paper candidates?** **E6 (primary), E2 (matched risk-budget challenger), P1 (historical reference)**, plus optional Phase 5 B 1× if an entirely separate independently observed worker can establish its account scopes. E3 is a reserve; no combined live account and no qualification.
9. **What could reverse the ranking?** CM-002/Whale source NAV and complete books, large ACT04 short-term exposure, builder markets, stop execution gaps, missing same-minute L2 depth, correlated-loss spikes, actual source/follower receipts and cost assumptions.
10. **What is safe to conclude now?** Gemini conditional E6/E2 preference is reasonable to **test**, not to **deploy**. Real native OHLCV shows concentration and unbounded modeled gap exposure; no real follower PnL, pass probability, alpha claim, hard loss guarantee or certified best alternative has been proven.

## VIII. Reproduction, artifacts and limitations

Scripts (isolated research PR only, without changes to PM03 financial authority):

```bash
uv run --extra market --group dev python scripts/phase7_native_exposure.py --cap-coins 30
uv run --extra market --group dev python scripts/phase7_conditional_stress.py --cap-coins 12
uv run --extra market --group dev python scripts/phase7_delay_cost_screen.py
uv run --extra market --group dev python scripts/phase7_native_open_screen.py
uv run --extra market --group dev python scripts/phase7_secondary_cm002_screen.py
uv run --extra market --group dev python scripts/phase7_universe_screen.py
uv run --extra market --group dev python scripts/phase7_candidate_screen.py /home/quant/.local/share/copytrade/reports/phase7_universe_20261104_v2.json
```

All scripts are read-only except explicit new, non-overwriting research `--output` files. Private alias-to-address binding is now exact-match against the separate Gemini identity evidence (especially the ambiguously named whale), with missing evidence failing closed. Dataset SHA, privacy and source-alias mappings remain owner-private. This report contains **no raw on-chain address map**.

| Owner-private artifact | SHA-256 |
|---|---|
| `phase7_universe_20261104_v2.json` | `2cef0d3a2c28de70a1991043a58de45fc226d6a8ec56b22960c5133909da45ff` |
| `phase7_candidate_screen_20261104_v4.json` | `f36d0fa4ac807d8d570cffb76387e990a6bb62073541fbd5dd3cce1190e3547f` |
| `phase7_native_exposure_20261104_v1.json` | `28acb92b37936888339304109963d6c14911055b0492ad65c07bca7ca7379713` |
| `phase7_conditional_stress_20261104_v3.json` | `e6a38c47dac15ba249f076d7831b470590670285af3da35922b68f45f0dacf9a` |
| `phase7_delay_cost_20261104_v1.json` | `ba778e6094e9b69186fc1a2617cde3b3c8f221ace3c4915d602933c9ee16299b` |
| `phase7_native_open_20261104_v1.json` and reproducibility check `v2` | `03f6f91dcf2f6a061aa79ce776ffd53575abbc802f64cef0c66b53ae69047076` |
| `phase7_secondary_cm002_native_open_20261104_v1.json` | `a9d3ecb7c711fc92bb01b4a56e1d35b6d91e2083a5ccd9fca4624be6b193c1a6` |

**Missing for faithful PM03 account certification:** independent first-known source receipts, atomic initial whole books for every DEX/subaccount, a historical time-series source NAV/collateral/funding ledger, verified liquidity/quote-side and fill latency, user-approved broker rules and independent matured matched follower/control outcomes. None should be fabricated to make a prettier portfolio report.

**The report's purpose is a conditional research decision with explicit uncertainty, not an end-to-end certified financial simulator.**
