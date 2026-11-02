# Wallet Research Handbook — discover, verify, rank, and select copytrade pods

**Version:** proposed research protocol v1 · **Date:** 2026-11-02 · **Independent judge:** `JUDGE_UNAVAILABLE` in the inspected workspace; direct source/code review and test results recorded. **Authority:** research guidance only. **Default result:** `NO TRADE` until separate scientific qualification and account authorization. This is the **canonical entrypoint for future wallet-selection research**, not a new executable engine or replacement for PM-02/PM-03/PM-04 contracts.

**Mandatory companion documents:** [INDEX](INDEX.md), [ARCHITECTURE](ARCHITECTURE.md), [wallet screening checklist](WALLET-POD-SELECTION.md), [Nansen directional discovery audit](NANSEN-DIRECTIONAL-POD-SHORTLIST-20261102.md), [Gemini report audit](GEMINI-REPORT-METHODOLOGY-AUDIT-20261102.md), [equity-weight sizing](EQUITY-WEIGHT-SIZING.md), [qualification and evidence ladder](QUALIFICATION.md), [data acquisition](DATA-ACQUISITION.md), [PM-02 evidence gates](PM-02-EVIDENCE-GATES.md), [PM-04 risk/batching](PM-04-shadow-hardening.md), [operator runbook](RUNBOOK.md), [RECOVER](BLOCKER-RECOVERY.md).

## 0. Objective, boundaries, and definition of a good wallet

**A profitable source wallet is not necessarily a profitable follower pod.** The primary objective is **incremental, after-cost, five-minute-delayed follower performance in units of an independently budgeted pod loss limit**, followed by **marginal three-pod challenge survival and target-before-breach performance**. The winning portfolio need not contain the three highest standalone-ranked source wallets.

Separate four questions, each with distinct evidence and labels:

1. **Source skill:** Are wallet decisions repeatable and economically distinct from market beta, known momentum, funding, maker rebates, and a lucky historical path?
2. **Follower copyability:** Does the same *whole-position strategy*, scaled by observed source equity, generate credible net follower returns after the actual 300-second batching and market execution?
3. **Portfolio contribution:** Does adding the wallet increase account-level target-first outcomes without concentration, cloned risk, simultaneous loss or unacceptable tail exposure?
4. **Current opportunity:** Given the wallet and the market **now**, is this particular eligible source-position change worth following? A skilled wallet can generate weak trades; a good-looking trade does not make a wallet skilled.

The owner chooses **directional, medium-frequency/swing pods**, not latency-dependent HFT, funding-carry/basis, market-neutral or systematic long BTC/ETH/HYPE/SOL versus a broad altcoin short basket. **Historical current-book contradictions must be audited; never screen style from a single latest position snapshot.** Primary instrument scope is the account's confirmed Propr set; a public ticker list is informational, not an execution permit. Prefer whole-book replication, but tolerate occasional *follower* skips with explicit tracking error. **Never omit required source hedges to make a book eligible.**

Keep the distinction among `REPORTED_SOURCE`, `AUDITED_SOURCE`, `HISTORICAL_ORACLE_FOLLOWER`, `PROSPECTIVE_MATCHED_FOLLOWER`, `SCIENTIFICALLY_QUALIFIED`, `ACCOUNT_AUTHORIZED`, `DEPLOYED`. Canonical machine/lifecycle states remain defined by [QUALIFICATION](QUALIFICATION.md) and code. Labels in this handbook are **descriptive research verdicts**, not new code enums.

### The real repository boundaries

