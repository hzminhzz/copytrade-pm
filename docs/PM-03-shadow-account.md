# PM-03 — consolidated shadow challenge simulator

Status: **engineering research capability**, not scientific wallet qualification or broker approval. This document records the implementation in PR #6. All simulation decisions and fills are **hypothetical**. There is no broker credential, live exchange order, Propr account connection, challenge purchase, automatic stage unlock, or live trading authorization.

## Architecture and boundaries

```text
PM-01 immutable wallet/source evidence (historical is hindsight, NOT first-known)
             |
PM-02 as-of manager proposals (R budgets, EMPTY allowed; no order authority)
             |
   pm03_bridge: frozen SHA and schema gate; risk R never inferred as a position
             |
PM-03 ShadowRun (only shadow account authority)
  |- pm03_rules          dated, verified-public defaults; unconfirmed account terms
  |- pm03_account        Decimal cash/balance/equity, PM virtual books, floors
  |- pm03_risk           deterministic GREEN/YELLOW/ORANGE/RED/HALT supervisor
  |- pm03_execution      internal crosses + bounded hypothetical residual fills
  |- pm03_attribution    intended PM vs executed PM vs consolidated PnL
  |- pm03_stress         same-path equal-risk/top-PnL/central policies
  |- pm03_memory         locked, append-only causal SHA event ledger/checkpoints
  |- pm03_run            deterministic replay, manifest, recover, no real fills
  |- pm03_cli            offline JSON inputs to owner-private immutable reports
```

**Authority:** PM-03 only simulates approval and hypothetical execution. The actual PM-02 36-wallet cohort has **0 scientifically qualified wallets, five EMPTY seats and zero actionable risk**. `pm03_bridge.inspect_pm02` reads the existing PM-02 `pm02_manager_governance_v1` sealed artifact with SHA and as-of checks. `require_external_targets` deliberately cannot synthesize positions from PM-02 R budgets. Real `PROSPECTIVE_OBSERVED` mode never executes fills through `ShadowRun`, even if someone asserts `pm02_qualified=True`. Historical HyperX fill event timestamps cannot be substituted for first-known timestamps.

## Rulebook evidence and legal unknowns

