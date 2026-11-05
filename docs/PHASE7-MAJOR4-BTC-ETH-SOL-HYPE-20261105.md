# Phase 7 — BTC/ETH/SOL/HYPE wallet-focused portfolio study

**Study:** 2026-08-05–2026-11-03 UTC (90 days, end exclusive); recent segment 2026-10-04–2026-11-03 UTC. Retrospective **traded-notional composition** only, not follower portfolio financial simulation or scientific qualification.

**Recommendation: M4-SPECIALISTS = ACT33 + ACT34 + H02 + W083** (S053-HYPE). A 3-wallet lean comparison and 5-wallet SOL-boost comparison are also retained for prospective research. Existing Gemini E6/E2/P1 frozen portfolios remain unchanged.

## Comparison of proposed portfolio market focus

| Research portfolio | Members | BTC | ETH | SOL | HYPE | Total four-market (90d) | Four-market (recent 30d) |
|---|---|---:|---:|---:|---:|---:|---:|
| M3-BALANCED | H02, VS002, W083 | 25.24% | 13.23% | 13.61% | 27.56% | **79.65%** | **77.28%** |
| **M4-SPECIALISTS** | **ACT33, ACT34, H02, W083** | **29.22%** | **29.55%** | **8.47%** | **19.57%** | **86.81%** | **86.67%** |
| M5-SOL-BOOST | ACT33, ACT34, H02, HX01, W083 | 30.17% | 26.92% | 10.41% | 17.35% | **84.85%** | **80.17%** |

Numbers above are the **equal-wallet arithmetic mean of each leader's share of historical filled USD notional** on those four exact main-perpetual market codes. They are **not actual concurrent positions, risk weights, realized equity allocations or returns**. The actual source-equity-faithful follower cannot be sized from these fractions alone.

### Individual wallet analysis

| Wallet | Stage-1 observation days | Four-market share 90d | Four-market share last 30d | Source fill-position evidence | Value to the proposed portfolio |
|---|---:|---:|---:|---|---|
| ACT33 | 51 | 91.38% | 98.72% | partial consecutive-fill startPosition | BTC specialist; 90-day BTC 90.0%, recent BTC 70.3%, ETH 25% |
| ACT34 | 62 | 100.00% | 100.00% | not available | Consistent ETH-only fill turnover; source opening book and NAV unknown |
| H02 | 56 | 73.86% | 68.17% | CSV fills only | SOL-leaning generalist; SOL 27.1% over 90d and 23.3% recently |
| W083 (S053-HYPE) | 71 | 81.99% | 79.79% | partial consecutive-fill startPosition | HYPE specialist; HYPE 75.4% over 90d and 79.8% recently |
| VS002 | 65 | 83.09% | 83.89% | CSV fills only | Balanced BTC/ETH/SOL/HYPE; recent SOL activity declines to ~1.1% |
| HX01 | 41 | 77.01% | 54.15% | CSV fills only | Additional SOL 18.2% over 90d / 21.3% recently, but overall focus drifts |

All six are **CANDIDATE_UNVERIFIED**, not financially qualified. Wallet aliases ACT33, ACT34, H02, HX01 and VS002 are **original inventory labels bound to exact canonical source addresses** in the current 158-address research cohort. The live wallet-registry alias lookup does not necessarily resolve these non-frozen display labels; use the source-address mapping. W083 resolves through the registry and has the separate historical research alias S053-HYPE.

## Three research hypotheses

**M3-BALANCED — H02 + VS002 + W083.** A simple three-pod design with 79.65% 90-day and 77.28% latest-30-day four-market focus. The historical fractions are BTC 25.2%, ETH 13.2%, SOL 13.6%, HYPE 27.6%, the most evenly distributed of the three presented mixes. Its drawback is position evidence: only W083 has partial fill-to-fill position anchors. H02/VS002 CSV histories do not prove starting account inventories. The mean historical overlap in four-coin gross turnover between wallet pairs is 0.2479; **not a cross-loss or direction correlation**.

**M4-SPECIALISTS — ACT33 + ACT34 + H02 + W083.** Preferred to test because each major is represented by an identifiable trading specialist or SOL-leaning wallet. The four-market share stays stable at 86.81% for the full 90-day cut versus 86.67% in the last 30 days, while the mean four-coin gross fill-turnover overlap is only 0.0934. SOL is still relatively light, 8.47% long window and 6.68% recently. Only two of the four wallets have **partial** source-position anchors; there are **zero independently complete opening account books**. This does not prove economic diversification or profitable copying.

