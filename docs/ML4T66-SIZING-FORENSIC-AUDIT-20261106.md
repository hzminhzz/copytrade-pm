# ML4T-66 Barbell sizing forensic audit — 2026-11-06

**Verdict:** Research under-allocation is real. The existing bridge does **not** multiply k twice; the conservative k allocator, its risk-budget calibration, and the *separate* pod-stop controller suppress exposure. No production risk limits were loosened, no trading authorized.

## Audit scope and authority

- Repository: `copytrade-pm`, working research PR #122, owner-private SQLite `ml4t-strict-66` roster, native SHA-verified minute prices and cached source fills.
- Source-account NAV is an untimestamped vendor scalar, not independently point-in-time verified. Opening positions and first-local follower receipts are not fully observed; zero per source coin is a different counterfactual strategy from whole-account replication.
- Risk calibration: August 5–September 18, 2026; separate historical follower study: September 19–November 2, 2026 (45 calendar days each). Wallet candidate selection was retrospective. Follower execution: first-source-event +5m, strict next-minute OPEN, commissions 3.5 bps/side plus adverse slippage 2.5 bps/side, with 12bps stressed costs.
- All sizing comparisons below use **exactly the same** market input, source orders, pod stop/next-open flattening and user-supplied $10,000 challenge (5% daily close-HWM, 10% continuous trailing, +10% target; intrabar adverse low/high bound). The 5%/10% terms are not a verified provider contract.
- The native `research.contract_selector` has been checked. Its EV comparison cannot legally infer a pass probability/EV from these source-event oracles without complete synchronized point-in-time follower tapes; it returns `MISSING_COMPLETE_NET_FOLLOWER_MTM_TAPE` for existing saved portfolios.

## Primary cause: sizing against unprotected worst excursions **and then** hard stops

In `scripts/ml4t66_barbell_protected_oos.py`, pre-sized k is:

```
k = min(
  k_base,
  k_base * (pod_daily_budget - 10) / (1.5 * observed_train_daily_adverse_at_k_base),
  k_base * (pod_lifetime_budget - 10) / (1.5 * observed_train_MDD_at_k_base),
)
```

A further whole-portfolio `$400` aligned, simultaneously adverse risk screen **uniformly shrinks all k** if necessary. But the 45-day calibration comes from the **UNPROTECTED** source-event wallet path at `k_base`, while the actual simulation independently hard-stops and flattens a pod. The former assumes surviving the entire adverse swing without an exit; the latter exits at the hard stop. This is not an algebra error, but it is a policy mismatch when the intended contract is *trade until a fixed $200/pod drawdown, then freeze and flatten*. The additional 1.5x excursion penalty and $10 risk reserve compound the conservatism.

The source-quantity bridge was independently tested for the identity `(Q * k/base_k) * base_k == Q * k`. An explicit per-pod `k_factors` input now removes the obscure rescale-and-reapply operation in the protected research simulator; a regression test compares the direct implementation with the old bridge and preserves matching P&L and gross exposure. No double scaling was found.

### Leading trio base k and actual exposure

| Wallet | k | Leader-equity-equivalent follower capital | 45-day modeled net P&L |
| --- | ---: | ---: | ---: |
| M55 | 0.011954150 | $252 | +$151.86 |
| M22 | 0.012073398 | $621 | +$73.27 |
| M58 | 0.002436930 | $68 | −$1.08 |
| **Total** | | **$941.56** | **+$224.05** |

Peak gross exposure was **$3,352.63**, just 0.335× initial account equity, with zero pod stops. Source-equity-equivalent allocations are *not cash margin*: source leverage remains embedded in copied quantities.

## Matched sizing sweep — same stop rules, 5m / 6bps each executed side

| Portfolio | Sizing | Net P&L | Observed max DD | Peak gross | Pod stops |
| --- | --- | ---: | ---: | ---: | ---: |
| M55/M22/M58 | 1× old k | +$224.05 | $57.10 | $3,352.63 | 0 |
| M55/M22/M58 | **2× old k** | **+$411.93** | $109.27 | $6,556.73 | 0 |
| M55/M22/M58 | 4× old k | +$324.49 | $213.06 | $7,841.33 | 1 |
| M55/M22/M58 | 8× old k | +$136.66 | $274.38 | $13,609.81 | 2 |
| M55/M22/M58 | static-equity 40/40/20 | +$158.19 | $224.66 | $11,734.33 | 3; all frozen/flat |
| M55/M22/M50 | 1× old k | +$220.24 | $56.26 | $3,460.24 | 0 |
| M55/M22/M50 | **2× old k** | **+$376.96** | $105.76 | $6,739.31 | 0 |
| M55/M22/M50 | 4× old k | +$201.38 | $247.12 | $8,498.67 | 2 |
| M55/M22/M29 | **1× old k** | **+$374.75** | $73.72 | $3,825.00 | 0 |
| M55/M22/M29 | 2× old k | +$315.36 | $144.95 | $7,669.76 | 1 |

