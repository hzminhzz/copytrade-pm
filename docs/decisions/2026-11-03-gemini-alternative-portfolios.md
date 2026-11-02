# Gemini Phase 2 — preserved alternative portfolio registry

- **Recorded:** 2026-11-03 (Asia/Bangkok; 2026-11-02 UTC)
- **Source:** user-supplied `Hyperliquid_Phase2_Deep_Wallet_and_Portfolio_Optimization.pdf`, Reports B–D, pages 3–4; these are **Gemini-reported modeled results**, not independently qualified follower returns.
- **Decision status:** **ARCHIVED AS ALTERNATIVES — NOT SELECTED, NOT DEPLOYED**.
- **Primary user-approved roster:** **`S053-HYPE + S051-BTC + S035-ENA`**; see [the binding selection decision](2026-11-02-gemini-selected-three-pod.md). Recording these choices does not amend it.
- **Scope:** preserve the alternative wallet membership and original risk-normalization scenarios for future comparisons and optional separately approved demo/paper experiments. Do not use this registry as an automatic fallback or deployment allowlist.
- **Later Phase 3 decision:** [2026-11-03 Phase 3 adoption and planned 180-day research](2026-11-03-gemini-phase3-adoption-180d.md). Phase 3's `P1/P14/P15/P16` refer to new candidate variants and **do not overwrite** this Phase 2 archive.

## Alias and input conventions

- Gemini abbreviates `S064-BRENT` / `S064`; the local dataset uses **`S064-xyz:BRENTOIL`**. Resolve this alias via the owner-private source roster before observing or trading. The source wallet also trades other instruments: the label does **not** imply a BRENT-only strategy.
- Other abbreviations expand as follows: `S053`=`S053-HYPE`, `S051`=`S051-BTC`, `S035`=`S035-ENA`, `C026`=`C026-XMR`, `C017`=`C017-HYPE`, `S021`=`S021-HYPE`, `S060`=`S060-HYPE`, `S048`=`S048-BTC`, `S058`=`S058-PUMP`.
- Original Gemini experiment: $100,000 modeled account, five-minute batched follower, training Aug 4–Sep 17 and claimed validation Sep 18–Nov 2, 2026. **Every monetary return, drawdown, and pass percentage below is a reported model output, not a prediction or verified outcome.**
- The $10,000 equivalent *nominal risk budgets* are divided by ten. **Do not divide Gemini's simulated PnL by ten and treat it as an independently executable $10,000 result**: lot sizes, liquidity, fills, slippage, funding, venue scope and actual account constraints can be nonlinear.

## Three-wallet combinations — Gemini Report B

All three-pod scenarios assume **2% nominal loss budget per pod**, **6% nominal total** ($2,000 × 3 on $100k; $200 × 3 on $10k).

| Gemini ID / mandate | Exact canonical wallet set | Gemini modeled net on $100k | Gemini modeled worst day | Gemini modeled maximum trailing DD | Gemini modeled pass fraction | Status |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| **3W-1 Best Balanced** | `S053-HYPE` + `S051-BTC` + `S035-ENA` | +$35,213 | −3.64% | −3.84% | 80.3% | **SELECTED PRIMARY** — separate canonical decision |
| **3W-2 Best Conservative / Low-DD** | `S053-HYPE` + `S035-ENA` + `S064-xyz:BRENTOIL` | +$32,455 | −2.17% | −2.98% | 77.0% | ALTERNATIVE |
| **3W-3 Conservative Crypto-Only** | `S053-HYPE` + `C026-XMR` + `S035-ENA` | +$30,735 | −2.26% | −3.37% | 78.7% | ALTERNATIVE |
| **3W-4 Aggressive / Fastest Target** | `S053-HYPE` + `C017-HYPE` + `S035-ENA` | +$33,274 | −2.98% | −5.20% | 78.7% | ALTERNATIVE |
| **3W-5 Aggressive Macro + Multi-Asset** | `C017-HYPE` + `S051-BTC` + `S035-ENA` | +$33,483 | −4.59% | −7.97% | 80.3% | ALTERNATIVE |

These are **four distinct alternate 3-pod memberships**, not four deployments. In particular, 3W-2 is Gemini's *modeled* lowest-drawdown option, while 3W-4/3W-5 materially increase modeled tail loss. `C026-XMR` showed averaging-down behavior and Gemini used an unusually high **8.0× frozen k** in its own model; never copy that multiplier into live sizing.

## Five-wallet combinations — Gemini Report C

**Two risk models must remain separate:**
- **Standard 5 pods:** $2,000 modeled risk/pod on $100k = **10% combined nominal**; $200/pod on a $10k challenge = $1,000 combined.
- **Risk-normalized 5 pods:** $1,200 modeled risk/pod on $100k = **6% combined nominal**; $120/pod on a $10k challenge = $600 combined. This makes the total nominal risk comparable to the 3-wallet design.