**M5-SOL-BOOST — ACT33 + ACT34 + H02 + HX01 + W083.** Adding HX01 increases the equal-wallet SOL-share proxy from 8.47% to 10.41% in the long window and from 6.68% to 9.61% recently. It also reduces total four-market focus in the latest 30 days to 80.17% because HX01 itself shifted from 85.60% in the earlier 60 days to 54.15% in the latest 30. Its turnover overlap is 0.1872 and it retains only two partial source-position anchors. Treat this as a SOL-boost comparison, **not** a superior trading portfolio merely because it has more managers.

### Rejected tempting substitutions

- ACT39 has 100% historical BTC fill turnover and 53 observation days, but no verified source startPosition book. We retain ACT33 for partial position-chain evidence; ACT39 is an optional BTC concentration stress control.
- ACT36 traded 26.9% SOL over the full 90 days, but exceeded 100 fills per active observation day (high churn) and **its four-major share was 0% in the recent 30-day sample**. Not recommended.
- ACT30's earlier HYPE/SOL orientation shifted to recent BTC-only four-major turnover. Avoid selecting it as a stable HYPE or SOL specialist solely from the 90-day aggregate.
- There is **no stable SOL-majority specialist** in the current non-rejected 158-wallet research cohort: SOL's highest 90-day share is N05 29.9%; H02 27.1%; ACT36 26.9%. H02 gives some SOL coverage without making SOL the dominant trade source.

## Acquisition, admission and scientific limits

- Registry observed 2026-11-04T09:36:57.574969+00:00, SHA e2836aab5ef6ef79306e9dfe732d8768c3b1ca6af29efbda066b37f03646a18f. Status checked CURRENT, 158 research addresses (108+20+30), 22 owner exclusions.
- Original Phase 7 union has 188 sources. Restricting to current research cohort, non-rejected Stage 1, at least 40 observation days, <=14 days since last fill, at most 100 fills per active observation day, >=80% default-perp fill count, and either >=60% four-market turnover or >=15% SOL turnover gives **24 candidate wallets**.
- Tested **55,154** combinations of 3, 4 and 5 of those 24 wallets: 2,024 three-wallet, 10,626 four-wallet, 42,504 five-wallet. **3,193** combinations met at least 75% four-market fill turnover and at least 7.5% average turnover share on *each* of the four markets: 115/645/2,433 by portfolio size. These are correlated retrospective trial counts, **not economic backtests**.
- The latest-30-day figures were independently recomputed from existing JSON and local CSV sources. The SHA-256 of each selected original source was checked against the immutable Phase 7 Stage-1 source catalog; every selected wallet's full-window coin shares also matched the frozen aggregate within 0.2 percentage points. The original CSV may not include source exchange transaction IDs; no invented TID-based deduplication.
- The partial consecutive-fill startPosition intervals are insufficient to reconstruct the entire whole-wallet book. The two CSV-only leader sources in the preferred M4 have no independent opening-position anchor; wallet equity, leverage, fees, funding, other markets and subaccounts remain unknown.
- **No follower PnL, maximum drawdown, first-known event clock, executable price, prop-firm pass likelihood, untouched holdout or valid trading sizing was produced.** An additional future paper observation and source-account reconstruction would be required. No new fills were downloaded. No live worker, paper run, registry selection, frozen E6/E2/P1 version or broker account was mutated.
- **Do not silently filter other leader coins to these four pairs for a real follower.** Such a policy changes the copied strategy and requires an independent registered protocol.

## Reproduction and private artifact

Script: scripts/phase7_major4_portfolio_screen.py; test module: tests/test_phase7_major4_portfolio_screen.py.

Immutable private report:
- /home/quant/.local/share/copytrade/reports/phase7_major4_registry_screen_20261105_v2.json
- SHA256: 451dbe71e3d9c322a96f3328f3de1845719eaec547ed70747cdda7fdb0786c43

To reproduce, pass the immutable Phase 7 source universe JSON to the script with --root /home/quant/dev/copytrade-pm and a *new* --output path, plus the current private SQLite research registry. No network connections are made. Existing source data remain read-only.
