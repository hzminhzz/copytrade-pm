# Evidence and qualification gates

**Read this before interpreting wallet rankings, a “pass,” an equity curve, or risk R.** Dated as of 2026-10-31 (repo `main` SHA `c3e9ccf`). The live source, actual GitHub issues and external Propr rules may evolve. Current research work is **not a trading system**.

## Separate the four statuses

| Label | Meaning | Minimum evidence |
| --- | --- | --- |
| IMPLEMENTED | Source/CLI contract exists | Code review and reproducible interface |
| ENGINEERING VERIFIED | Tests, lint, build and deterministic/adversarial replay pass | Exact commit, commands, test results, artifacts |
| SCIENTIFICALLY QUALIFIED | Real, independent prospective matched follower skill after realistic costs survives predeclared OOS/multiplicity, uncertainty, horizon and dependence tests | Causal first-known/economic data with immutable independent lineage; **not** historical HyperX replay |
| AUTHORIZED | Account-specific Propr/broker instrument, rules, copying/API permission, fee/leverage and operational gates explicitly approved | Signed/authoritative rules and separate risk authorization; **not** inferred from a simulator |

A fifth state, **DEPLOYED**, requires actual service/release and health verification. Neither repo tests nor PR merge imply it. NO TRADE is the default when evidence is missing.

## Evidence ladder and what each level permits

| Level | Required proof | Allowed claim | Forbidden promotion |
| --- | --- | --- | --- |
| D0 — candidate wallet | Verifiable alias and independent hashed identity | Candidate for source acquisition | “Profitable PM” without source economics |
| D1 — vendor roster/pages | Complete *vendor-listed* pages to frozen date, TID uniqueness/overlap and SHA lineage | Historical vendor-filled instruments exist | Complete exchange account NAV, funding, all positions |
| D2 — source book and market | Same-millisecond source position-before/after continuity, whole listed-leg anchoring, native exact 1m day SHA/coverage | Historical scenario can be replayed or explicitly blocked | Missing hedge = zero, Binance proxy = Hyperliquid native, 90% days = tradability |
| D3 — hypothetical follower | 5/15/60m delay, matched same-market control, stress on taker/spread/slippage/volume/funding, whole-book equity | Labeled **historical hindsight proxy** if all executable guards pass | Real PnL, predictive alpha, challenge probability |
| D4 — genuine prospective receipt | Immutable local first-known producer receipt, independent time/continuity audit, no post-hoc clock substitution | Event was independently witnessed in time | Receipt = executable trade/whole account |
| D5 — matched outcome | Independently signed, source+market+follower evidence with decision before 5/15/60m maturity and realistic execution/cost/control PnL in R | Matched follower episode available **as of** evidence time | One successful episode = qualified manager |
| D6 — wallet manager inference | Frozen predeclared sample/holdout, confidence interval, selection budget, independence/shrinkage, drift and tail robustness | PM-02 research candidate state, possibly allocation **proposal** | PM-02 R = actual position/order |
| D7 — consolidated challenge engineering | PM-03 fully reconciled shadow accounting, partial fills, HALT, costs and 3-policy stress on identical PIT paths | **Synthetic** account behavior | Real Propr challenge probability or live permission |
| D8 — real account and contract gate | Actual Propr market IDs, fees, executable venue/account terms, copying/API policy, leverage/margin, live-forward evidence, explicit authorization | Only then may a separate authorized execution project be considered | Any implicit permission from public web rules |

## Why “90% covered” is not “90% ready”

The [dated PM-01 Propr coverage study](PM-01-propr-90pct-scope.md) targeted **90% of strict native-market instrument-days** relevant to *individual* candidate wallets. It did **not** establish: 90% minute-level executable actions, 90% entire account books, 90% market pairs accepted on a purchased Propr account, or 90% probability of passing. Its four shortlisted wallets were **data acquisition milestones**. Filtering away a live non-Propr hedge changes the source strategy and cannot be represented as whole-wallet replication.

## Frozen PM-01 → PM-02 business logic