Public information checked against:
- [Propr public Rules](https://www.propr.xyz/rules), rulebook version displayed `v1.0.5` (2026-07-27), observed 2026-10-31 UTC
- [Evaluation Terms](https://www.propr.xyz/terms) and [Funded Terms](https://www.propr.xyz/funded-terms)
- Owner-private, independently existing dated 2026-10-30 source snapshot, stored outside Git at `/home/quant/.local/share/copytrade/reports/five-pod-20261029-research/PROPR_LIVE_RULES_AND_API_SNAPSHOT_20261030.json`

Publicly described **evaluation** limits, not an authenticated account contract:

| Program / stage | Target fraction | Daily loss | Max drawdown | Model |
| --- | ---: | ---: | ---: | --- |
| Classic 1-Step eval | 10% | 3% | 6% | static initial balance |
| Turbo 1-Step eval | 9% | 3% | 3% | static initial balance |
| Classic 2-Step stage 1 | 5% | 5% | 8% | trailing highest equity, cap at start |
| Classic 2-Step stage 2 | 10% | 5% | 8% | trailing highest equity, cap at start |
| Funded stage | no evaluation target | published stage-dependent; independently confirm | published stage-dependent; independently confirm | **not authenticated** |

Daily reset: 00:00 UTC. Daily floor = **realized start-of-day account balance × (1 − daily_rate)**; unrealized PnL is excluded from the balance baseline, but is included in marked equity **when evaluating breaches**. Combined floor = max(daily floor, static floor, trailing HWM floor if applicable). Trailing floor cannot rise above initial account balance when that cap is specified. HWM tracks intraday marked equity, not closing balance. Equality with floor is treated as breach. A breach is permanent within the simulated stage and cannot be manually reset. After a stage target is reached, new exposure is frozen until an explicitly sealed transition event; an emergency reduction is not treated as an executed fill if the market is unavailable.

The `pm03_rules.propr_rulebook` factory has `confirmed=False`, `account_terms_confirmed=False`, no market allowlist, no default leverage, source/observed/effective timestamps and content SHA. **Any unconfirmed rule is blocked from producing simulated account fills.** Tests use explicitly named *synthetic* confirmed fixtures to validate mechanics, not contract eligibility. Source date and document ID are recorded even where limits are unconfirmed.

**Compliance-question register (written clarification required):**

| Topic | Current status | Required evidence |
| --- | --- | --- |
| Wallet-driven external signal aggregation | UNKNOWN; no live permission | Written Propr authorization for multi-wallet independent PM research/risk allocator |
| One-account vs own Propr account cross-copy | CONFLICT: public rules and evaluation/funded annexes differ | Signed account-specific terms and written interpretation, not cosmetic trade alteration |
| API algorithmic execution and supported market IDs | UNKNOWN; display roster ≠ API acceptance; HIP-3 namespace separate | Actual account-specific contract/market-ID allowlist and execution permission |
| Leverage | CONFLICT: public rulebook BTC/ETH 5× vs public effective-API snapshot 10× | Authenticated account margin config and contractual limits |
| Fees/funding | CONFLICT: Hyperliquid pass-through vs example 0.075% | Account statement/fee schedule and funding reconciliation |
| Daily reset when feed interrupted | UNKNOWN until authoritative balance and mark captured | Dated account balance/reset observation, or block |
| Funded-stage payout and loss rules | Account-specific UNKNOWN | Written funded terms for the relevant stage |
| Execution model | Propr says simulated fills may be A/B-booked; not real HL fills | Quote/fill reconciliation and capacity tests before any economic claim |

Never assume regulatory or Propr acceptance from tests or a public docs snapshot. `R` budgets are loss-risk proposals, **not** guaranteed stop-loss bounds.

## Financial accounting invariants

All arithmetic uses `Decimal`; input prices/sizes/amounts cannot be NaN or infinite. Exact identity is (venue, market namespace, instrument), including HIP-3 DEX, not ticker alone.

1. `cash = starting_cash + sum(virtual_PM_cash_flows)`.
2. `equity = cash + sum(consolidated_signed_quantity × known_mark)`.
3. `balance = initial_balance + realized_PnL − modeled_external_fees + funding`; `equity = balance + unrealized_PnL` (rounding tolerance explicitly 10⁻¹²).
4. `consolidated_position[instrument] = sum(virtual_PM_position[instrument])`.
5. `sum(virtual_PM_attributed_PnL) = consolidated_PnL` (rounding tolerance 10⁻¹²).
6. `sum(PM_external_fees) = account_external_fees` and `sum(PM_funding) = account_funding`.
7. `intent_mid_PnL + central_overlay_PnL − execution_price_drag − external_fees + funding = account_PnL`; report includes explicit rounding residual. Source-wallet PnL is `UNKNOWN`, never substituted from hypothetical PMs.

Virtual internal crosses transfer exactly opposing manager quantities at an as-of known mark without changing external consolidated cash/position; they are **not an external Propr fill**. Only the residual external signed delta invokes a hypothetical fill, and only up to known participation capacity. Mark/volume sampled from 1m OHLCV are explicit proxies, not asserted bid/ask, order depth or platform fills. Spread, fee, slippage and impact are separately configurable synthetic assumptions. Missing quote, stale knowledge, unknown capacity, bad clock or unsupported market prevent execution; a reduction request does not count as a fill until modeled as such. Pending/unknown broker state prohibits new simulated risk.

## Predeclared research-risk policy

`RiskPolicy` includes stress-to-contract-headroom ratios: GREEN above 3; YELLOW ≤3 (0.75× proposed targets); ORANGE ≤2 (0.5×); RED ≤1.25 (no new risk, reductions only); HALT at ≤1 (latches). Reserve defaults to 0.5% of initial balance. Gross leverage and instrument concentration limits default to 2× and 50% equity **for synthetic policy tests only**, not assertions of Propr limits. These are configurable/frozen as part of the run manifest; a policy or rulebook changed after sealing cannot rewrite prior decisions. HALT persists through restart; manual reset must be an explicitly appended operator/authorization event and is **never allowed after a contractual breach**.

Stress shock inputs must be supplied for all targeted instruments. When different PMs propose opposing signed targets in one exact instrument, an explicitly positive hedge-break stress loss is **mandatory**; otherwise the supervisor refuses new risk. Liquidity-loss and additional independent hedge-break scenarios are configurable. Unknown stress, stale clocks, source coverage or pending state blocks exposure. No assumption of always-effective hedges. No automatic broker flattening.

## Point-in-time ledger and memory

Each run has a private directory (0700) containing immutable `manifest.json`, append-only `events.jsonl` (0600), SHA checkpoints and reports. Every event carries `source_event_at ≤ first_known_at ≤ decision_at ≤ hypothetical_fill_at`, source SHA, original input payload, deterministic post-state SHA and action/tool trace (identity, status, timing and input/output/rulebook SHA). Events are hash-chained, idempotent, chronological; conflicting revisions, broken chains, truncated tails and stale writers fail closed. An exclusive flock serializes writers and expected-head compare-and-swap blocks concurrent modification. After process crash, the account **replays all events**, verifies each post-state SHA and trace; checkpoints are optional accelerators and require exact replay correspondence. No chat-transcript reconstruction or restoration of secret credentials.

Current ledger schema: `pm03_shadow_run_v1`, `pm03_run_state_v1`, `pm03_account_v2`, `pm03_checkpoint_v1`, and event JSONL. No timestamp backfill is permitted; retrospective discoveries are not prospective evidence.

## Three-policy research comparison

`compare_policies` evaluates **identical, ordered, point-in-time synthetic steps** under: (a) equal *modeled stressed dollar risk per PM* proxy; (b) historical top-PnL wallet **HINDSIGHT_BIASED**; (c) centralized PM-03 supervisor. No missing return is silently imputed. Reported data: equity paths, turnover, external fees, funding, maximum drawdown, 5% historical expected shortfall, contractual breaches, target progress, PM intended/actual economics, central overlay, unresolved executions, risk interventions, input SHA and immutable report SHA. These are not statistically estimated challenge-pass probabilities or demonstrated transferable alpha.

## Reproduction (offline, no network)

Python ≥3.14, uv. The example fixture under `examples/pm03_synthetic.json` contains invented quantities/prices only.

```bash
uv run --extra market --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
uv run --group dev ruff format --check src tests
uv build

uv run --group dev copytrade-pm-shadow \
    --input examples/pm03_synthetic.json \
    --output-dir /tmp/copytrade-pm03-shadow-demo
```

The CLI prints the content-addressed report path and SHA. It never submits orders. A `compare` request accepts only `RESEARCH_SYNTHETIC`; a `replay` request requires versioned input events, run ID and manifest SHAs.

## Engineering limitations vs scientific qualification

Synthetic engineering tests do not demonstrate real Propr fill economics or wallet skill. The PM01-first-known/cross-provider/account-continuity gap, real PM02 manager qualification, actual market order ID and capacity confirmation, fee/rebate/funding calibration and written contract approval are separate evidence gates. Zero wallets qualified as of last verified artifact. Stage transitions require an explicit sealed `STAGE` event rather than blindly enabling a funded account. A 1-minute midpoint proxy omits tick microstructure and actual broker queuing/counterparty execution. NO real trading, funding or production deployment is authorized by this package or PR.
