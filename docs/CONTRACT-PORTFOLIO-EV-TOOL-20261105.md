# Portfolio x prop-contract EV tool — operator and research contract (2026-11-05)

**Scope:** Read-only, research-only feature inside the existing native `copytrade-pm`
operator facade. The component is `copytrade_pm.pm_contract_selector`, reusing
the existing vectorized `contract_actuary.simulate` engine. It does **not**
replace the PM-03 Decimal risk engine, the wallet registry, protected research
qualification, or the forward-paper execution/receipt workers.

## What it answers

For a **named, SHA-sealed portfolio** (e.g. `gemini.phase4/E6` or
`gemini.phase4/E2`), and a complete **simultaneously observed NET
follower MTM P&L panel**, rank the A/B/C user-specified prop-firm archetype
rules under each evaluation/funded-stage risk scale. Output:

- pass probability for all evaluation stages, estimated fee per successful
  funding attempt, probability of first payout, knock-out before first payout,
  evaluation expiry before first payout, and overall no-first-payout probability
- expected discounted payouts across a **specified 180-day default funded
  horizon**, net expected cash value `E[payouts] - purchase_fee`, ROI on fee
- 95%-normal Monte Carlo lower bound (sampling noise only; **not** model or
  multiple-testing uncertainty)
- best modeled risk scale within each contract, plus overall scenario winner
  only if all considered contracts/policies were evaluated
- versioned rule and input SHA, registry generation and frozen portfolio
  identity, source clocks and modeling assumptions
- `NO_AUTHORIZED_PURCHASE_RECOMMENDATION` on **every** result: positive
  hypothetical EV is not live alpha or an account purchase authorization.

The no-buy alternative dominates negative modeled EV when buying is optional.

## Commands

```bash
# Installed native read-only CLI: no new service and no broker route.
uv run --extra actuary --group dev copytrade-pm capabilities show research.contract_selector
uv run --extra actuary --group dev copytrade-pm contracts rules

# Native current portfolio identity lookup: a saved portfolio is NOT an operating worker.
uv run --extra actuary --group dev copytrade-wallet-registry doctor
uv run --extra actuary --group dev copytrade-wallet-registry portfolio --current

# Explicit absence of economic evidence reports BLOCKED with native portfolio SHA.
uv run --extra actuary --group dev copytrade-pm contracts compare \
  --portfolio gemini.phase4/E6 --portfolio gemini.phase4/E2

# One or more complete owner-private joint PnL tapes, in portfolio argument order:
uv run --extra actuary --group dev copytrade-pm contracts compare \
  --portfolio gemini.phase4/E6 --tape PRIVATE_E6_NET_PNL.json \
  --portfolio gemini.phase4/E2 --tape PRIVATE_E2_NET_PNL.json \
  --paths 100000 --block-days 7 --evaluation-days 180 --funded-days 180 \
  --evaluation-scales 0.5 1.0 --funded-scales 0.25 0.5 \
  --extra-daily-cost 0 --discount-rate 0 \\
  --max-no-first-payout-probability 0.80
```

`--extra-daily-cost` is **USD/day of additional cost at k=1**, on top of the
net modeled tape, not an exchange-bps input. Larger sizes are scaled *linearly*
for screening only; market impact is not independently recalibrated for each k.
The CLI is read-only and emits JSON on stdout. A missing tape, wrong portfolio
identity, unknown leverage (B 25x), incomplete costs, missing clock interval or
stale registry blocks a definitive ranking and exits nonzero.

## Input: private, joint follower PnL

Provide a JSON document with schema
`copytrade_portfolio_net_pnl_tape_v1` and **all** the fields below. This is
a shortened illustration; a production scoring input must contain at least
42 complete UTC days, a gap-free fixed cadence and **every pod** at every mark. A cross-portfolio
winner is withheld unless all compared tapes share the same inclusive start,
exclusive end, interval width and provenance class; identical random block
indices then represent identical historical dates across portfolios.

```json
{
  "schema": "copytrade_portfolio_net_pnl_tape_v1",
  "portfolio_id": "gemini.phase4/E2",
  "portfolio_definition_sha256": "REPLACE_WITH_NATIVE_PORTFOLIO_DEFINITION_SHA",
  "members": ["ACT04", "S051-BTC", "S053-HYPE"],
  "source_status": "HISTORICAL_HYPOTHETICAL",
  "observed_at": "2026-11-05T00:00:00+00:00",
  "pnl_basis": "FOLLOWER_NET_MARK_TO_MARKET_USD",
  "initial_capital_usd": 10000,
  "step_minutes": 60,
  "costs_included": {
    "commissions": true,
    "spread": true,
    "slippage": true,
    "funding": true,
    "market_impact": true
  },
  "peak_gross_leverage": 3.0,
  "rows": [
    {
      "timestamp": "2026-11-01T00:00:00+00:00",
      "pnl_by_member": {"ACT04": "2.40", "S051-BTC": "-0.60", "S053-HYPE": "1.10"}
    }
  ]
}
```

Each `timestamp` is the UTC **start** of a forward interval; its reported
PNL change becomes knowable at the **end** of that interval. The model
applies the increment after each interval, never as a predicted entry at
its start. The final `observed_at` must be no earlier than the end of the
last interval. No duplicate timestamps, omitted pods, nil/NaN/Inf or shifted
calendar days. In addition to the gross market model, the input must
already include follower execution friction, unrealized PnL and the effect
of correlated/offsetting pod positions; realized vendor fills alone are
**rejected**. Input assertions do **not** constitute independent audit proof.