- The historical fill replay v2 has **36 wallets × 3 latency rows**. `pnl=None` is a blocked/unknown economic result. A vendor-reported source `closed_pnl` is not the PnL of a separately sized follower; aggregation across source accounts is not consolidated challenge equity.
- For true prospective episodes, `pm_manager` requires source-event, first-known, outcome-known ordering, `verified_first_known`, `matched_control`, source/market SHA provenance and finite follower/control net R. It applies fixed **60 episodes**, **40 effective independent samples**, **30 calendar days**, staleness no more than 24 hours and conservative positive incremental lower bound. These are *research model-policy thresholds*, not statistically proven optimal numbers.
- `pm02_risk` checks synchronized exposure and tail dependence; no asynchronous missing-return zeros. Candidate seats max five; EMPTY is allowed; PM-03 owns simulated account-level risk. A wallet may rank high historically yet be ineligible for any R.
- The signed ledger enforces SHA chain, Ed25519 independent attestation, conservative local first-known and matured outcome. **A valid cryptographic signature proves a key signed a declaration, not that the market data or actual follower trades were measured honestly.** Independent audit material must be retained off Git.

## PM-03 risk: account equity vs wallet source PnL

- PM-03 `cash`, realized balance, unrealized PnL, equity, floor and fee/funding models are **synthetic ledger quantities** unless independently grounded in actual account records. The risk supervisor is GREEN/YELLOW/ORANGE/RED/HALT and persists HALT; it does not connect an order gateway.
- Public Propr snapshot `v1.0.5` from 2026-07-27 (observed 2026-10-31) is **unconfirmed per account**. `propr_rulebook(...)` sets `confirmed=False`, no market allowlist, no default leverage. The presence of public `www.propr.xyz/universe` display tickers cannot authorize a trade. Contractual copying/aggregation, funded terms, fees and venue fills require independent validation.
- `pm03_stress` compares equal-risk, historical top-PnL (**hindsight biased**) and centralized supervision on the *same synthetic PIT steps*. Simulated target touches and drawdowns are not a calibrated pass-probability distribution; missing source episodes must not be dropped as non-losses.

## Current evidence register — time-scoped, not a permanent result

| Workstream | Verified scope at this snapshot | Remaining UNKNOWN/blocked |
| --- | --- | --- |
| PM-01 | 36 cohort and frozen vendor source parity; offline 5/15/60m replay and read-only audit; historical Propr native-day 90% shortlist | Full source account equity/funding/collateral and unresolved position chains, minute execution/capacity, independent prospective followed fills |
| PM-02 | Existing actual 36-wallet sealed report SHA `7bf28ee5ad53cdac9212bb0222ae1b3e0ef020eee5faae9972c53028e4b60f4f`: 0 qualified, five EMPTY, 0 actionable R; independent signed *adapter* merged | Real signed/verified economic outcomes and causal independent OOS selection/portfolio utility |
| PM-03 | Engineering and tests merged via [PR #6](https://github.com/hzminhzz/copytrade-pm/pull/6) (Issue #2 closed) | Account-specific Propr authorized execution, calibrated follower PnL and challenge-pass likelihood |
| Wave C | Versioned 2-wallet vendor generation, page/manifest SHA lineage and an independent integrity verdict `ACCEPTED_FOR_IN_WINDOW_REPLAY` for 2026-04-11 onward; frozen 36 untouched | Any prospective first-known clock, follower PnL, pre-2026-04-11 replay (native 1m lake gap 2026-03-01…04-07) and scientific qualification |
| PM-36 | [Draft PR #7](https://github.com/hzminhzz/copytrade-pm/pull/7) separate 2026Q3 research (not on main), with limited partial episode diagnostics | Whole-book simultaneous account equity, true matched prospective OOS, integration into current `main` |

Current scientific trackers: [PM-01 #4](https://github.com/hzminhzz/copytrade-pm/issues/4) and [PM-02 #5](https://github.com/hzminhzz/copytrade-pm/issues/5). No live order/deployment authority.

## Decision protocol for new research

1. **Define a narrow falsifiable thesis** and the causal event/decision/fill clock, target universe, horizon and held-out period before seeing outcome returns.
2. **Verify source and native market** lineage. Keep missing/source discontinuity and outside-Propr hedge risks explicit. Stop if the required complete book cannot be reconstructed.
3. **Model follower economics**, not source wallet closed PnL: latency, volume/depth/fee/funding sensitivity, same-path matched control, central netting/correlated tails and consolidated account constraints.
4. **Enforce PIT separation and multiplicity.** Historical TID timestamps are hindsight; prohibit using holdout/OOS to tune candidate/risk parameters; freeze the selection family and attempted experiments.
5. **Report rejects and uncertainty.** Negative, blocked, unknown and censored episodes remain visible; no survivorship or missing-return zero fill.
6. **Never authorize live trading** from the PM-01/02/03 package. Any new execution boundary requires a separate specification, dated written Propr approval and explicit owner authorization.

For actual commands: [RUNBOOK](RUNBOOK.md). For precise clock/audit signatures: [PM-01 prospective ledger](PM-01-prospective-ledger.md).
