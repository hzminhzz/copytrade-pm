# Phase 6A input reconciliation and Phase 6B v19 audit — 2026-11-04

**Status:** Phase 6A report imported as an *external, conditional research claim*, not as verified follower-account economics. Phase 6B independent data/engineering audit completed; **scientific qualification NOT ESTABLISHED; no authorization for real orders**.

This follows [the prior Phase 6B v13 evidence record](PHASE6B-RECOVERY-SCENARIOS-20261104.md) without changing its immutable SHA generations. It uses the Gemini documents supplied in the ChatGPT conversation as **untrusted research inputs**, not an API/live execution signal. The attached files were not committed or copied to the VPS.

## Source identities and reproducibility limit

| Uploaded source | SHA-256 | Notes |
|---|---|---|
| `Hyperliquid_Phase6A_Adversarial_Risk_and_Survival_Report_20261104.pdf` | `34eb7047a13ada7a42556a150fd4fd9dc1be86601d254ee3fb57442c528d355f` | 9-page report, conditional hourly MTM and forced-flatten assumptions |
| `Phase6_Portfolio_Survival_and_Decision_Matrix_20261104.csv` | `0a9164b4f37068df346618db851f70814124a17a1c6d6f659b303edcd41f540d` | 24 policy/scenario rows across six portfolio variants |
| `Phase6_Failed_Assumptions_and_Forensic_Audit_20261104.csv` | `0c1764101e25939deb5d1f0dc7a5115bfac48b62f7bc150e9075c6d9234157ac` | 5 issue rows, not independently reproduced by this repo |
| `Pasted text(20261104-073513).txt` | `6fd6877a0a0caa88d69c8b830feb4b3efdf8c9490d943a359b99b08a7db503a7` | Human-readable summary; should not override the CSV |

Gemini mentions a scenario/kill-switch event log with 190+ rows and a reproducible configuration JSON. **Neither file was attached**. No original 1-hour synchronized equity/event trajectory, fill-level simulated follower execution records or audited `P2_flatten` source code were supplied. The reported challenge pass/breach sequence is therefore **not independently reproducible** from the supplied attachments.

## Material inconsistencies in the supplied Phase 6A outputs

1. **Portfolio B (1×), P2_flatten:** PDF page 4 and executive summary report **$11,550 (+15.50%)**, **4.02%** maximum trailing DD. The decision CSV records **$11,553.17 (+15.53%)**, **4.01%** trailing DD. These are conflicting output versions, not a precise SHA-linked single run; do not choose the nicer result.
2. **Per-pod gross-notional ceiling:** PDF page 6, P2_flatten policy table recommends **0.35×** pod allocation for N01/ACT08. PDF pages 8–9 and the text summary recommend **1.5×**. This is a material **4.29×** ratio conflict; the exact cap is **UNRESOLVED**, and no production/forward-paper policy mutation is approved on its basis.
3. **N07 absolute loss normalization:** The forensic CSV describes **-$7,525 / -7.53%** loss at 1× and says DASH **-$4,211** and VIRTUAL **-$3,032**. PDF pages 1–2 report **-$752.54 / -7.53%** for the $10k account (DASH **-$421.14**, VIRTUAL **-$279.49**). This appears consistent with a **10× account-scale mismatch**, but neither attached artifact provides a linked accounting ledger proving the conversion.
4. **Study-clock parity:** The report refers to Aug 5 through Nov 3 inclusive (91 UTC calendar dates if both full days) while the New-50 frozen VPS source window is **2026-08-05 04:30 UTC to 2026-11-03 04:30 UTC** (**90×24h**). The provided CSV does not contain a fully bound start/end or receipt-clock manifest. Reported 90d returns are not a direct like-for-like comparison.
5. **Claims of verification:** `FILL_VERIFIABLE` validates observed source fills and position-before fields, **not** the completeness of all source accounts, native mark/oracle price paths, fees, liquidation execution or prospective first-known. Reports of `PASSED` remain **conditional simulations**.

## Core Gemini finding that survives independent scrutiny

The methodology objection is sound: **realized-only closed-trade PnL is not a prop-firm drawdown measure** when substantial positions remain underwater. N01's NEAR/BTC short risk, ACT08 short inventory and N07's extended losing-long inventory are valid *research warnings* requiring account-wide MTM and stress-sensitive controls.

The external numbers remain unverified here. Gemini's favored **Portfolio B (1×)** with `P2_flatten` claims +15.50%, 2.58% daily and 4.02% trailing drawdowns *under its specified conditional simulation*. Its own evidence also models breach from a +20% short squeeze and from the Sep 17–21 kill-switch outage. Therefore it is a **conditional forward-paper experiment only**, **not a live account candidate or proven challenge pass**.

