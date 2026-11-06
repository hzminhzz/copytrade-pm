# Source-NAV-optional copytrading policy — owner-approved 2026-11-06

**Decision:** ADOPT **risk-budgeted fixed-k mirroring** as the default for future research, shadow/paper readiness, and execution-design work. **Leader whole-account NAV is not a mandatory admission gate** in this policy. Do not stop implementation or ask the owner to fetch parent/child whole-account NAV for fixed-k sizing. Historical equity-normalized research remains a separate opt-in fidelity contract and is not retroactively rewritten.

## Two independent sizing policies

| Dimension | Default: `FIXED_K_NATIVE_QUANTITY` | Opt-in: `ALLOCATION_OVER_LIVE_NAV` |
| --- | --- | --- |
| Target | `leader_signed_qty × source_mark × independently selected signed k` (notional) | `leader_qty × leader_mark / verified leader_nav × follower_allocation` |
| Leader whole-account NAV | **Not required** | Required; independently reconciled PIT |
| Source position scope | Complete **explicitly selected** leader account/perp venue set (e.g., parent perp account only); do not silently claim unrelated subaccounts | Complete scope required by that fidelity policy |
| Leader open trades | Position snapshots preferred; deduplicate fills, preserve net exposure and actual selected-scope exits | Equity-relative complete source exposures |
| Follower equity/headroom | **Mandatory**, from broker/Guardian | **Mandatory** |
| Risk | Configured k and independent follower gross/per-market caps, pod loss supervisor, margin/fees, daily/trailing floor, netting, broker reconciliation | Same |
| Fidelity claim | **No** assertion of exact leader leverage/equity-relative exposure | Only with verified source NAV and time-aligned evidence |
| Trade authorization | Separate protected execution approval | Separate protected execution approval |

For fixed-k, use the **full selected position vector**, never `k × independent fill size` as if each fill were current exposure. At the same source and follower price, 2→3 BTC with `k=0.04` produces a 0.08→0.12 BTC follower target. If prices differ, the **notional** remains `k × leader signed notional`, and follower quantity is `target_notional / follower_mark`. Guardian reconciles against **actual** follower inventory. Source NAV, quote spot balances, and sums of per-DEX collateral are neither inputs nor substitutes.

The native pure function `copytrade_pm.pm_exposure_sizing.target_from_fixed_k` is a **research intent**, with explicit validated k, source and follower marks, follower equity, gross/single-market exposure caps, and a declared pod loss budget. It returns `order_route=NONE`, `risk_supervisor_required=true`; it does **not** independently enforce hard stops or permit execution. The prop application owns signed k and real Guardian enforcement.

The `copytrade-pm-paper-readiness` CLI defaults to `FIXED_K_NATIVE_QUANTITY`; it treats whole source collateral and unrelated child account coverage as optional diagnostics for a **selected parent-perps-only** strategy. It still verifies source/market hash chains, position clocks, canonical account identity, selected all-DEX perp scope, quote freshness and protected worker evidence. It continues to return `BLOCKED_NO_TRADE` when those actual requirements are missing. Only explicit `--sizing-policy ALLOCATION_OVER_LIVE_NAV` invokes the legacy whole-wallet NAV/child/collateral gates.

## Fixed-k acceptance checklist

1. **Selection:** explicitly freeze account identity, targeted parent/child account set, instruments, and a k per pod. Parent-only means the strategy intentionally ignores unrelated child accounts, not that they have no exposure. If children are selected, observe them; do not infer a combined book.
2. **Source:** preserve complete within-scope positions and exits, DEX/instrument identities, event time, **first local receipt time**, gap/reconnect evidence, position-vs-fill agreement, and dedupe. Never infer actual receipt time from historical Vike fills.
3. **Follower:** require broker-confirmed equity and headroom, actual current positions and open/pending orders, market availability/lot precision/costs, liquidity capacity and account-specific prop-firm rule snapshot.
4. **Risk:** enforce per-pod nominal $200 configured loss budget on the standard $10,000 challenge scenario, three-pod $600 aggregate *nominal* budget, gross/per-market exposure, concentration, daily 5% and trailing 10% floors **only when these are the verified contract rules**, funding/slippage stress, kill switch, latching HALT and restart reconciliation. A $200 stop is a trigger, never a guarantee against adverse fills or gap loss. The account/rulebook must override these example numbers if different.
5. **Evidence:** distinguish simulated requests, read-only forward observation, paper follower PnL, actual broker execution, scientific qualification, and owner authorization. Passing code tests is not a positive follower return.

**Do not block solely because:** Vike summary omits NAV; parent/subaccount NAVs are asynchronous; source uses unified account/portfolio margin; spot collateral or vault equity is unknown **when copying only the selected perp position scope using fixed k**. Those are required only if the selected strategy explicitly depends on their exposures or invokes leader-equity fidelity mode.

**Do block for:** absent/invalid k, uncertain selected-scope book, missing/stale first-known receipts, unknown source identity, missing follower equity, absent market quotes/orderability, breached risk caps, unresolved broker reconciliation/permissions or incomplete protected operational safeguards.

This decision does **not** repeal strict source-equity replay requirements for the historical `pm_historical_combos`, `pm_wallet_replica`, or `ALLOCATION_OVER_LIVE_NAV` scientific contracts. Old scientific results and their qualifying claims remain unchanged.

## Repo contracts

- **copytrade-pm:** this document, `AGENTS.md`, `pm_exposure_sizing.py`, `pm_fixed_k_source_scope.py`, `pm_forward_readiness.py` and their tests. Research intent + source/market observations only, `order_route=NONE`.
- **prop-production:** `docs/SIZING-POLICY.md`; signed release `sizing_policy=FIXED_K_NATIVE_QUANTITY` requires explicit `k`, and Planner/Guardian independently check targets, quote and account risk. No operational authorization comes from policy selection.
- **trading-connector:** transport/provider library only; source leader NAV must never be a connector precondition for submitting an *already risk-approved* follower order. Broker-owned **follower** equity/reconciliation remains mandatory.

Update the relevant repository `AGENTS.md`, runbooks and current acceptance gates whenever sizing semantics change. Old time-stamped incident reports are evidence, not standing vetoes over this explicit owner decision.
