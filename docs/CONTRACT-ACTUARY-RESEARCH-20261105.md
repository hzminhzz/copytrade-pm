# Actuarial challenge lifecycle — research-only prototype (2026-11-05)

## Authority and scope

The contracts below are **user-supplied hypothetical archetypes**. No named
provider's authenticated account rulebook, withdrawal policy or tradable
instrument terms have been established. This module may not authorize real
orders, account purchases, portfolio promotion or claims of alpha.

Implementation: `src/copytrade_pm/contract_actuary.py`; deterministic tests:
`tests/test_contract_actuary.py`. This is a standalone stochastic scenario
calculator; it does **not** replace PM-03's Decimal accounting or independent
prospective first-known follower outcomes.

## Corrected Sprint evaluation EOD rule (v2, 2026-11-05)

The owner-supplied Sprint rule specifies **5.0% end-of-day trailing drawdown** for evaluation: the high-water floor only ratchets on the 00:00 UTC daily mark; its existing floor and 3.0% intraday daily limit remain enforceable between resets. The previous implementation accidentally inherited `challenge_eod=False` (continuous intraday ratchet), applying the wrong absorbing boundary. The corrected native rule catalog is `user_archetypes_20261105_unverified_v2` and `B Sprint.challenge_eod=True`.

**Historical synthetic Sprint statistics in the dated v1 tables below are superseded as Sprint rule-model evidence.** The original values are retained for audit of prior runs, *not* to represent the corrected v2 EOD contract. Do not use those B figures to rank a real purchase or portfolio. Existing positive model examples remain unqualified. Other absent terms (EOD floor lock/cap, green-day minimum threshold and withdrawal mechanics) remain explicitly unknown.

## Run

```bash
uv run --extra actuary --group dev python -m pytest -q tests/test_contract_actuary.py
uv run --extra actuary --group dev python -m copytrade_pm.contract_actuary --paths 100000 \
  --seed 20261105 --evaluation-days 180 --funded-days 180 \
  --steps-per-day 4 --daily-sigma 75 --daily-mu 0 --daily-cost 1
```

Contract stages: A $40/(900,)/$400 max DD/$250 daily, funded $300 EOD
DD/$200 daily and five green days per distribution; B $75/(800,)/$500/$300,
funded $400 EOD/$250 daily and five green days; C $100/(1000,500)/$800/$500,
funded $800 continuously trailing, no funded daily limit assumed, no green
minimum assumed. All split 80%. Stage balances and peaks reset to zero.
Daily limit breaches are terminal; daily baseline resets 00:00 UTC. Challenge
trailing peaks update continuously at four discrete marks per day. Funded EOD
peaks update at final daily mark and enforcement applies every mark.

Other **non-verified choices**: no leverage/margin or consistency rule;
no minimum payout; 14-day payout checks; zero payout delay; funded life
truncated at 180 days; maximum 180 days *per evaluation phase* despite
Contract C's stated no time limit; a successful phase 2 resets equity.
No subscriptions, resets, refunds, data access fees or renewals.
Evaluation phase and funded stage share one stationary iid Gaussian USD
P&L law. Daily gross mean and daily standard deviation refer to a
**$-denominated fixed unit strategy**, not market returns. Fee/friction drag
is charged while active, not on each individual observed order. The price
process has neither jump overshoots between substeps nor Brownian-bridge
barrier corrections. Continuous monitoring is therefore only approximated.

Payouts withdraw the smaller of eligible profit since the previous
distribution and account equity exceeding the larger floor by $25; trader
gets 80% of withdrawn profits. The historical peak does not move down when
profits are withdrawn. This is **one** optional policy, not a known or
proven optimal strategy.

## Reproducible 100,000-path base results

Daily gross mean $0, daily standard deviation $75, daily cost $1, seed
20261105, four subdaily marks, 180 days per evaluation phase plus 180 funded
days. Each contract consumes the same seeded innovation sequence; differing
account lifetimes do not induce future-path lookahead.

| Metric | A | B | C |
|---|---:|---:|---:|
| P(funded) | .10400 | .18975 | .10697 |
| P(any payout) | .04930 | .11100 | .08085 |
| Expected payouts | $7.2824 | $22.9503 | $35.2249 |
| Net EV | -$32.7176 | -$52.0497 | -$64.7751 |
| ROI on fee | -81.794% | -69.400% | -64.775% |
| E[payouts] SE | $0.1212 | $0.2565 | $0.4804 |