- Discovery/Nansen queries and new cohorts are **upstream/private**; `pm_sources` and `pm_manager.source_rows()` intentionally expect the frozen 36-wallet PM-01 replay. **Never add fresh Nansen addresses to that manifest or feed them into the 36-wallet interface by coercion.** A new cohort/adapter needs a separately reviewed contract before integration.
- `pm_wallet_replica` / `pm_exposure_sizing` own whole-book source-equity proportional intents; PM-04/PM-03 own one shadow account's batching, netting, simulated attribution and risk HALT. The 2026-11-02 research docs do **not** authorize broker/Propr order mutations.
- PM-02 policy `MAX_MANAGER_R = 0.20` is **not** the owner's nominal 2%-of-challenge pod loss budget, and Telegram A/B/C grades are **not** PM-02 allocations. Distinguish these units in every report.
- The external production Telegram/consensus candidate system is **not implemented in this repository**. Its **3+ distinct addresses with >=2:1 directional agreement** is an experimental incumbent baseline *only if the actual upstream version and candidate cuts are frozen and verified*, not a rule to assert exists in `pm_manager`.

### Compact decision rubric (apply in this order, not as an arbitrary weighted sum)

| Dimension | Favor | Reject or investigate |
| --- | --- | --- |
| **Strategy authenticity** | Independent directional swing / medium-frequency manager; source sizing is interpretable | Funding/basis carry, broad long-major/short-alt hedge, clone, invisible cross-venue leg, martingale |
| **Economic opportunities** | Multiple independent position decisions across market regimes; source edge survives market/flow controls | One huge winner, all profits from funding/rebates, 100% closed-fill win rate with unknown underwater positions |
| **Copyability** | Native Propr-eligible liquid instruments, realistic market-order costs, source inventory/equity sufficiently observable | Maker/HFT dependence, >5m-sensitive edge, missing source hedge/book, unauditable marks |
| **Risk efficiency** | Attractive **net follower R per fixed pod loss budget**, tolerable MAE/stop frequency and stress tails | Source ROI alone, outsized stop overshoot or correlated account breaches |
| **Marginal diversification** | Different conditional return driver and downside-loss timing from incumbent pods | A second address for the same manager; hidden common BTC/HYPE/ZEC crash exposure |

**Operating preference:** reconstruct holding episodes (prefer median ~10 hours or longer for this medium-frequency project, *not* a universal scientific threshold), and use approximate 90% market-day coverage for *exploratory triage* when clearly labeled. Neither substitutes for whole-book execution coverage at the actual traded moments. **Do not invent numeric scoring weights or grade thresholds from the three papers.**

### Proportional-effort operating modes (avoid analysis paralysis)

- **SCREEN (hours/cheap inputs):** G0–G2 on broad Nansen inventory, complete current books and bounded funding observations; return a defensible **ten-wallet research shortlist**, not a claim of qualification. No retrospective minute-by-minute equity reconstruction is required merely to decide whom to investigate.
- **REPLAY (selected finalists):** G3–G8 on audited source fills, market data and allowable historical *as-of* equity. If historical equity is sparse, run **clearly labeled** hypothetical/proxy scenarios with coverage accounting and source-exposure sensitivity; do **not** claim faithful historical follower sizing or drop unknown risk silently. Collect missing authorized data and continue other wallets.
- **CONFIRM (prospective only):** G9 with independently observed first-known receipts, matched follower/control economics, frozen models and separate account authorization. An impressive in-sample replay is not a substitute.

Do not expand a weak sample into elaborate deep models merely to meet a numeric shortlist target. A useful **negative result** and a smaller honest roster beat ten fabricated qualified pods.

## 1. The scientific basis and the allowed transfer