No automatic `P2_flatten` trading policy was deployed by Phase 6B. The Phase 6B S1–S8 model evaluates *one-step known-leg sensitivities*, and actual PM-03 `classify` tests exercise **unknown-source negative admission**. A supervisor RED/block on unknown source does not prove flatten orders execute, fill, settle or survive an outage.

## Independent Phase 6B source-scope correction and v19 results

Official Hyperliquid API documentation defines spot identifiers `@{index}` and `PURR/USDC` separately from perpetuals. The ACT08 raw 5,475-fill file on the VPS contains **exactly four `@107` spot fills**. Those four rows are preserved in the immutable source SHA, but excluded from **perpetual-only position chains and the 1m perp coverage universe**. Their spot/collateral contribution remains **UNKNOWN** in whole-account equity. Numeric linked fills and same-ms continuity remain constrained by the original source and never fabricated.

| Independent v19 metric | Verified result |
|---|---|
| Wallet source files SHA-bound | 7 |
| H21 / H17 source fill availability | 749 / 1,503 raw fills verified in frozen New-50 files |
| Total raw source fills in frozen seven-wallet files | 18,592 (including the 4 ACT08 spot fills) |
| Native *perpetual* instruments inventoried | **95** |
| Fully verified native 1m symbol coverage across 90d | **26 / 95** |
| Conditionally nonzero observed source exposure-minutes **on unverified market days** | **348,758** |
| Stress research | 540 retrospective snapshots; **not** full-book execution |
| Native PM-03 negative admission | 540/540 RED, zero new-risk permissions |
| Full account economics matrix | 180 scenario rows **BLOCKED_NOT_RUN**, no PnL/first-passage fills invented |

**Updated private immutable SHA generations:**

- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-coverage-v14/` — unmodified source-file SHAs; distinct spot exclusion ledger
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-minute-v15/` — 95 pure-perp instruments, exact native minute SHA audit
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-observed-exposure-v16/` — nonzero-perp inventory interval audit, excluded spot count reconciled
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-snapshot-stress-v17/` — 540 conditional S1–S8 snapshots without spot as a perp
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-blocked-scenarios-v18/` — immutable no-economic-output matrix
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-final-disposition-v19/` — cross-generation SHA signoff, explicit spot-exclusion consistency and zero true qualification

Historical 8-account sparse public portfolio observations remain in `phase6b-portfolio-history/g20261104Phase6BPortfolioHistoryV1/` and are bound into the final generation. v4/v6/v10/v11/v12/v13 still exist as **previous dated evidence**, not silently rewritten.

## Distinct data gates for actual scientific progress

1. **Historical first-known/whole-book:** Retrospective HyperX/Hyperliquid fills do not provide verified original local receipt clocks, complete parent/subaccount collateral/equity/funding or continuity of absent positions. Future prospective research must record authenticated local first-known and all-DEX snapshots with replayable receipts.
2. **Mark-price vs trade-price:** `ml4t-data` canonical `HYPERLIQUID_*_1m` partitions are **trade-derived OHLCV**, not native Hyperliquid oracle/mark-price candles. Never label trade-price proxies as exact exchange liquidation marks. Binance or Arcus marks are not permissible substitutes. Official Hyperliquid docs: https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data and https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint .
3. **Funding and execution:** Hyperliquid public `fundingHistory` and `userFunding` endpoints exist, but missing historical ownership, position scope, same-hour mark and liquidity prevent settled follower carry from being established merely by querying rates. Market depth and final simulated fill/cancel/reconnect evidence still require separate, recorded data.
4. **Policy / platform terms:** The `P2_flatten` 0.35×/1.5× cap conflict, reference $500 daily / $1,000 trailing loss rules and actual Propr stage/day-reset/collateral definitions need a separately frozen, verified policy before implementing a risk-authorized paper supervisor.
5. **Forward-paper bridge:** Link to the independent FP-01..FP-15 prospective worker campaign for matched simulated fills, online MTM, persistent kill-switch decisions, explicit flatten receipt/partial-fill proof and freeze-on-unknown. Research decisions are not authorizations for a broker route.

**Disposition:** Treat Gemini's recommendations as *testable hypotheses*. For selection, `Portfolio B (1×)` is the leading **conditional paper-only research candidate** relative to the supplied alternatives, but no portfolio has demonstrated independently verified historical 90d follower-equity survival. Keep PR #74 research-only; no merge into broker or production service, no research result promoted to qualified.
