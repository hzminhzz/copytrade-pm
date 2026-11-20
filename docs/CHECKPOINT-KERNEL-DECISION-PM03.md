# PM03 consumes the canonical checkpoint decision

The paper consumer no longer owns a second financial decision engine. For every
`CWSA_PAPER_REVIEW` written after the cutover it hands `copytrade_kernel` the
normalized decision inputs and consumes the kernel's risk decision, native
targets and net order intents. Paper fill simulation and the signed event hash
stay in the shell, and `order_route` stays `NONE`.

## Decision semantics

`pm_checkpoint_decision.DECISION_VERSION` is `checkpoint_decision_q15_v1` (the
kernel's `DECISION_SEMANTICS`). New rows carry it as `decision_version` and are
persisted in the account state as `pm04.checkpoint_v3.decision_version`.

| Concern | Owner before | Owner now |
| --- | --- | --- |
| Whole-book stress sizing and reduction scale | `pm03_risk.classify` paper tiers | `copytrade_kernel.risk.size_book` |
| Native quantity targets and net deltas | `pm03_risk.classify` + shell lot flooring | `copytrade_kernel.decision.plan_execution` (`checkpoint_execution_projection_v2`) |
| `reduce_only` and per-owner allocation | implicit in the fill model | `NetOrderIntent` |
| Q15 opening-retry suppression | none (memory always empty) | kernel `OpeningMissed`, persisted per owner/instrument |
| Modeled fills, costs, quote claims | shell | shell (unchanged) |
| Signature, policy/mandate binding, event hash | shell | shell (unchanged) |
| No-trade authority (evidence, rulebook, floor, leverage, halt) | `pm03_risk.classify` | `pm03_risk.gate` + kernel `NO_TRADE` |

Consequences worth knowing:

* The paper risk **label** is now derived from the kernel's chosen scale
  (`1 → GREEN`, `≥ yellow_scale → YELLOW`, `≥ orange_scale → ORANGE`, else
  `RED`). A state the old paper tier called `YELLOW` can therefore be `GREEN`
  when the kernel's own limits allow the full request; PM03 no longer shrinks a
  plan the kernel accepted. Paper sizing is now exactly Guardian's envelope
  instead of a second, stricter model.
* `pm03_risk.classify` is unchanged and still used by the non-checkpoint PM03
  paths (`pm03_run`, `pm03_stress`, `pm_offline_account`). It now shares
  `assess()` with the new `gate()`.

## Inputs

`decision_inputs()` maps signed paper evidence onto the kernel vocabulary and
never invents a financial rule:

| Kernel input | Source |
| --- | --- |
| `quotes` (`bid`, `ask`, `known_at_ms`) | verified L2 quote receipt for this review |
| `markets[].qty_step`, `min_notional` | verified native market metadata |
| `markets[].min_qty` | the verified native quantity step |
| `markets[].price_tick` | the paper fill model's 1e-8 price quantum |
| `markets[].liquidity_notional` | displayed best-level size × mark |
| `markets[].fee_rate` | signed `policy.costs.fee_bps` |
| `markets[].initial_rate` / `tiers[0].rate` | the rulebook's signed max gross leverage |
| `markets[].funding_bound`, `liquidation_rate` | `0`: PM03 has no signed funding or venue-liquidation evidence |
| `finance.headroom` | `equity − rulebook floor` |
| `finance.pod_loss_used` | PM03's per-owner realized equity loss |
| `checkpoint_basis` / observed basis | the paper ledger's own entry basis |
| `policy.scenarios` | signed `policy.shocks` (full coverage required) |
| `policy.pod_loss_budget` | signed `policy.pod_loss_limit` |
| `policy.checkpoint_execution.max_gross_notional` | signed `policy.max_gross_notional` |
| `policy.minimum_headroom` | signed `reserve_fraction_initial × initial_balance` |
| `policy.made_limit` | the same headroom: PM03 keeps no cumulative "made" ledger |
| `policy.scale_steps` | `4`, i.e. the paper policy's declared 1 / 0.75 / 0.5 / 0.25 ladder |
| `policy.shortfall_bps`, `hedge_tolerance` | the shared kernel's declared floors (30 bps, 5%) |
| `capabilities` | modeled paper venue: cross-zero and reduce-only are simulated only |

`valid_until_ms` is `now_ms + 1`: native market evidence is re-verified on every
checkpoint and never cached across reviews.

## Q15 opening memory

Persisted as `pm04.checkpoint_v3.entry_memory[owner][instrument] =
{missed_at, qty_at_miss}` and rebuilt on replay from the same state, so no
opportunity history is re-read.

* A terminal miss (expired, kernel `NO_TRADE`, shell veto, Q15 suppression) of an
  **opening** attempt records `qty_at_miss = signed source quantity`.
  A live same-side position is managed, never an opening retry, so it never
  records.
* `qty_at_miss` is **retained**: a later same-sign decrease or a rebound at or
  below it cannot replace the record (the kernel's `OpeningMissed.allows_retry`
  is the only writer gate). Only a genuine increase or a flip writes a new
  record, and only if that attempt also misses.
* A proven entry (the owner holds the same sign as the source leg) clears the
  instrument's memory.

## Journal compatibility

`pm_checkpoint_paper.apply` dispatches on the persisted `decision_version`:

* absent → `_effect(..., legacy=True)`, the frozen pre-cutover body (paper tiers
  size the request, the kernel only supplies the fixed-k notional). Its event
  ids, input hashes, post-state hashes and chain hashes are byte-identical to
  `HEAD`; `tests/test_pm_kernel_decision.py::test_pre_cutover_rows_are_byte_identical_to_the_pre_cutover_golden_vector`
  pins two rows captured from that tree. Legacy rows also never write
  `entry_memory`, so an old snapshot hash is reproduced unchanged.
* equal to `DECISION_VERSION` → the kernel decision path.
* anything else, or a legacy row after a forward row →
  `CHECKPOINT_DECISION_SEMANTICS` / `CHECKPOINT_DECISION_SEMANTICS_DOWNGRADE`.

Forward rows use the effect-id prefix `checkpoint_paper_effect_v4`; legacy rows
keep `checkpoint_paper_effect_v3`.
