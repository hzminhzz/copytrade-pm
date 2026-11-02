# Wallet selection for fixed-loss prop-challenge pods

**Status:** Research policy and operator checklist, not a qualified roster or live-trading authorization. **Decision date:** 2026-11-02. **Repository baseline:** `d11d754660714a2572ad1c6b91680a89b9d5e397`. **Owner intent:** three independent source-wallet portfolio managers, each with a nominal loss budget of 2% of a $10,000 challenge ($200); source-equity-relative position sizing; five-minute rebalance batching; no 1:1 fill-copying or HFT.

Read with [INDEX](INDEX.md), [EQUITY-WEIGHT-SIZING](EQUITY-WEIGHT-SIZING.md), [QUALIFICATION](QUALIFICATION.md), [PM-04](PM-04-shadow-hardening.md), [DATA-ACQUISITION](DATA-ACQUISITION.md), and [BLOCKER-RECOVERY](BLOCKER-RECOVERY.md). Qualification terminology and account-contract rules live in those documents, not here.

## Objective and non-negotiable distinctions

**Optimize a three-wallet follower portfolio's probability of reaching the *account-specific* challenge profit target before any real account rule breach.** Do not rank primarily by leader leaderboard PnL, advertised ROI, closed-fill win rate, or an isolated wallet's smoothness.

- **Pod risk budget = $200 nominal loss capacity, not $200 deployable capital or a guaranteed worst loss.** Three budgets total $600 / 6%; this **exceeds** a hypothetical $500 / 5% daily threshold. The account supervisor has priority over pod intent and must halt or reduce exposure with a tested buffer; stops can overshoot because of gaps, slippage, fees, liquidation and stale state. Do not assume correlation disappears during stress.
- Treat each wallet as an **independent portfolio manager**, including its entire long/short inventory, adds, reductions, financing and changing source account equity. Do not transform each fill into a fixed-size signal.
- For instrument `i`, target dollar notional before guards is `pod_virtual_capital * (leader_signed_notional_i / leader_equity_as_of)`; then apply the common pod risk scale `k`, allowable-market and gross/concentration caps, and account risk supervisor. Example: $100k leader equity and +$300k BTC position, $2k pod virtual capital, `k=1` => +$6k BTC desired notional, **not** +$2k. `k` must be predeclared/calibrated on training evidence, not adjusted after seeing held-out outcomes.
- Pod attribution and stop budget are **separate** from account-level risk and from source-wallet notional sizing. Cross-pod positions net at broker/account execution; retain pre-net attribution, order/fill/cancel race state, reservations and HALT journaling. A risk-stop may truncate source fidelity; quantify that divergence.
- **Five minutes since first known source change:** group same-window changes to one desired target per instrument, then execute a single hypothetical market rebalance after the deadline using information available *then*. Reductions/halts for safety may act earlier as independently specified policy. Revisit unknown source updates, missed trades and first-known clocks explicitly.
- The 2% pod budget and account buffer are **research hypotheses**. Firm variant, daily reset timezone, floating-PnL accounting, profit target, trailing/static floors, copying/API restrictions, instruments and leverage must be validated for the **specific** challenge account against dated official/versioned evidence. No assumption that all Propr challenges share a 5% limit. This repo places no real orders.

## Preferred wallet archetypes and trade-offs