| Gemini ID / mandate | Exact canonical wallet set | Nominal risk / $100k | Gemini modeled net / $100k | Modeled worst day | Modeled trailing DD | Modeled pass fraction | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| **P5-1 Balanced All-Weather** | `S053-HYPE`, `C026-XMR`, `S051-BTC`, `S035-ENA`, `S064-xyz:BRENTOIL` | 10% | +$45,328 | −3.90% | −5.45% | 82.0% | ALTERNATIVE |
| **P5-1N Risk-Normalized** | *Same five identities as P5-1* | 6% | +$27,197 | −2.34% | −3.27% | 77.0% | ALTERNATIVE — distinct sizing policy |
| **P5-2 Highest-Profit Multi-Asset** | `S053-HYPE`, `C017-HYPE`, `S051-BTC`, `S035-ENA`, `S064-xyz:BRENTOIL` | 10% | +$47,867 | −4.62% | −6.99% | 82.0% | ALTERNATIVE |
| **P5-3 Low-Stop-Out Macro/Trend** | `S053-HYPE`, `C026-XMR`, `S051-BTC`, `S035-ENA`, `S021-HYPE` | 10% | +$44,176 | −3.78% | −6.01% | 80.3% | ALTERNATIVE |
| **P5-4 Highest Pass-Rate Crypto-Only** | `S053-HYPE`, `C017-HYPE`, `C026-XMR`, `S051-BTC`, `S035-ENA` | 10% | +$46,148 | −4.88% | −8.59% | 83.6% | ALTERNATIVE |
| **P5-5 High-Beta Majors Momentum** | `S060-HYPE`, `S053-HYPE`, `S051-BTC`, `S035-ENA`, `S021-HYPE` | 10% | +$43,251 | −4.25% | −7.61% | 78.7% | ALTERNATIVE / HIGH-BETA |

There are **five distinct alternative 5-pod wallet sets**, with **six retained configurations** because P5-1 and P5-1N use different risk budgets.

### Historical exclusion benchmark — not an eligible alternative

| Gemini ID | Wallet set | Gemini report outcome | Disposition |
| --- | --- | --- | --- |
| **P5-6 Original Phase 1 Ensemble** | `S048-BTC`, `S060-HYPE`, `S053-HYPE`, `C017-HYPE`, `S058-PUMP` | Rank #233/252; modeled worst day **−6.17%** breached its assumed 5% daily limit | **REJECTED comparator**. Never silently return to this roster. |

## What Gemini concluded, versus what is actually decided

**SOURCE REPORT:** Gemini preferred 3W-1 for modeled return per unit of equal total nominal risk; 3W-2 for lowest modeled drawdown. At the same 6% combined risk, Gemini argued that P5-1N (five wallets at 1.2% each) was less efficient than the three-wallet portfolios. The reported 5-wallet percentages used partly overlapping starting windows; they are **not calibrated real-world pass probabilities**.

**CURRENT USER DECISION:** Only **3W-1** is approved as the *next demo/paper implementation roster*. All 3W-2 through 3W-5 and P5-1 through P5-5 remain **alternative research candidates**. No alternate is automatically activated after a wallet disconnection, halt, poor drawdown, missing source equity, or untradeable hedge. Fail closed and record the problem.

**VERIFICATION LIMIT:** Prior local work confirmed some source realized PnL and conducted incomplete native 1-minute PM03 research, but did **not** establish Gemini's exact report rankings, claim of 120/252 executed configurations, forecast pass rates, independently observed follower alpha or verified Propr execution for these alternatives. The report's missing-`closedPnl` and unique-wallet claims also differed from a subsequent local source-cohort audit. This registry **quotes Gemini's proposals without endorsing their numerical results**.

## Conditions for evaluating or promoting any alternative

1. **Explicitly choose a different candidate**, document why the primary is unsuitable, and record a dated superseding decision; preserve the original decision and identity manifests.
2. **Verify complete source account identity** (parent/subaccounts/all-DEX), prospective first-receipt timestamps, positions, collateral and equity. Different instrument labels are not proof of independent manager risk.
3. **Check supported Propr instruments and hedges before sending orders.** In particular, `S064-xyz:BRENTOIL` must not be assumed wholly executable, and source `C026-XMR` sizing may involve large multipliers or unusual inventory behavior.
4. **Apply the existing copytrade-pm follower architecture:** source-equity-relative **whole-book intent**, 300-second first-signal batching, consolidated PM03/PM04 risk budget, independent pod attribution, market capacity, durable intent journal, and broker reconciliation. Do not reuse Gemini's frozen ratios as order sizes.
5. **Separate three-wallet vs five-wallet total risk.** Do not claim a 5-pod portfolio is more robust solely because its reported gross PnL is higher while its total nominal risk rose from 6% to 10%.
6. **Advance only through read-only capture → offline/paper → separately authorized Propr demo**; no automatic transition to live/funded account. Recheck actual demo equity and contract terms.

## Source pointers

- User-provided **`Hyperliquid_Phase2_Deep_Wallet_and_Portfolio_Optimization.pdf`**, Reports B, C, D (pages 2–4). Values recorded above are source-reported **MODELED**, not re-verified on this documentation task.
- [User-selected primary portfolio](2026-11-02-gemini-selected-three-pod.md) (merged via [PR #37](https://github.com/hzminhzz/copytrade-pm/pull/37)).
- [Previous exploratory native 94-wallet PM03 research — PR #25](https://github.com/hzminhzz/copytrade-pm/pull/25).
- [Qualification and evidence tiers](../QUALIFICATION.md).
- [Source-equity follower sizing](../EQUITY-WEIGHT-SIZING.md).