The 2× k variants have **no pod stop in the separate historical 45-day period**, but this is not proof of zero future tail loss. Training-period 1.5× co-worst stress for M55/M22/M58 increases from **$293.80** at 1× to **$587.60** at 2×; this violates the existing **$400 internal stress ceiling** (and exceeds the $500 challenge daily allowance in the hypothetical aligned shock). M55/M22/M50 similarly rises to $597.18; M55/M22/M29 to $620.00.

**Risk-sensitivity result:** for M55/M22/M58, modeled 12bps cost P&L is +$173.46 at 1×, +$310.55 at 2×, +$203.38 at 4×, +$42.27 at 8×. Thus 2× sizing appears more profitable in this historical path but not stress-admissible unchanged.

## User's explicit $200/pod trailing freeze policy is not the old research allocation

The prior research assigned lifetime limits **$200/$200/$150** in 3-pod portfolios and as little as $100 in 5-pod portfolios, plus daily hard limits of $70–$120. These values were conservative barbell *research hypotheses*; they are not the user's explicitly stated fixed $200/pod trailing kill switch.

A separate opt-in `fixed_200_trailing` experimental stop policy was added: every pod gets a hard **$200 cumulative mark-to-market drawdown** from its own HWM, no extra pod-daily latch, but the **account's daily/trailing floors still apply**. Next-minute OPEN flattening remains cost-bearing and fail-closed on missing price. It **does not** grant permission to spend 3×$200 simultaneously under a $500 account daily limit. The policy remains research-only.

| Portfolio | k mode | Fixed $200/pod modeled P&L | Observed max DD | Stops |
| --- | --- | ---: | ---: | ---: |
| M55/M22/M58 | 1× | +$224.05 | $57.10 | 0 |
| M55/M22/M58 | 2× | +$411.93 | $109.27 | 0 |
| M55/M22/M58 | static-equity 40/40/20 | **+$29.14** | $353.71 | 3 |
| M55/M22/M50 | 2× | +$376.96 | $105.76 | 0 |
| M55/M22/M50 | static-equity 40/40/20 | +$206.97 | $229.74 | 3 |
| M55/M22/M29 | 2× | +$276.26 | $177.02 | 1 |
| M55/M22/M29 | static-equity 40/40/20 | +$272.83 | $255.04 | 3 |

**Why the user's intuition was correct:** pre-sizing targets a historical worst case *before trading* while exit hard stops already enforce a risk-budget liquidation policy. This can leave 66%+ of the account without gross exposure. But **higher k must be admitted by independent pre-trade stress, gross/notional caps and quote-side execution**, not by blindly doubling historical k. This experiment does not enforce pretrade account gross or per-coin concentration caps; a coincident stressed loss beyond $500 remains disqualifying.

## Implementation and verification

The research revision:
1. Adds optional explicit per-wallet k factors to `scripts/ml4t66_protected_portfolio_replay.py`, preserving old behavior by default; the extended script now passes k directly.
2. Adds optional strict daily-boundary start index to skip the 45-day completely flat period without modifying PnL or opening books; forbids orders prior to account start.
3. Adds an opt-in, **research-only** fixed-$200 trailing-stop policy without overriding current production/default PM-03/PM-04 controls.
4. Saves immutable SHA-hashed private stress/replay reports with 1×, 2×, 4×, 8× and 40/40/20 k sensitivities across three trios at 6bps and 12bps.
5. Adds regression tests on k identity, invalid overrides and pod-stop attribution.

Private immutable per-portfolio evidence:

- M55/M22/M58: `barbell-20261106/ml4t66_barbell_protected_oos_080a8d1e53181dd04e1e.json`, SHA256 `080a8d1e53181dd04e1efe86baedfcf1d5138b14455461a1344c84a1d1b0a920`.
- M55/M22/M50: `barbell-20261106/ml4t66_barbell_protected_oos_be19e25076046088c352.json`, SHA256 `be19e25076046088c352593425dc7b2ba470194a218ffac597929cb4d7fdc23c`.
- M55/M22/M29: `barbell-20261106/ml4t66_barbell_protected_oos_98755f8d99f27fc73334.json`, SHA256 `98755f8d99f27fc73334f40465cb06b30511f2eca92d5cb3bb5e679483f6ebbc`.

**Decision: retain existing production controls and historical baseline; do not silently promote the profitable 2× multiplier.** Required next experiment is account-level gross/coin stress admission with asynchronous pod flatten/funding, complete point-in-time wallet leverage/NAV, and matched independent paper execution. Broker orders, deployed release, portfolio registry and contract EV remain unchanged/blocked.
