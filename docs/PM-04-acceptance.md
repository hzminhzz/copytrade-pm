# PM-04 — offline engineering acceptance / review evidence

**Scope:** Issue [#12](https://github.com/hzminhzz/copytrade-pm/issues/12), draft [PR #13](https://github.com/hzminhzz/copytrade-pm/pull/13). Synthetic unit and replay engineering ONLY. No simulated test authorizes Propr orders, authenticated account actions or a challenge purchase. The frozen PM-01 v2 and PM-02 evidence contracts remain unchanged.

## Deterministic contract tests: all 18 named scenarios

| # | Scenario | Public-seam test and expected invariant |
| --- | --- | --- |
| 01 | Two same-side BTC pods | `test_01_same_side_netting_no_double_broker_quantity`: one net signed account quantity; independent PM quantities |
| 02 | Two opposing BTC pods | `test_02_opposite_side_netting_and_internal_cross_not_fill`: only residual modeled external fills, virtual cross labeled non-external |
| 03 | Non-resetting batching | `test_03_nonresetting_300_second_batch_for_multiple_updates`: second signal does not move the release clock |
| 04 | Immediate reduction | `test_04_prompt_reduction_keeps_unrelated_pod_position`: one pod closes, unrelated book remains |
| 05 | Native market ID collision | `test_05_market_namespace_collision_blocks_without_mutation`: exact `venue/market/symbol`, no ticker-only alias |
| 06 | Reversal and zero exit liquidity | `test_06_reversal_with_zero_liquidity_cannot_cross_through_flat`: no fictitious flat/short |
| 07 | Partial fill, fee, funding and attribution | `test_07_partial_fill_fees_funding_and_pod_pnl_reconcile`: Decimal reconciliation after PM-03 funding event |
| 08 | Held + inflight + queued gross | `test_08_pretrade_reserves_current_inflight_and_queued_increases`: conservative gross includes all three |
| 09 | Independent pod stress veto | `test_09_pod_pretrade_stress_budget_prevents_oversized_new_trade`: rejected pod does not trigger account-wide HALT |
| 10 | Mark gap over gross cap | `test_10_gap_over_cap_zero_liquidity_latches_reduction_request`: RED/HALT, durable reduction request, position unchanged |
| 11 | Pod loss suspension | `test_11_pod_daily_loss_suspends_only_losing_pod`: losing pod stops; unrelated pod remains eligible |
| 12 | Account stop precedence | `test_12_account_halt_overrides_all_pods_and_restoration`: global HALT beats per-pod permissions |
| 13 | Duplicate and revised external fill | `test_13_duplicate_fill_and_conflicting_revision`: exact duplicate idempotent, conflicting SHA rejected |
| 14 | Out-of-order cumulative fills | `test_14_out_of_order_fill_sequence_keeps_max_cumulative_only`: no rollback of filled total; no invented account cash |
| 15 | Cancel/fill race | `test_15_cancel_then_fill_race_requires_later_account_snapshot`: unresolved until later complete snapshot |
| 16 | Missing broker balance/reconnect | `test_16_missing_balance_or_reconnect_gap_denies_broker_ready`: UNKNOWN is not flat or safe |
| 17 | Restart with inflight and HALT | `test_17_restart_recovers_halt_pending_orders_and_sha`: same ledger head and actual positions |
| 18 | Fixed-input 3-policy comparison | `test_18_identical_input_three_policy_comparison_and_replay`: immediate/batched/asymmetric deterministic hashed report |

Other mandatory checks live in `tests/test_pm04_faults.py`, `tests/test_pm04_extended_acceptance.py`, existing `tests/test_pm04_shadow.py`, `tests/test_pm04_compare.py` and PM-03 adversarial tests. These include five explicit independent-budget-funding contract tests (`tests/test_pm04_budget_contract.py`) proving total pod daily/drawdown/stress reserves cannot exceed the declared PM-03 account headroom, and cover fee/funding and position mismatches, stale/out-of-order provider observations, expired batch signals, stale or missing market marks, explicit pod restore, source/contract floor, independent pod risk, hard concentration limit, provider canceled-order release only after complete snapshot, journal corruption, comparison cache corruption, simulated crash **after immutable append but before in-memory state update**, and automatic deterministic recovery. Additional regression cases verify a funding-triggered pod loss immediately queues an *unfilled* reduction and that a challenge-stage rulebook change HALTs until reauthorization.

## Independent reviewer P1 corrections (PR #13, comment #6540806432)

`tests/test_pm04_review_regressions.py` now reproduces and protects the following formerly uncovered cases through public `ShadowRun` events:

1. **Sequential opposing BTC pods:** after W028 holds +3 and W042 proposes -2 at the later 300-second batch, net BTC must be +1, W028 virtual +3 and W042 virtual -2. Pod-vs-net sign cannot falsely reject a valid consolidated net decrease.
2. **Suspended pod net reversal:** W028 virtual +3 and W042 -2 produce account +1. After W028 loses its pod budget, request a safe net close to zero and retain the remaining W028 virtual +2 as a non-filled `pending_pod_reductions` amount of -2. The opposite-net -2 remains recorded as `pending_reversals` and cannot auto-open on the next tick.
3. **Low/zero liquidity and restart:** with zero capacity, actual BTC remains +1 and pending safe net reduction -1; capacity 0.5 fills only 0.5, then later reaches flat. Full outstanding virtual pod exit and blocked reversal survive immutable checkpoint replay; no fictitious fill or short.
4. **HALT and simultaneous offsetting changes:** account HALT still permits safe net reduction (when synthetic liquidity and model evidence permit), never new risk. Same-instrument opposing *pod reductions* produce an internal virtual cross without fictitious net broker fill.

The held opposite-side remainder needs separately specified, explicit authorization before actual net-new-risk execution. There is deliberately no automatic release or live adapter in this PR. These tests supplement, not replace, the existing 18 numbered scenarios.

## Independent reviewer P1 source-clock correction (PR #13, comment #6540960265)

`tests/test_pm04_broker_timestamps.py` reproduces the two reported false-READY states through public `ShadowRun` events, with failing tests recorded **before** the production changes:

- **Pre-cancel source, post-cancel receipt:** intent at 10, cancel at 20, complete position snapshot `event_at=15` but `first_known_at=30`, followed by matching balance/fee receipts at 31/32. Broker remains **NOT READY**, cancel/fill race unresolved, full 3 BTC still reserved, and HALT persists across journal recovery. A receipt cannot retroactively change the provider as-of time.
- **Old provider state, recent receipts:** position, balance and fees all `event_at=10`, received at 350/351/352, `broker_max_age_seconds=300`. All three snapshots are stale at decision 352 despite recent receipt clocks; broker remains **NOT READY** and shadow HALT is latched.
- **Positive contrast:** complete position source at 21, received at 30 after cancel source at 20, releases the modeled canceled-order reservation when all snapshots are fresh. Broker may report reconciled readiness, but a previously latched account HALT is **never** automatically reset.
- **Age progression:** after a valid post-cancel snapshot ages beyond 300 seconds, the cancellation balance becomes reserved again and broker readiness is revoked. **Reconnect** likewise requires an as-of source snapshot after the reconnect event, not just late receipt. A reconnect **re-reserves** previously discharged canceled-order quantities until new complete post-reconnect position evidence is received; fresh post-reconnect balance/fee snapshots are separately needed for full readiness.
- **Crash and immutable replay:** an injected crash *after* journal append but *before* in-memory commit reconstructs the late-old snapshot and outstanding canceled-order reservation deterministically. No fabricated account position, broker fill or new live execution path.

The tests run entirely offline and preserve source and receipt clocks independently. Historical SHA-sealed runs from earlier commits are not rewritten; reproduce them using their originally pinned code. Required checks: `uv run --extra market --group dev python -m pytest -q tests/test_pm04_broker_timestamps.py` plus the complete core/market suites, Ruff and build.

## How to reproduce

```bash
uv run --extra market --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
uv run --group dev ruff format --check src tests
uv build
git diff --check

# Synthetic, no external broker or vendor request:
uv run --group dev copytrade-pm-shadow \
  --input examples/pm04_synthetic_comparison.json \
  --output-dir /tmp/copytrade-pm04-acceptance-issue12
```

Reports are SHA-addressed, owner-private, and checked against replayed immutable PM-03 event ledgers; cached reports cannot mask a missing or corrupted underlying chain. **Reproducibility version note:** the earlier PM-04 engineering checkpoint at commit `193fcda` used different synthetic budget semantics. Preserve its immutable evidence and use that **pinned original commit** for forensic replay. This hardening requires a fresh isolated run ID/output root and does not retroactively re-sign or rewrite earlier SHA artifacts. Comparison includes sampled drawdown, *daily balance-derived floor headroom*, contractual headroom, gross/notional ceilings, risk reservations from queued + inflight requests, execution residuals, unreduced positions, pod economics and explicit modeled-vs-real limitations. Never label the synthetic output as challenge-pass probability.

## Safe manual recovery: no mutation of original evidence

1. **HALT/UNKNOWN first** on order-ID ambiguity, duplicate/conflicting fill, stale account snapshots, mark gap, broker mismatch, crash, or corrupt event tail. Disable creation of new-risk intents. A requested close is not a broker-acknowledged fill.
2. Preserve the original `manifest.json`, `events.jsonl`, checkpoints, provider receipts and SHA; never truncate, delete, reset or rewrite an untrusted ledger to make a test pass. Keep original private paths and permissions (0700 directory, 0600 files).
3. Reopen the exact `ShadowRun` run ID and let full immutable replay verify the hash chain and each post-state SHA; compare state with independently acquired *read-only* current provider positions, orders, balance/equity, fees, funding and native IDs. If external evidence lacks an independent signed, reliable source or is stale/partial, the correct state remains UNKNOWN.
4. For a known lost ACK, retain the original intent ID and outstanding reservation; never blindly submit another order. Reconcile provider order history and later complete positions after reconnect. Do not silently turn canceled/uncertain orders into flat exposure.
5. An operator-authorized `MANUAL_RESET` cannot clear contractual breach or unresolved Propr rulebook problems. Pod `PM04_RESTORE` never replenishes used daily/drawdown allowance or bypasses account HALT. Actual live recovery is **out of scope** and must be separately specified.
6. The operator may use a **new isolated private output root** to reproduce synthetic policies, preserving prior immutable results intact. Never overwrite the original run's evidence.

## Engineering versus external gates

- **Engineering acceptance:** all 18 scenarios plus fault tests, deterministic offline CLI, accounting identity, event-chain recovery, Ruff and packaging must pass on the reported commit. The branch is **READY FOR REVIEW**, not merged/deployed.
- **External read-only evidence:** still blocked without a genuinely authorized, independent Propr provider observation interface with trusted signer/clock, exact native market-ID registry, broker order/fill semantics and account-specific balances. The current `pm04_broker_observation_v1` is a **synthetic/untrusted input contract**, NOT an authenticated broker client.
- **Scientific:** W028/W042/W030 selected post-hoc; no qualified prospective follower skill or calibrated pass probability.
- **Trading authorization:** zero. No Propr order submission, credentials, deployment, or changes to `hyperliquid-expert-ensemble`/dirty `trading-connector`.

**Judge review:** repository policy requires external judge when available for a new contested architecture or risk threshold. The engine/policy ownership was user-approved before this PR. Do not claim judge verdict unless a real available interface has been invoked and produced a recorded result.