| Archetype | Screen result | Why / test |
| --- | --- | --- |
| Controlled medium-frequency directional/swing PM | PRIORITIZE | Repeatable risk sizing, multi-hour holds, meaningful positions; check 5-minute execution decay |
| Selective higher-volatility directional PM | EXPERIMENT | Fixed follower risk permits rougher equity curves **only** when realistic loss truncation leaves positive net R |
| Differentiated long/short basket PM | EXPERIMENT | Potential diversification; demand entire book including hedges and Propr-eligible execution |
| Concentrated single-coin whale | CONDITIONAL | May drive fast target gains but large adverse excursions, hard-stop breaches and shared coin beta |
| High-fill-count trader | INVESTIGATE, not auto-reject | Millions of partial fills may collapse into few order IDs/decision episodes; measure effective turnover after batching |
| HFT scalper, market maker, latency/rebate arbitrage | REJECT for 5m follower if edge disappears | Five-minute batch and market orders cannot replicate maker economics |
| Martingale / unbounded losing-side averaging | REJECT | Multiple small realized wins can conceal unrecoverable floating drawdown |
| Incomplete hedged/cross-venue strategy | BLOCK | Visible Hyperliquid leg is not whole economic strategy; omitted hedge changes the thesis |
| Illiquid/outside-account-market strategy | BLOCK or REJECT | No faithful, executable follower book or risk proxy |

**Heuristics, not hard admission gates:** prefer median reconstructed *episodes* lasting roughly 10-72 hours, active decisions across multiple independent market days, liquid Propr-supported assets, source gross/equity generally in a tractable range, and diverse downside return drivers. Never impose a universal 1-3x leverage or win-rate cutoff without testing the interaction with $200 loss and target. Historical return-to-drawdown, tail adverse excursions and stopped follower R matter more than leader display leverage.

## Candidate intake checklist (check each; record PASS / FAIL / UNKNOWN + evidence SHA)

### A. Identity and discovery (D0-D1)
- [ ] Canonical 0x address, optional alias, discovery time UTC, source(s), provider endpoint and exact date window retained; deduplicate related/subaccounts and aliases; use a versioned new cohort rather than editing the frozen 36-wallet manifest.
- [ ] Confirm active equity and meaningful recent position *decisions*, not just nonzero balance; inspect dormant/wiped wallets using existing dated exclusion registries before spending API quota. A historical zero-equity snapshot does not prove permanent death.
- [ ] Capture **whole-wallet**, not single-coin, realized + unrealized PnL, fees, funding, deposits/withdrawals and collateral/positions where available; distinguish missing data from zero.
- [ ] Split by months and market regimes. Mark concentration of economic profit into one open position, one month, one token or a few outsized events. Source selection from the same backtest period = in-sample, regardless of later split.
- [ ] Treat 100% trade wins or enormous closed trade counts as a **measurement alarm**: closed partial fills are not position episodes; losing open PnL may be invisible; compare full trade history and account-level NAV. Nansen labels alone are not verified strategies.

### B. Reconstructability / fidelity (D1-D2)
- [ ] Reconcile HyperX raw historical fills, pagination, duplicates/order IDs/TIDs, event order and position-before/after chains; preserve source hashes and original pages off Git.
- [ ] Group partial fills by order/causal episode; count distinct decision windows, distinct risk bets, median holding time and source rebalancing tempo. Do not infer strategy cadence from fill count.
- [ ] Reconstruct source inventory as a *whole book*, including carried positions at cutoff, new subaccounts, liquidation, cross/instrument hedges, funding and changes in equity. As-of leader equity/positions must have legitimate availability timestamps; today's snapshots cannot prove historical Q3 information.
- [ ] Audit symbol membership and minute coverage for every economically relevant leg, plus exact account Propr universe and price/volume/market limits. Missing hedge/mark/execution is BLOCKED, not excluded as an unprofitable outlier.
- [ ] Distinguish (1) vendor event time, (2) first observed receipt, (3) decision time and (4) hypothetical market fill. Retrospective reconstruction cannot manufacture first-known time. Qualify only on independently audited prospective observations.