For historical/synthetic-origin follower modeling, the tool rejects mark-to-market
cadences coarser than 60 minutes. The test-only synthetic fixture mode may use
coarser marks, but does not establish intrabar barrier accuracy. One-minute
marks plus adverse high/low excursions are preferable; this NumPy kernel may
be computationally expensive at 100,000 paths and minute resolution.

`--max-no-first-payout-probability` is an optional [0,1] risk constraint;
only risk-feasible scenario policies can be selected. If no policy meets the
limit, the output has no winner. The model does not estimate uncertainty
in the constraint probability itself.

`peak_gross_leverage` is a **self-declared tape value** used for a 25x
screen on the Sprint archetype, not independently proven leverage compliance.
If unknown or beyond the cap at a proposed risk multiplier, the all-contract
ranking is BLOCKED.

The tape dollar PnL must refer to the whole frozen portfolio on the
$10,000 base capital at unit k, *after* the configured pod combination,
cross-pod netting, sizing, 2m/5m delay, participation, costs and funding.
Do **not** pass market mid-returns, original leader's wallet PnL or a
portfolio whose mark-to-market NAV is missing.

## Statistical method

1. Verify SQLite-authoritative wallet registry `doctor` integrity, schema,
   inventory SHA and registered portfolio membership. Legacy CSV parity/import
   age is a separately disclosed diagnostic, not a portfolio identity gate.
   Lookup the sealed `portfolio_id` (namespace or reviewed singleton),
   definition SHA, version, members, known-at and source generation.
2. Validate that every pod is present in every contiguous UTC interval,
   all cost components are marked complete, and the tape identity and
   definition SHA equal the native registry. Keep the input's actual raw SHA.
3. Verify that every compared portfolio uses the **same source window and
   observation cadence**; otherwise report per-portfolio scenarios but withhold
   the global ranking to avoid bull-versus-bear-window selection bias.
4. Sum synchronized per-pod **USD** MTM increments into a joint portfolio
   return path; choose a contiguous 7-day block jointly across **all** pods
   per scenario and sample with replacement. 7 days exceeds the 3-day
   holding horizon described for these strategy families. Longer blocks
   are supported. This preserves observed within-block serial/asset
   dependence, not future position continuity across joins.
5. Feed the **same seeded joint bootstrap** to all contracts and risk
   scales so comparisons share market outcomes. The account simulation
   applies both the daily reset and the continuous/EOD trailing threshold,
   stage transitions and eligible payouts, with a user-scenario $25
   withdrawal reserve. The UTC promotion day is not counted as a full
   funded green day.
6. Return per-contract best scenarios, full grid and the overall best
   scenario **only if no contract or sizing cell is blocked**. Estimate
   `Net EV = mean discounted payouts - fee`, and
   `CI_low = Net EV - 1.96*MC_SE`. Neither handles parameter
   error, serial regime shift, family multiple testing or rulebook uncertainty.
   Exact non-finite output (`NaN` or `Infinity`) is forbidden: an absent
   conditional funding cost is JSON `null` when no simulation passes;
   first-payout timeouts are not mislabeled as drawdown knockouts.
7. Keep scientific qualification and trading authorization false. A
   positive portfolio-contract ranking is **not** an executable trade
   decision, broker permission or observed first-known follower PnL.

## Rulebook coverage and incompleteness

The versioned catalog `user_archetypes_20261105_unverified_v1` covers
A ($40, $900 target, $400/$250 challenge, funded $300 EOD/$200 and 5
green days); B ($75, $800 target, $500/$300, funded $400 EOD/$250, 5 green days,
up to 25x gross-leverage screen); and C ($100, $1,000+$500 two stages,
$800/$500 challenge, funded $800 trailing). All use 80% split.

Only user-provided archetype assumptions are implemented; **these are
not authenticated real provider contract snapshots**. Payout checks
default to every 14 days. Stage balance and HWM reset upon promotion;
a funded daily stop for C is *unknown* (modeled none), and C's declared
no-time-limit is represented by a specified finite research horizon.
The challenge trailing floor uses intraday peaks because sampling is
unspecified. Green-day positive-PnL threshold, EOD lock, balance vs equity,
consistency, payout caps, permitted markets, margin, account expiration,
refunds, refunds by phase, and provider business/credit risk are not
verified. The model's decision is `SCENARIO_ONLY`, never `BUY`.

## What to do when E6/E2 return BLOCKED

Their research selection is saved and SHA-sealed, **not** equivalent to
first-known follower NAV or economic replay. The correct next evidence is
one complete, independently auditable portfolio-level follower book per
interval: whole source account equity and positions, effective pod sizing,
no missing native marks, executable quotes and costs, funding, optional
margin, and prospective as-of observation clocks. The existing PM-03/
offline research and Forward-Paper owners produce/validate those facts.
Do not synthesize them from a vendor fill report or use retrospective
timestamps as signal receipt times.

## Engineering verification

```bash
uv run --extra actuary --group dev python -m pytest -q tests
uv run --extra actuary --group dev ruff check src tests
uv run --extra actuary --group dev copytrade-pm capabilities validate
uv build
```

Native module: `src/copytrade_pm/pm_contract_selector.py` for input/evidence/
policy selection; `src/copytrade_pm/contract_actuary.py` for the lifecycle
kernel. Tests: `tests/test_pm_contract_selector.py`,
`tests/test_contract_actuary.py`. No order route or service deployment.