| Source | Supported insight | Adaptation to Hyperliquid / constraints |
| --- | --- | --- |
| Jia & Sun (2026), [Beyond Profit Rankings](https://arxiv.org/abs/2610.34754) | Reconstruct wallet strategies and heterogeneity; distinguish historical source profitability from copy execution; examine persistence and economic feasibility on **Polymarket**. | Use full-book, episode and follower-cost forensics. **Do not copy Polymarket win-rate, 90/180-day, profit-factor or fixed decision thresholds** as Hyperliquid facts. |
| Zhai (2026), [Public Trader Identity](https://arxiv.org/abs/2608.04373) | On **Hyperliquid**, wallet identity supplies incremental predictive information relative to anonymous price/book/flow controls when scored on past trading and tested on later data. The main result is **one-second**, high-frequency, full-depth-book forecasting. | Test **conditional identity/specialization value** at our 5-minute observed-execution and later source-exit horizons using 1m-native market evidence. Do **not** claim the paper's one-second R², sample sizes or 10-day score windows imply our economic follower edge. |
| Li & Ma (2025), [Learn to Rank Risky Investors](https://arxiv.org/abs/2509.16616) | A profit-aware learning-to-rank loss can align ranking with economic consequences, versus purely binary trader flags, in **CFD market-maker risk classification**. | Redefine ranking label as **matured follower net R / account survival**, not market-maker risk, the paper's risk label or next-100-trade PnL. Compare interpretable/shrunk and logistic/tree baselines **before** complex ranking/deep models. |

These are research inspirations, **not** pre-validated models or performance guarantees for this project. Record the URL, accessed version/date, precise adapted claim and falsification test in the experiment manifest.

## 2. Mandatory ordered workflow for future agents

Advance through these steps without treating discovery as qualification. On an ordinary technical/data blocker, follow [RECOVER](BLOCKER-RECOVERY.md), continue other eligible candidates, and preserve a blocker register. Missing true historical first-known observations cannot be repaired by pretending hindsight data were known earlier.

### Gate G0 — Freeze the question and the research clock

Before inspecting candidate performance on a supposed test set, record:
- `research_asof_utc`, owner goal, challenge type/start balance, **official account-specific** loss floors, profit target, expiration and allowed instruments; mark missing official evidence `UNKNOWN`.
- PIT **wallet-universe selection timestamp and cohort generation**, candidate-source history, wallet aliases/identity SHA, active/dormant/rejected sampling policy, training/validation/holdout dates, selection and model-family trial budgets. If all 90 days were selected by hindsight, designate them **exploratory in-sample**, not OOS.
- Hypothesis and its falsification (e.g. “after matched market-return control and five-minute taker execution, wallet identity improves net follower R on unseen events”), unit of analysis (parent episode vs fill vs decision), primary exit policy, cost model, latency sensitivity and confidence/acceptance rule.
- Any future holdout must be **future to the frozen roster and model**; do not reselect a roster using outcomes within that holdout.

**Deliver:** private, SHA-versioned `experiment_manifest.json` and `cohort_manifest.json` with explicit unknowns. No retrospective promotions.

### Gate G1 — Broad discovery, with audit trail of all rejects

- Use connected **Flovia/Nansen** leaderboards, wallet-wide PnL summaries, recent trades, active equity and full current account books for **discovery only**. Search multiple leaderboard pages, coins, trading styles and regimes. Record all addresses attempted, source query windows and provider lookup IDs. A top-single-token winner can have a **negative whole-wallet** PnL.
- Reuse the existing 94-wallet owner-private HyperX inventory when it actually contains the address; **verify address overlap**, do not infer it. New wallets enter a **separate versioned cohort**; do not alter the frozen 36-wallet PM-01 manifest.
- Cross-check with authorized **HyperX historical fills** (preferred fill provider, no substitution of official HL account-fill API) and read-only official Hyperliquid `userFunding` / position snapshots as supporting evidence. Handle provider quota, complete paging, TID/OID dedup, versioned raw source hashes.
- Audit current equity/activity, entire traded-coin breadth, deposits/withdrawals, source cost basis and suspicious ~100% **closed-fill** win rates. Keep unprofitable/dormant and source-unavailable wallets in the screened denominator.

**Deliver:** full attempted-candidate ledger with disposition `PROCEED`, `STYLE_REJECT`, `NOT_COPYABLE`, `BLOCKED_DATA` or `INSUFFICIENT_SAMPLE` (these are document labels, not canonical machine enums). Continue until enough candidates for meaningful portfolio comparison; **ten screened names are not ten qualified wallets**.

### Gate G2 — Verify the actual strategy; reject non-directional economics

For each address and all known master/subaccounts and DEX scopes:

- **Reconstruct gross signed exposure by instrument and time, not only current book**. Test concurrent long BTC/HYPE/ETH/SOL against short alts, broad paired books, cross-venue basis, net-beta neutrality, spot/perp offsets, same-time position co-adjustments and repeated scaling ratios between accounts. A contemporaneous long+short snapshot is stronger than “both sides sometime today”; same-day reversals are not hedged baskets.
- Independently aggregate **signed funding USDC credits/debits** over a bounded window and compare with realized/unrealized/fees/withdrawals. Positive funding by itself is **not** proof of carry; negative net funding rules out *net HL funding earned over the observed period* but **not** off-venue carry or unknown hedge income.
- Distinguish strategy types: directional swing; episodic breakout; slow trend; low-frequency concentrated; high-churn partial fills; maker liquidity provision; rebate farming; funding/basis/relative-value; martingale/losing-side averaging. Identify **clone clusters** from whole-book trajectories and timed returns, not shared labels or normal-period correlation alone.
- **Hard veto** deliberate ongoing carry/basis or market-neutral book, persistent long-major/short-alt basket, missing economically required hedge, prohibited instrument, sustained HFT/maker edge that vanishes with a 5m taker follower, verified clone (only one seat per economic risk source), and uncontrolled tail exposure. **Conditional** one-off hedges, 100% closed-fill wins, single-month profits, high notional leverage or incomplete historical clocks: audit rather than invent certainty.

**Deliver:** wallet `strategy_profile` + timestamps/evidence and `STYLE_PASS/REJECT/UNKNOWN`. An unsupported “not carry” claim is `UNKNOWN`, not `PASS`.

### Gate G3 — Reconstruct independent economic episodes and causal features

- Retrieve/preserve original raw HyperX pages; check page/timestamp coverage, unique fills, `start_position` continuity, order IDs, partial fills, initial inventory, source equity/collateral, funding, position reconciliation, missing market minutes, asset mapping and subaccount completeness. One order broken into 100 fills is **not** 100 independent outcomes.
- Group changes into **parent decisions** and flat-to-flat position episodes; preserve multi-asset strategy book as one economic decision where legs depend on each other. Record holding duration, adds/reductions, realized + mark-to-market adverse/favorable excursion, turnover, time underwater, tail/gap and **effective independent** sample counts.
- Construct timestamped features only from prior-known source/market states: past episode hit/loss/tail statistics, shrinkage uncertainty, concentration, specialization, market momentum/volatility/regime, recent signal consensus, spread/liquidity proxy, source book/current equity freshness and overlapping pod inventory.
- Record four distinct clocks: `source_event_at`, `first_local_receipt_at`, `decision_at`, `hypothetical_fill_at`. A historical vendor timestamp **does not** become a witnessed receipt. Current source equity reused backward is **lookahead**. 90% native market-day coverage does not mean 90% whole-book executable events.

**Deliver:** `episode_tape`, source position-vector lineage, PIT `feature_tape`, source/data SHA and explicit coverage flags; unknown initial holdings and incomplete economic legs remain censored/blocked.

### Gate G4 — Establish genuine wallet skill beyond anonymous market exposure

Test the **same events, same dates, same instruments and same accounting**:
1. Market/anonymous-only benchmark: source instrument returns, local volatility and trend, genuinely observed recent volume (and flow **only if separately available**), common trading hours, **without wallet identity**. Do not fabricate LOB imbalance or signed order flow from 1m OHLCV.
2. Simple source-PnL/ROI ranking (diagnostic, likely selection biased).
3. Shrinkage skill model per wallet and per specialization/market regime with uncertainty adjusted for **independent episodes and shared factors**.
4. Anonymous controls **plus** frozen wallet identity, specialization, and historical quality features; inspect incremental OOS outcome and matched-wallet/placebo cohorts.

Test rank persistence across nonoverlapping chronological periods (e.g. Spearman rank rank-stability with uncertainty), peer- and opportunity-adjusted outcomes, token/side/regime attribution, performance after removing the largest win or most favorable dates, and matched placebo identities. Do not interpret generic BTC beta or a source-specific funding subsidy as transferable identity skill.

**Deliver:** `wallet_skill_model` summary with raw source skill, adjusted follower skill if mature evidence exists, risk/tail uncertainty, matched baselines, rank stability and **identity incremental value**. If identity has no economically significant incremental value, record **NEGATIVE_RESEARCH_RESULT**.

### Gate G5 — Copy economics, not the leader's reported return

**Authoritative sizing:** follow [EQUITY-WEIGHT-SIZING](EQUITY-WEIGHT-SIZING.md):

```
source_signed_notional_i(t) = source_quantity_i(t) * source_native_mark_i(t)
source_weight_i(t)          = source_signed_notional_i(t) / source_equity_asof(t)
follower_target_notional_i(t) = pod_virtual_capital(t) * source_weight_i(t) * predeclared_risk_scale
follower_catchup_i(t)       = target_quantity_i(t) - actual_follower_quantity_i(t)
```

**$200 is a nominal pod loss budget for a $10,000 account; it is NOT $200 deployment capital or source leverage.** At $100,000, 2% = $2,000. Three independent nominal 2% budgets = 6%, **already above an illustrative 5% daily floor**. The shared account supervisor always overrides pod targets; account floor, reserve/buffer and stop overshoot must be modeled with the actual challenge rules.

- Observe first source change at **first local receipt**, allow **300 seconds non-resetting batching**, then reconcile **one market rebalance toward latest verified whole-book targets**. Protective risk reductions/halts can be earlier under the predeclared policy; skipped follower trades require latest-target catch-up, not blind reapplication of original fill size.
- Use exact native Hyperliquid 1m prices for marked/next-executable-bar fill scenarios, account-approved symbol/DEX identity, realistic taker fees, spread/slippage, market impact/capacity, funding and market data staleness. Record **0/5/15-minute** latency and **1x/2x/3x** costs plus capacity/coin shock scenarios as sensitivities; **5m** is primary. A 1m OHLCV replay cannot certify tick-level fillability and must be labeled hypothetical.
- **Primary exit policy** mirrors the source's observed reductions/exits after follower batching and risk clipping. A fixed 5/15/60-minute post-entry exit study is a **separately labeled diagnostic**, not interchangeable with source-exit follower economics. Explicitly specify counterfactual behavior when source events or exits are missing.
- For each parent opportunity report `follower_net_R = after_cost_attributed_follower_PnL / nominal_pod_loss_budget`, forced-stop loss/overshoot, unrealized MAE, liquidity rejection, tracking error, realized contribution, and same-path matched control. If no real first-known clock/source NAV, label the result `HISTORICAL_ORACLE_FOLLOWER`, **not** prospective matched alpha.

**Deliver:** matched source/follower/control opportunity ledger with all accepted, rejected, skipped, stale, blocked and censored cases. **No actual broker order** is authorized here.

### Gate G6 — Separate the ranker from trade/opportunity evaluation

Two independent components, two evaluations:

**A. Trader skill ranker (slow update):** rank `wallet_id` in a frozen eligible roster using **matured** follower net R per independent episode, drawdown/tail robustness, source-copy tracking error, rank persistence, specialization and uncertainty. Start with hierarchical/empirical-Bayes shrinkage or interpretable robust scoring; compare with source-PnL, equal-wallet and market-adjusted baselines. No blanket fixed win-rate or profit-factor threshold imported from other venues.

**B. Opportunity evaluator / meta-label (on each source change):** estimate the incremental follower economic value **conditional on** source direction/size, the wallet's frozen skill, current market regime and eligible instruments, cost/latency, correlated pod exposure and the account supervisor. Label on **post-decision, after-cost follower outcomes under a fixed exit and size policy**, not raw source `closedPnl` or a future "oracle optimal exit". Use calibrated logistic/regularized regression or boosted trees first. Optional cross-trader LTR, LambdaMART, PA-style economic pairwise losses or transformers only if independent sample size, honest OOS gain, stability and engineering cost justify them.

**Do not leak model outputs:** in chronological evaluation, each wallet skill feature and calibration must be computed **only from outcomes matured before the opportunity's first-known timestamp**; no future label or cross-wallet test outcome feeds a historical signal.

**Grades are separate presentation:** Telegram `C/B/A` must be downstream of calibrated evidence and PM03/PM04 risk permissions, not an intrinsic wallet score or a claim of "0.5R"/"1R" broker exposure. Risk units for communication and PM-02 `R` are not automatically equivalent. If no high-quality opportunity evidence: `WATCH/NO TRADE`.

### Gate G7 — Five required matched baselines (plus ablations)

Use **identical candidate events and timestamps, source roster eligibility, market bars, exit rules, five-minute decision clock, market-order costs, sizing/risk supervisor and censoring** for all methods. Do not improve the new model by silently deleting cases that hurt it.

| ID | Selector | Purpose |
| --- | --- | --- |
| `B0` | External incumbent `>=3 distinct addresses, directional agreement >=2:1`, **only if reproduced from verified upstream version** | Operational baseline; if not verifiable, report `UNAVAILABLE`, not an invented copytrade-pm rule |
| `B1` | Equal-weight, clone/dependence-aware distinct-wallet consensus | Simple diversification / denominator-aware control |
| `B2` | Source historic realized-PnL leaderboard | Test if sophistication beats the seductive simple ranking |
| `B3` | Trader-only shrunk/adjusted skill ranker | Is wallet selection enough without opportunity timing? |
| `B4` | Trader + opportunity + risk-aware evaluator | Does market context and meta-labeling **incrementally** improve follower outcomes? |

Ablations: market-only/no-identity, identity-only/no-context, no-specialization, no clone/dependence adjustment, no risk overlay (for **research comparison only**), 1/2/3-wallet portfolios, and optional 5-wallet **risk-equalized** portfolios. The no-risk-overlay case **must never** be deployed. Record all attempted model families and wallet/threshold/exit combinations as the multiple-testing family.

Evaluate **net follower R**, stop-out rate, daily and peak-to-trough account equity loss, CVaR/tail, concentration by symbol and regime, first-passage target-before-breach rate with censored dates, time-to-target, turnover/costs, rank stability, calibration (Brier/log loss/reliability), NDCG@K if ranking is used, incremental wallet identity lift, and rejected/missing counts. Statistical rank metrics are supplementary; **account/follower economics are primary**.

### Gate G8 — Three-pod challenge composition

- Begin with **3** distinct economic risk sources, not just 3 addresses. For the owner's $10k hypothesis, nominal loss budget `$200/pod`; for $100k, `$2,000/pod`. These are *provisional research settings*, not an assurance that orders stop exactly at -2% each.
- Compare combinations on **synchronized minute-by-minute** follower equity, same starting dates and cost model. Construct independent pod attribution **before** shared account netting; then consolidate actual gross/net exposures, correlated signs, coin caps, shared market beta and stop/fill races. Avoid hidden triple HYPE/ZEC/BTC concentration and clone seats.
- Compute target-first / rule-breach-first / still-open outcomes, including maximum adverse excursion, daily floor based on **correct account-specific reference**, total/static/trailing floor, risk supervisor early halt, stop overshoot, missed source/follower events, funding, slippage and stress. Do not assume 3 x $200 max loss safely fits a $500 daily limit. Use verified source exposure envelopes and plausible joint shock, not independence by assertion.
- Optimize **marginal** portfolio utility after uncertainty, not highest individual `R` or high historical Sharpe; test a two-pod ablation and hold-one-out loss correlation. For 3 vs 5 compare **equal total risk** in addition to 2%-per-wallet exposure. The best outcome may be **fewer than three** eligible wallets or `NO TRADE`.

**Deliver:** versioned `portfolio_combination_scorecard` including the same event roster for every method, 3-vs-5 ablation, rule version, uncertainty bounds, all simultaneous-loss paths, and a list of exact accepted/rejected/missing starts. An in-sample 100%-pass rate across overlapping starts is **not** calibrated pass probability.

### Gate G9 — Independent OOS, forward receipts and a real falsification rule

- Freeze wallet roster, selection epoch, feature definitions, model families, parameter budget, costs/exits and rulebook **before** a holdout is examined. The retrospectively chosen August–October 2026 roster is **in-sample** for all methods and **cannot become OOS** because it is renamed or split after discovery.
- Prefer **PIT historical rosters** that genuinely existed before the evaluated window or prospective `first_local_receipt_at` + independent matched follower/control outcomes. Use **chronological** walk-forward validation; purge overlapping label horizons/whole position episodes and embargo where features share rolling windows. Block bootstrap by calendar/time-regime and cluster wallet/coin-dependent returns; never treat partial fills or overlapping starts as independent observations.
- Correct for multiple comparisons when scanning many wallets, model families, thresholds, horizons, starts and portfolios; declare the family and trial budget. Report effect size, paired uncertainty, false discoveries, data availability and **why** each failed model failed. Deep model improvement must exceed both simple and economically aligned controls on a truly untouched evaluation.
- Test drift: rank stability, changes in wallet size/notional, trade frequency, specialization, copy friction, venue availability, suspicious newly mixed hedges, source equity staleness and correlation in simultaneous drawdowns.
- **Decision outcomes:** `BETTER_THAN_BASELINE` (only when supported by prespecified independent results), `NOT_BETTER` (**negative research result is acceptable**), `BLOCKED_DATA`, `BLOCKED_PIT`, `REJECTED_RISK/STYLE/REPLICATION` and `UNKNOWN` (research disposition labels only). No fabricated `A` grade, "pass probability", or forced ten qualified wallets.
- Promotion still follows [QUALIFICATION](QUALIFICATION.md): research-only historical simulations may inform choices, but prospective scientific qualification and any real account authorization are **separate**. This repository has no permitted order gateway.

## 3. Reproducibility deliverables and evidence schema

Each campaign must make an audit-ready, **private** immutable directory under the owner-approved research root (for example `/home/quant/.local/share/copytrade/reports/<frozen_run_id>/`, **not Git**). Keep source pages, original full wallet-address maps, token secrets, market data and private account identities out of the repository.

| Artifact | Minimum contract |
| --- | --- |
| `experiment_manifest.json` | as-of, exact hypothesis, paper/source versions, candidate eligibility, firm rule version, horizons, cuts, models/trial budget, cost/exit/stop policies, SHA pointers |
| `candidate_ledger.csv` | one row per attempted canonical wallet: discovery origin/time, current state, **entire** style veto reason, data coverage, evidence SHA, final disposition; never winners only |
| `source_evidence_manifest.json` | per-wallet full-address binding/hashed alias, HyperX raw page digests, TID/OID completeness, subaccount scope, funding window/paging, realized/MTM reconciliation, native Propr-compatible symbol check |
| `episode_tape.parquet` | decision/episode IDs, all four clocks, source signed whole-position exposure, account equity as-of, volume/fees, missing flags, source and follower outcome-maturity times |
| `matched_follower_outcomes.parquet` | frozen event cuts, actual/oracle evidence tier, model eligibility, one policy, follower/control PnL in $ and R, latency/cost stress, reason for veto/skipped/censored |
| `wallet_skill_scorecard.csv` | raw vs shrunk vs adjusted outcomes, sample/effective N, rank stability, identity-vs-market matched increment, confidence intervals, source/follower distinction |
| `baseline_ablation.csv` | B0–B4 **same cut**, period, model version, costs, accepted/rejected/unknown denominators, paired uncertainties and negative results |
| `portfolio_scorecard.json` | 3-pod risk budget, source-scale, marked consolidated equity and netting, firm floor/version, daily/tail loss, target-first/breach-first/censored starts, correlation/coin risks |
| `decision_report.md` | `ADOPT/EXPERIMENT/IGNORE` per technique; `RESEARCH_ONLY/SCIENTIFICALLY_QUALIFIED/BLOCKED/REJECTED` per wallet; recommended next acquisition, reproducible commands, SHA, exact tests, caveats |

**Core per-candidate record:**

```text
wallet_address_sha | alias | cohort_version | selected_asof_utc
source_data_sha | market_data_sha | funding_window/coverage
master_subaccount_scope | leader_equity_asof_coverage
episode_count | effective_independent_n | median_episode_hold
long_short_style_and_confidence | carry_credit_debit_attribution
maker_share | follower_taker_cost | source_vs_follower_tracking_error
identity_increment_vs_market_control | monthly_rank_stability
follower_net_R | stopout/overshoot/MAE_R | pairwise_tail_coloss
account_target_before_breach | rejected/blocked/censored counts
evidence_level | decision | reason | holdout_used_flag
```

Never fill missing economic fields with numeric zero. Explicitly log `UNKNOWN`, `NOT_AVAILABLE`, `BLOCKED` or `NOT_APPLICABLE`. Preserve rejected candidates and trading opportunities for denominators and failure analysis.

## 4. Minimal operator checklist for the next agent

- [ ] Read `AGENTS.md`, activate OptMem, inspect current branch/dirty worktree, `docs/INDEX.md`, canonical code/tests, current GitHub issues/PRs and private evidence generations. **Preserve other sessions' work.**
- [ ] Choose a *new, frozen* wallet research cohort/time split and account-rule snapshot; verify no conflict with the 36-wallet PM-01 or PM-02 contracts.
- [ ] Use Nansen for discovery, HyperX for authoritative historical fill investigation and local first-known forward capture, HL `userFunding` as a signed-cashflow diagnostic; reconstruct and flag whole-book hedges/carry/maker-dependence.
- [ ] Keep a full attempted-wallet log; continue searching while fewer than ten **provisionally suitable** candidates exist, but never inflate a cohort by admitting rejected hedges or pretending screening equals qualification.
- [ ] Aggregate **economic episodes**, as-of features, full source book and equity; label missing start states, market gaps and prospective receipt gaps. Recover routine API/data blockers without inventing missing knowledge.
- [ ] Reuse existing `pm_wallet_replica`, `pm_exposure_sizing`, native verified 1m sources and PM-03/PM-04 **where actual input contracts are satisfied**. Make any new cohort adapter a separately tested/versioned engineering change; **do not** weaken the frozen 36-wallet source contract to get a result.
- [ ] Freeze and execute B0–B4, wallet-level/portfolio-level ablations, exact matched 5m source-exit follower policies and fee/latency stresses, with all negative/missing/blocked outcomes.
- [ ] Preserve OOS validity and conditional identity test. Do not run a deep transformer before lower-complexity baselines justify it.
- [ ] Document **source skill**, **follower copyability**, **portfolio marginal value**, **current opportunity quality** separately, each with exact evidence tier and uncertainty. No wallet is qualified from a headline source PnL or passing unit tests.
- [ ] Use the approved [runbook](RUNBOOK.md) for actual current commands. For documentation/code changes, run `uv run --frozen --extra market --group dev python -m pytest -q tests`, `uv run --frozen --group dev ruff check src tests`, `uv run --frozen --group dev ruff format --check src tests`, `git diff --check`, review actual diff and exact commit/CI; no trade/network order mutation.

**Final principle:** a good wallet has plausible repeatable economic decisions; a good *copyable pod* delivers net follower R with bounded losses under the actual latency/account constraints; a good *portfolio* adds target-before-breach survival after dependence, full costs and uncertainty; and a good *trade* adds conditional value **today** beyond anonymous market movement. Any step may return `NO TRADE`.