Strict interpretation: all three are **negative EV** on this synthetic
zero-edge, friction-paying law; A is the minimum expected dollar-loss buy,
C is the least-negative fee ROI. "Do not buy" dominates buying under
a net monetary value objective.

For a second **synthetic positive drift** scenario, daily gross $12 and
cost $1 at the same daily sigma, payouts become A $66.8746, B $177.6239,
C $733.8449; net EV A +$26.8746, B +$102.6239, C +$633.8449. This
ranking is **not** evidence that an actual strategy earns $12/day.

## Stage-invariant bet-size sensitivity (illustrative, not HJB optimum)

A coarse control grid at each fixed multiplier k in {0.5,1,1.5,2.0},
identical in all evaluation/funded stages, uses the synthetic +$12/day gross
/ $1/day friction / $75/day sigma *per unit k* law. Training seed 20261106
and 25,000 paths per cell:

| k | A net EV | B net EV | C net EV |
|---:|---:|---:|---:|
| 0.5 | $156.02 | $307.50 | $309.07 |
| 1.0 | $25.13 | $103.42 | $627.10 |
| 1.5 | -$17.76 | $4.06 | $287.10 |
| 2.0 | -$32.46 | -$40.31 | $143.91 |

Independent fixed-policy evaluation at 100,000 paths, seed 20261107:
A k=0.5 net EV $157.70 (SE $0.80); B k=0.5 $309.12 (SE $1.18);
C k=1.0 $632.42 (SE $2.08). This is a **restricted grid** with
preassigned constant k for each account, not an optimal state-feedback
policy or proof of positive real-world alpha. Contract C is preferred within
this synthetic scenario/grid, not universally.

## Zero-edge mathematical result

A nonnegative payout functional V of a path can be worth more than the
premium F even when pre-fee P&L increments are martingale differences.
The contract buyer can walk away after loss of the fixed fee rather than
fund virtual losses. With no restrictions other than those encoded in an
authentic rulebook:

`EV = E[sum(exp(-r*t_j)*payout_j)] - fee - outside_costs`.

Thus `EV>0` iff the discounted expected payout stream exceeds the all-in
fee. Leverage does not change martingale expected P&L; it changes first
passage and the contract payout distribution. With zero market alpha and
positive execution costs, net P&L becomes a supermartingale; optional
stopping alone cannot generate edge in the *trading account*. The provider
can nevertheless subsidize the contract payoff.

For a toy single-period evaluation with probability 1/2 of reaching
funding, a subsequent deterministic distributable $100 and a split of
80%, expected gross cash payout is $40. Any fee below $40 yields positive
purchase EV; a $40 fee breaks even. The second-stage deterministic payout
is a contract benefit, not zero-edge trading generated by the same
fair random process.

## Missing scientific and production requirements

- Authenticated snapshot per provider and stage: daily clock, equity vs
  balance high-water, trailing cap/lock, green-day dollar threshold, minimum
  eligible payout, safety margin, fees, phase reset, account inactivity,
  account cap and actual withdrawal impact.
- Market path generator from **prospectively available** correlated returns,
  wallet positions, contract/basis funding and exact exchange fee schedule.
- 1m or tick adverse excursion / Brownian bridge for breaches between
  marks; discrete orders with slippage, impact, margin, and jump overshoots.
- Decision policy on each permitted event rather than terminal path
  hindsight; phase-specific leverage grid is a coarse research control.
- Independent multi-run confidence intervals, paired contrasts and
  sensitivity to horizon, trading costs, leverage and rulebook variants.
- For true lifetime value, either unbounded discounted Markov continuation
  valuation or a certified tail-value bound beyond the chosen 180-day
  simulation horizon. Finite-horizon expected payouts are **not** LTV.
- Scientific wallet predictive validation and separate live authorization.

## Source-rule examples (not A/B/C verification)

Provider rule behavior differs. Apex explicitly distinguishes an intraday
daily-liquidation pause from an account-ending EOD trailing failure:
https://apextraderfunding.com/help-center/additional-helpful-items/eod-drawdown-explained/

For Traders documents an initial-balance cap and payout safety:
https://help.fortraders.com/en/articles/11992386-what-does-trailing-max-drawdown-eod-mean-and-how-is-it-calculated

Summit describes additional 5 qualifying-day thresholds, safety net,
minimum payout, consistency cap and maximum lifetime payouts:
https://www.summitpropfirm.com/help-center/eod-trailing-drawdown-accounts/eod-payouts/
