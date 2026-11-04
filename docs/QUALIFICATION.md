# Evidence and qualification gates

## Polars offline milestone #2 two independent result dimensions (2026-11-04)

Read [two-track engineering acceptance](OFFLINE-MILESTONE2-ENGINEERING-ACCEPTANCE-20261104.md)
before interpreting draft [PR #92](https://github.com/hzminhzz/copytrade-pm/pull/92).
`ENGINEERING VERIFIED` requires a positive complete-evidence fixture and
adversarial negative evidence tests through one sealed public job, exact
PM-03 Decimal and compatible frozen code contracts. A correctly
`BLOCKED` real historical-oracle study is **not** a failing engineering
test when source facts are genuinely absent.

`SCIENTIFICALLY QUALIFIED` instead needs independently authenticated
prospective first-known events, historical source NAV/full account-book,
funding, matched executable follower and control outcomes, OOS/holdouts,
uncertainty, actual account terms and risk authorization. The optional native weekly `numpy.memmap` screen cache is an
immutable, exact-minute market-data view, not an executable L2 book or
permission to convert mid/open screening prices into certified
follower P&L. The public
90-day oracle-only job retains `financial_certified_real=false` and
`scientifically_qualified=false` despite correctly matching native 1m
context. Synthetic simulated `PASS`/`BREACH` cannot be promoted.
`pm_offline_receipts` ties a sealed local file's IDs/clocks to fixture
events; a SHA hash does **not** independently prove capture authenticity.


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

The [2026-11-01 PM02 gates](PM-02-EVIDENCE-GATES.md) additionally require code-pinned predeclared OOS windows, all declared horizons, whole-account v2 economic proof and independent selection-plan review. Familywise correction uses the declared wallet × horizon × look family; broader search history and tail uncertainty still require independent audit. Reused windows cannot advance lifecycle, RETIRED cannot requalify under the same policy, and missing evidence never counts as falsification. Current qualified count remains zero.

## PM-04 incremental engineering — NOT qualification

[PM-04 contract](PM-04-shadow-hardening.md) and [PM-04 engineering acceptance](PM-04-acceptance.md) add three-pod synthetic target batching, pretrade gross/inflight guards, pod loss budgets, separate intended vs executed attribution and a read-only external execution-evidence seam to the **same** PM-03 account authority. Synthetic reconciliation fixtures, passing accounting identities and report SHA demonstrate only an *engineering* contract. They do **not** show actual Propr order acknowledgments, signed verified broker fills, a profitable independent follower, an authorized account or a live deployment. The currently selected `W028 + W042 + W030` research set remains post-hoc and **not scientifically qualified**.

## PM-03 risk: account equity vs wallet source PnL

- PM-03 `cash`, realized balance, unrealized PnL, equity, floor and fee/funding models are **synthetic ledger quantities** unless independently grounded in actual account records. The risk supervisor is GREEN/YELLOW/ORANGE/RED/HALT and persists HALT; it does not connect an order gateway.
- Public Propr snapshot `v1.0.5` from 2026-07-27 (observed 2026-10-31) is **unconfirmed per account**. `propr_rulebook(...)` sets `confirmed=False`, no market allowlist, no default leverage. The presence of public `www.propr.xyz/universe` display tickers cannot authorize a trade. Contractual copying/aggregation, funded terms, fees and venue fills require independent validation.
- `pm03_stress` compares equal-risk, historical top-PnL (**hindsight biased**) and centralized supervision on the *same synthetic PIT steps*. Simulated target touches and drawdowns are not a calibrated pass-probability distribution; missing source episodes must not be dropped as non-losses.

## Current evidence register — time-scoped, not a permanent result

The latest [recovery disposition](RECOVERY-DISPOSITION-2026-11-01.md) records PR18 integration, current source capture, PM02 governance repairs, bounded market acquisition and the offline [ML4T/Propr specification](ML4T-PROPR-INTEGRATION.md). The older register below retains its historical evidence scope.

| Workstream | Verified scope at this snapshot | Remaining UNKNOWN/blocked |
| --- | --- | --- |
| PM-01 | 36 cohort and frozen vendor source parity; offline 5/15/60m replay and read-only audit; historical Propr native-day 90% shortlist | Full source account equity/funding/collateral and unresolved position chains, minute execution/capacity, independent prospective followed fills |
| PM-02 | Existing actual 36-wallet sealed report SHA `7bf28ee5ad53cdac9212bb0222ae1b3e0ef020eee5faae9972c53028e4b60f4f`: 0 qualified, five EMPTY, 0 actionable R; independent signed *adapter* merged | Real signed/verified economic outcomes and causal independent OOS selection/portfolio utility |
| PM-03 | Engineering and tests merged via [PR #6](https://github.com/hzminhzz/copytrade-pm/pull/6) (Issue #2 closed) | Account-specific Propr authorized execution, calibrated follower PnL and challenge-pass likelihood |
| PM-36 | [Draft PR #7](https://github.com/hzminhzz/copytrade-pm/pull/7) separate 2026Q3 research (not on main), with limited partial episode diagnostics | Whole-book simultaneous account equity, true matched prospective OOS, integration into current `main` |

Current scientific trackers: [PM-01 #4](https://github.com/hzminhzz/copytrade-pm/issues/4) and [PM-02 #5](https://github.com/hzminhzz/copytrade-pm/issues/5). No live order/deployment authority.

## Decision protocol for new research

1. **Define a narrow falsifiable thesis** and the causal event/decision/fill clock, target universe, horizon and held-out period before seeing outcome returns.
2. **Verify source and native market** lineage. Keep missing/source discontinuity and outside-Propr hedge risks explicit. Stop if the required complete book cannot be reconstructed.
3. **Model follower economics**, not source wallet closed PnL: latency, volume/depth/fee/funding sensitivity, same-path matched control, central netting/correlated tails and consolidated account constraints.
4. **Enforce PIT separation and multiplicity.** Historical TID timestamps are hindsight; prohibit using holdout/OOS to tune candidate/risk parameters; freeze the selection family and attempted experiments.
5. **Report rejects and uncertainty.** Negative, blocked, unknown and censored episodes remain visible; no survivorship or missing-return zero fill.
6. **Never authorize live trading** from the PM-01/02/03 package. Any new execution boundary requires a separate specification, dated written Propr approval and explicit owner authorization.

A blocked scientific result stays blocked. For root-cause repair, bounded acquisition and continuation of independent work, follow [RECOVER](BLOCKER-RECOVERY.md); never reclassify missing PIT or outcomes as qualified.

Independent review is handled at protected [governance decision boundaries](GOVERNANCE-GATES.md), not on every research conversation or file inspection. The current read-only Trader Intelligence readiness report is always `NOT_SCIENTIFICALLY_QUALIFIED`; an external review cannot override that state. No scientific signoff/roster promotion writer exists in this repository.

For actual commands: [RUNBOOK](RUNBOOK.md). For precise clock/audit signatures: [PM-01 prospective ledger](PM-01-prospective-ledger.md).

## Offline Polars milestone #2 acceptance distinction (2026-11-04)

The separate offline prototype under PR #92 has distinct verdict domains:

| Result | Verified scope | What is **not** established |
| --- | --- | --- |
| `HISTORICAL_ORACLE` / `VALIDATED_INPUT_ONLY` | SHA/source/clock guard or retrospective compiler | True first-known, future tradability or source profitability |
| `COMPLETE_SYNTHETIC_FIXTURE_ONLY` | Frozen 3/5-wallet, 5-delay, cost-stress scenario; PM-03 Decimal fixture | Real source replay, executable liquidity, contract PASS, scientific alpha |
| `SYNTHETIC_PM03_OPEN/BREACH/TARGET` | Simulated account state from specified artificial events | Real challenge event or probability |
| `UNKNOWN` / `AMBIGUOUS` | Missing funding, equity, source, minute mark, contract attestation, or unresolved intrabar order | Favorable assumption or zero loss |
| `BLOCKED` / `INVALID` | Failed provenance, clock, complete-book, schema, cache or safety gate | Automatic retry with invented data |

Only PM-03's sequential Decimal account may compute contractual cash/PnL
and floor transitions. Polars Float64 price/volume projections are
diagnostics until original exact prices or independently parity-verified
fixed point is available. No contractual real PASS/BREACH is permitted
from the current synthetic runner. A passing engineering suite is not an
independent prospective causal study, scientifically qualified return,
owner-approved risk, deployment or live order authorization.

## Real 90-day Polars compiler versus real follower qualification (2026-11-04)

The [real-data offline audit](OFFLINE-PIT-REAL-ORACLE-20261104.md)
verified 450,172 retrospective perp fills and 322,970/377,130 batch
observations matched to native exact minute open + preceding completed
volume **screening context**. These are genuine local source/market bytes,
**not** 322,970 independently executable fills or realized leader/follower
trades. A bar's open and previous volume do not establish L2 depth, price
impact, successful follower funding or copytrade permission.

A source file's present-day equity scalar is not an historical NAV tape.
No independent historical first-known timestamps or atomic initial
whole-account books were verified for these 94 JSON inputs.
`HISTORICAL_ORACLE_BATCH_SCREEN_ONLY` and
`HISTORICAL_ORACLE_NATIVE_SCREEN_ONLY` therefore cannot produce a
PM-03 financial PASS/BREACH, probability, qualified alpha or risk
authorization. Only the existing PM-03 Decimal account may certify
contractual equity/floor outcomes after full independently evidenced
source, native execution, funding and rulebook prerequisites pass.