### C. $200 pod risk replay (D3 research only)
- [ ] Freeze account starting equity, **pod loss budget $200**, virtual capital and `k` definition, initial holdings, firm variant and rule snapshot, allocation/reset policy, costs, slip, stale/kill behavior and candidate set *before* outcome evaluation.
- [ ] Size by signed `leader_notional / source_equity_as_of`, not fixed lots, equal signal weights, or initial-fills-only. Reconstruct missed-trade catch-up as latest executable target; log target/executed tracking error.
- [ ] Replay synchronized 1-minute price marks with 5-minute first-known batching, independent pod fees/funding/realized/unrealized PnL, per-pod stop buffer and execution overshoot. Do not confuse source gross PnL with follower PnL.
- [ ] Carry stop events as terminal or defined re-entry states; keep skipped/missing and rejected instrument outcomes visible. A portfolio that only succeeds by repeatedly circumventing pod stops is unsuitable.
- [ ] Compare latency 0/5/15 minutes and cost 1x/2x/3x, spread/liquidity shocks, coin shocks, source equity stale/gap, source sizing change and unhedged exposure. Show all attempted cases.
- [ ] Compute **net R = net follower PnL / $200**, stop-out frequency, maximum adverse excursion (MAE) in R, worst intraday equity drawdown, time underwater, CVaR/tails, volume/capacity, target-time and number of independent economic episodes.
- [ ] Track pod/account **attributed** risk vs common broker *netted* book; total gross coin cap and concentration cap, inflight reservations, and the binding account supervisor. Test all-three-stop concurrent scenario ($600 plus overshoot), correlated gap, missed cancel/fill and stale snapshots.
- [ ] For a hypothetical $10k 5%-daily challenge, install a *testable* account halt buffer below $500; a proposed $350-$400 soft threshold is **not an approved universal production setting**. Derive buffer from firm rules, latency and worst observed/plausible overshoot; simultaneous risks must never rely solely on weak normal-period correlation.
- [ ] Compute portfolio first-passage results on many **predeclared** start dates: target reached first, daily breach first, total/trailing breach first, expiry/open/censored, plus median days and net costs. Keep missing/censored starts in denominator or report bounds; never count simulated target as actual pass probability without uncertainty and forward validation.

### D. Three-pod composition / validation (D6-D8)
- [ ] Screen **marginal** value of each candidate to existing pods: correlation of synchronized marked follower returns, left-tail co-loss frequency, conditional beta to BTC/ETH/HYPE/ZEC, cluster of simultaneous positions and worst-case gross per coin.
- [ ] Label correlated archetypes and initially compare alternatives rather than adding both. Different wallet addresses or coin counts are not independent risk factors.
- [ ] Freeze selection universe and all look/parameter counts, apply holdout/rolling-start or forward splits, report selection and survivorship bias; preserve losing and dead candidates.
- [ ] Present one-winner, two-pod and three-pod ablations against a suitable no-copy/equal-risk baseline, with costs and full equity path; require higher pass rate or superior risk utility after uncertainty before adding a third pod.
- [ ] Require distinct source/follower/PIT evidence and scientific qualification per [QUALIFICATION](QUALIFICATION.md), then separately check account-specific permission and execution. **Default NO TRADE**. No inferred API permission from a public universe page.

## Ranked metrics and promotion decisions

**Primary:** portfolio *first-passage* target-before-breach likelihood with confidence intervals and censored outcomes; credible net follower R per $200 risk budget, and worst-case account survival. **Secondary:** time-to-target, stop-out/capital-efficiency, execution decay, marginal tail diversification, style stability and book fidelity. **Diagnostics only:** raw dollar PnL, ROI, closed-fill win rate, leaderboard rank, 1-day positive result, or correlation estimated only in quiet regimes.

Use states: `DISCOVERED` -> `SOURCE_AUDITED` -> `FOLLOWER_REPLAYED_EXPLORATORY` -> `OOS_TESTED` -> `PROSPECTIVE_SCIENTIFICALLY_QUALIFIED` -> `ACCOUNT_AUTHORIZED`; any stage may be `BLOCKED_DATA`, `REJECTED_ECONOMICS`, `REJECTED_RISK`, or `REJECTED_REPLICATION`. These are **descriptive checklist labels**, not newly introduced code/PM-02 state enums. Keep repo canonical status names in machine output.

