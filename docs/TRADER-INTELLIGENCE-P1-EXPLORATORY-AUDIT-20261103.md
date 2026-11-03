# Trader Intelligence P1 — prospective-journal, retrospective-analysis audit

**Executed:** 2026-11-03 UTC. **Disposition:** `NOT_SCIENTIFICALLY_QUALIFIED` for all three P1 wallets. This is an **already-inspected exploratory period**, **not** the Nov 4 future holdout or a statement about executable Propr returns.

## Source and durable provenance

The live read-only opportunity journal reported 75,469 first decisions across 189 wallet IDs on the first inspection, with first-known receipts from 2026-10-13 through 2026-11-03. P1 aliases were joined **privately** to exactly named existing 90-day wallet files without printing their addresses. Matching first-decision counts were S035-ENA **217**, S051-BTC **133** and S053-HYPE **362** (712 total). These are source *first decisions*, not independent trade episodes or evidence of a continuously observed whole wallet.

For replay diagnostics we **reused** `hyperliquid-expert-ensemble/src/ensemble/wallet_audit.py` (the existing causal-cost, verified-clock, overlapping-episode, matched-market-control and day-block uncertainty validator), not a replacement simulator. Its live read-only `load_episodes` returned **50,758** accepted overlap-adjusted episodes, of which **50,266** had usable paired market controls, across all observed wallets at that inspection.

Full official `wallet_audit` CLI completed a separate private generation, at:

`/home/quant/.local/share/copytrade/reports/ti-p1-shadow-audit-20261103-001/`

- `manifest.json` SHA256: `3c579ba06d16857f39b840d3dccdab4df7bb9bf88112f195fc3087d358c54e27`
- `executive.md` SHA256: `2168c2521239d08ec900ef121fda21e10eacf6bb667668bd4f56824a06afab95`
- `predictive_leaderboard.csv` SHA256: `e4f654ec78fc7c7e4833f62352461e9269cce5af40b84dd9c8bea4d02f2ed820`
- Private generation mode **0700**; manifest mode **0600**. Private wallet IDs and raw evidence are **not in Git**.
- Source scan at the report's sampling cut: **75,472** opportunity decisions, **1,095,398** source-ledger sequence, **217** historical source wallets, **215** with at least one valid source-equity snapshot. That does **not** attest continuous whole-account NAV or source book.
- The full market-control study had **11,146** paired overlap-adjusted 1h episodes; 124 wallets received **provisional exploratory** labels, **zero scientifically qualified**. Its horizon-wide mean incremental returns are not a predeclared wallet-selection result and may be biased by post-selection.

## P1 source-wallet diagnostic

Cost-model values are **10-bps-midpoint markout proxies**, not independently observed executable follower fills, not 300-second wait-plus-single-market-order economics, and not an account-specific Propr fee schedule.

| Wallet | Horizon | Deduplicated paired episodes | UTC days | Mean hypothetical net | Mean increment over matched market |
| --- | --- | ---: | ---: | ---: | ---: |
| S035-ENA | 5m | 16 | 8 | -24.198 bps | -17.656 bps |
| S035-ENA | 15m | 16 | 8 | -16.202 bps | -19.650 bps |
| S035-ENA | 1h | 16 | 8 | -111.405 bps | -70.024 bps |
| S051-BTC | 5m | 12 | 9 | -14.788 bps | +3.432 bps |
| S051-BTC | 15m | 12 | 9 | +0.061 bps | +16.509 bps |
| S051-BTC | 1h | 11 | 9 | -13.385 bps | +5.686 bps |
| S053-HYPE | 5m | 64 | 16 | -8.813 bps | +2.421 bps |
| S053-HYPE | 15m | 63 | 16 | +2.198 bps | +24.457 bps |
| S053-HYPE | 1h | 56 | 16 | +12.738 bps | +53.739 bps |

**Dependence-aware day-block uncertainty (1h)** from the existing validator's seeded exploratory bootstrap. Confidence intervals refer to *equal-day incremental* return, not the episode-weighted mean above.

| Wallet | Valid source coverage | Equal-day mean vs market | Exploratory 95% interval | Holm-adjusted exploratory p | Mean sampled entry delay after actionable |
| --- | ---: | ---: | ---: | ---: | ---: |
| S035-ENA | 3 / 16 | -104.195 bps | [-260.685, +38.652] bps | 1.0 | 24.2 s |
| S051-BTC | 2 / 11 | -0.648 bps | [-34.382, +28.540] bps | 1.0 | 34.4 s |
| S053-HYPE | 7 / 56 | +37.128 bps | [-26.287, +96.271] bps | 1.0 | 31.6 s |

The HYPE observed mean is **not distinguishable from zero**, with large uncertainty and **49/56** episodes failing verified source-coverage status. ENA is strongly negative as a *diagnostic sample* but its interval still crosses zero. No "three profitable managers" or calibrated A/B ranking follows from these data.

## Binding limitations

1. **Selection and hypothesis history are contaminated:** P1 was chosen using earlier wallet/backtest inspection. The evaluated Oct–Nov window is not an untouched future trial.
2. **Action convention is wrong for TI-04 final qualification:** the existing producer uses a short early-action assumption, sampled market midpoint and fixed hypothetical 10-bps cost. It does **not** implement the portfolio's five-minute waited market-order fill or native independently verified spread, depth, funding and Propr execution.
3. **Coverage and equity are incomplete:** partial source observations and occasional source-equity snapshots do not reconstruct a complete whole-book, continuous NAV, spot, funding and subaccount account ledger.
4. **Uncertainty invalidates positive alpha claims:** all three 1h intervals include zero, Holm-adjusted p-values are 1.0, and the study has only 8–16 distinct sampled UTC days. Clone/parent histories and held-out selection are not independently validated.
5. **No signed mature matched whole-account follower outcomes:** the existing `ProspectiveLedger` supports external Ed25519 signatures but no verified real matched-outcome producer was located in inspected source paths. The new read-only `trader_intelligence_qualification_cli` cannot manufacture this evidence.

**Decision:** Retain **C/X at 0R**, no order authority, and **NOT SCIENTIFICALLY QUALIFIED** for P1. Do not blacklist/replace ENA or pick HYPE alone from this test without disclosing a new adaptive selection trial. The [Nov 4 future study proposal](TRADER-INTELLIGENCE-PROSPECTIVE-STUDY-20261103.md) is a **new prospective validation candidate**, not a backdated repair or currently active validated capture campaign. No production Telegram or broker service was modified.
