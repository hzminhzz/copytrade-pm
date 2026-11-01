# PM02 fixed OOS and whole-account evidence gates

This is the current engineering contract for the prospective PM02 path. It extends
the [signed prospective ledger](PM-01-prospective-ledger.md); it does not modify the
frozen 36-wallet cohort, PM01 replay schema, or historical source-era research files.

## Immutable registration and selection

`python -m copytrade_pm.pm02_campaign --pm01 SEALED_PM01 --out PRIVATE_REGISTRY
--oos-start FUTURE_UTC --windows 4` registers one immutable campaign in that registry.
The CLI uses the actual registration clock; there is no historical clock override.
It records the exact PM01 canonical source hash and 36 aliases, four disjoint
30-day windows by default, horizons 5/15/60 minutes, primary horizon 15, fixed decision
times one hour after each window ends, and all 36 * 3 * 4 = 432 declared hypotheses.
The policy also pins the exact selection, ledger, audit and risk module bytes.
A different policy or source cannot overwrite the registration; old campaigns must
be evaluated with their pinned code rather than silently reinterpreted by new code.

Registration is a local research record, not independent proof of preregistration
or scientific approval. The independent auditor must verify its custody, clock,
global experiment registry, broader search/multiplicity history, control and sizing
plans, and outcome census before signing eligible evidence. Creating another
directory does not make repeated searches independent. This campaign grants no
access to another study's protected holdout, including separately frozen WP4 data.

`pm_manager --campaign PRIVATE_PLAN` rejects an as-of clock before the campaign was
registered and reads only matured fixed looks. With a verified ledger, its evidence and ledger-head cutoff are the declared decision time. Late
records cannot revise that look; earlier source revisions and future outcomes stay
excluded. A signed ledger head without a registered campaign cannot qualify a wallet.

## Independent whole-account outcomes

Legacy `pm02_independent_matched_outcome_v1` records and their existing consumer
shape remain readable. They are not sufficient for the new whole-account selection
gate. Version `pm02_independent_matched_outcome_v2` requires the existing independent
Ed25519 audit and actual recorded first-known clocks, plus:

| Requirement | Attested, hashed evidence |
| --- | --- |
| Selection governance | Exact campaign hash and independent plan review |
| Source intent | Complete source book, equity, one proportional scale and separate source result |
| Whole-account economics | Reconciled balance/PnL, positive declared USD risk unit, complete episode census |
| Execution | Costs, funding and capacity evidence; no invented fill or zero-filled missing return |
| Control and uncertainty | Predeclared matched control and independent tail/uncertainty review |
| Native exposure | Hyperliquid mainnet perpetual market namespace including DEX; no ticker substitution |

All proof claims require boolean True, not truthy strings. Missing or nonfinite
amounts, missing proof hashes, unsupported native instruments, or missing scope fail
closed. A second outcome for the same source event, horizon and campaign is rejected
under the ledger's writer lock even if it has a new episode ID. The code provides
no signing function and creates no real economic attestation.

Actual first receipt, source event, decision, outcome maturity, audit and ledger
recording clocks remain separate. PM02 uses the actual ledger recording time as
outcome knowledge, never a retrospective declared timestamp.

## Statistics and risk

Each horizon is scored separately. Three horizons of one source event do not become
three independent observations. Qualification needs all registered horizons; the
primary horizon supplies the reported current-window economics. Overlapping
decision-to-horizon intervals cannot supply independent qualifying episodes.

The uncertainty multiplier now uses the declared family:
`max(3.5, NormalDist.inv_cdf(1 - 0.05 / (2 * hypotheses)))`.
This is a conservative normal-approximation screen with the existing shrinkage and
positive serial-dependence effective sample estimate, not a guarantee for heavy
tails, optional stopping or unknown prior searches. Independent uncertainty review
and the complete predeclared experiment census remain mandatory.

Source, follower and matched-control returns are distinct. A source R total is only
reported from valid whole-account primary outcomes; historical vendor closed PnL
does not become source account performance. Existing sample, calendar, drift,
drawdown and freshness gates still apply. A decision older than 24 hours is stale
for a new risk proposal; no automatic forward extension is inferred.

Dependence and allocation can use primary outcomes from prior declared windows,
only if known at each original fixed look. This allows the existing 40 matched-day
risk gate to span multiple 30-day windows without rescoring a historical decision.
Absent dates remain absent. Paired return/tail screens, clone clusters and uncertainty
reserves remain required. Concentration now uses the worst observed daily absolute
exposure envelope; quiet days, reversals and opposing wallets cannot average away
observed gross risk. Exact simultaneous exposure is still preferable and requires
independent data. At least 0.5 R stays reserved; each proposed manager remains capped
at 0.2 R, subject to PM03's separate authority.

## Durable lifecycle

A passing new OOS window can advance CANDIDATE -> SHADOW -> INCUBATION -> ACTIVE ->
CORE. Repeating the same window cannot advance a manager, even with a later report
or another ledger head. Sealed decision history retains evaluated window IDs,
transition reasons and statistical failures. Changing campaign mid-chain or
supplying unsealed campaign history is rejected.

Staleness can suspend; valid adverse evidence can reduce; three distinct windows
with statistically supported rejection can retire. RETIRED is terminal in this
policy. Missing data, immature evidence and absent independent audits never count
as falsification. Every state and allocation is a research proposal, with no live
authority. EMPTY / NO TRADE is a valid and required outcome.

## Operational checks

```bash
uv run --frozen --group dev python -m copytrade_pm.pm02_campaign --help
uv run --frozen --group dev python -m copytrade_pm.pm_manager --help
uv run --frozen --group dev python -m pytest -q tests/test_pm02_campaign.py tests/test_pm02_campaign_integration.py tests/test_pm02_whole_account_outcomes.py tests/test_pm02_risk.py
```

The tests use explicit synthetic fixtures only. They verify immutable registration,
multiplicity, UTC ordering, strict claims, source/horizon deduplication, fixed-look
cutoffs, all-horizon requirements, evidence-reuse attacks, every lifecycle state,
native exposures, worst-case concentration and missing-data behavior.

On 2026-11-01 the unchanged historical-only PM02 artifact reproduced exactly:
`7bf28ee5ad53cdac9212bb0222ae1b3e0ef020eee5faae9972c53028e4b60f4f`.
It still has zero qualified wallets, five EMPTY seats and zero allocated R.
Independent, real matched whole-account outcomes have not been supplied to this
new gate. A healthy collector or passing test does not change that scientific status.