## 2026-11-02 Nansen/Flovia discovery — candidates only, not imported cohort

Nansen-sourced monthly **realized** wallet-wide PnL, rounded USD. Flovia endpoints `/api/v1/perp-leaderboard`, `/api/v1/profiler/perp-pnl-summary`, `/api/v1/perp/account`, `/api/v1/profiler/perp-trades`. Lookups date-range 2026-08-01 through 2026-10-31 (leaderboard sometimes to Nov 1); account snapshots 2026-11-02 UTC. Data provided by Nansen. These are point observations, NOT an audited full-equity replay or true matched follower PnL.

| Address | Aug realized | Sep realized | Oct realized | Current gross / account equity | Discovery interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| `0xd6e56265890b76413d1d527eb9b75e334c0c5b42` | +$386,960 | +$478,178 | +$329,378 | 1.39x | HYPE long and broad alt shorts; 37 open positions, difficult whole-book fidelity |
| `0x230963164d9637a4c536270a06b4e3636d44a2d9` | +$1,598 | +$405,380 | +$629,957 | 3.43x | ZEC/NEAR concentrated longs, two current positions |
| `0x597568694fe6ee1b701ec8578bd57102c9a29abd` | +$165,550 | +$633,613 | +$169,237 | 5.17x | LIT/HYPE/ZEC/NEAR longs; overlaps prior wallet; aggressive |
| `0xac26cf5f3c46b5e102048c65b977d2551b72a9c7` | +$67,660 | +$57,874 | +$92,826 | 2.12x | HYPE/BTC long with broad shorts; similar factor to first wallet |
| `0x1bbfb3a33600338d5a948618189649a4588d5fc4` | $0 reported | +$3,048,551 | +$1,651,684 | ~1.98x | BTC/SOL, 100% closed-fill win report needs full-book audit |

**Proposed initial experiment** (not selection approval): compare `0xd6e562...` + `0x230963...` + `0x1bbfb3...`; ablate the third and compare correlated alternatives. Never assert they are qualified or that $600 cannot coincide. Source-current data changes; requery and timestamp any live candidate profile.

**Provider caution:** Nansen leaderboard `total_trades` and profiler `closed_trade_count` can count partial fills; 100% per-fill win rate does not establish episode-level wins. Snapshot gross/eq may disagree across endpoints/time. Individual asset tables omit non-top assets; check the entire account and positions. Keep raw provider payloads + request windows/IDs in approved private storage if permitted; this public note deliberately contains no API keys or private alias map.

**Existing project evidence:** See time-scoped wallet lists and exclusion registries in the operator's dirty primary checkout (not automatically committed here). Reconcile with existing source registries before any new acquisition; a newly discovered 0x address must not silently alter frozen PM-01 membership.

## Reusable evaluation record (one per candidate and one per combination)

Record: `candidate_id/address`; `research_asof_utc`; `cohort_version`; `discovery_window`; `source_manifest_sha`; `market_sha`; `leader_equity_clock`; `positions_coverage`; `episode_count`; `median_hold`; `realized/unrealized/fees/funding`; `gross/net/coin_exposure`; `virtual_capital`; `k`; `stop_policy`; `execution_clock/latency`; `cost_model`; `account_rulebook_version`; `pod_max_MAE_R`; `stopout_rate`; `net_R`; `worst_day`; `tail_coloss`; `fidelity_error`; `start_dates/blocked/censored`; `first_passage_target/breach`; `OOS_selection_history`; `status/evidence_SHA/reasons`. Missing fields must be explicit `UNKNOWN` or `BLOCKED`, never numeric zero.

**Bottom line:** A *good source wallet* is profitable; a *good prop pod* contributes reliable net follower R without consuming its $200 budget too often; a *good three-pod portfolio* maximizes account-level target-first survival under joint stressed loss and real execution constraints. These remain separate claims.
