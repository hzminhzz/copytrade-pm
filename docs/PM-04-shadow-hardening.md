# PM-04 — three-pod shadow risk hardening (Issue #12)

**State:** Research-only engineering implementation on `feat/pm04-three-pod-hardening`. All balances, model executions, order-intent evidence and market observations remain **synthetic or externally supplied**. No broker client, execution credentials, Propr API, real signed attestation transport, live orders, challenge purchase or ensemble deployment. Wallets W028/W042/W030 are **post-hoc research pods, not qualified**. The source `pm01_fill_only_replay_v2` and PM-02 frozen SHA contracts remain untouched.

## Ownership and event boundary

`ShadowRun` in `pm03_run.py` remains the **exclusive account authority**. The PM-04 feature is an optional versioned coordinator plus independent read-only evidence store kept *inside the same PM-03 account snapshot/immutable event chain*. Legacy PM-03 events and post-state hashes preserve their original format when PM-04 is absent.

```text
PM-01 observations (no event-time-as-receipt promotion)
  -> PM-02 proposals (R does NOT become an order quantity)
  -> independent pod target observation
  -> PM04_SIGNAL / PM04_TICK (nonresetting 300s new-risk queue)
  -> PM-03 classify + execute_targets (shadow-only)
  -> account balance/equity, virtual pod books, pending reductions
  -> PM04_BROKER read-only evidence/reconciliation (not broker fills)
  -> one PM-03 durable, hash-chained ledger + replay + snapshots
```

**Do not run a PM-04 broker observation as if it were an executable order.** The `PM04_BROKER` event only changes the evidence state, never the PM-03 shadow account quantities or cash.

## Contracts

- `PM04_CONFIG` carries `pm04_research_policy_v1`: `version`, `approval_reference`, `pods` keyed by stable IDs, per-pod `budget_ref`, `daily_loss`, `max_drawdown`, `stress_loss`; `max_gross_notional`, `max_instrument_fraction_equity`, `max_stress_loss`, `reserve`, `reconcile_tolerance`, `max_signal_age_seconds`, `broker_max_age_seconds`, `batch_seconds=300`, `broker_required` and `execution_policy`. These are **explicitly synthetic research thresholds**, not authorized Propr limits. At configuration, PM-04 checks distinct pod budget references and explicitly reserves the **sum** of per-pod daily, drawdown and stress allowances against the PM-03 synthetic daily allowance, static/trailing loss budget and declared account reserve. Unfunded or unobservable contractual budgets are rejected; the frozen account-funding receipt is included in the PM-03 snapshot/ledger. An initial config is event-sealed and cannot be silently revised.
- `PM04_SIGNAL`: full PM-03 `Event` causal clocks and `source_sha` plus `input.targets[]`; each target has `pod`, exact `venue/market/symbol`, signed `quantity`, monotone `revision`, source/first-known times, SHA source provenance and matching `budget_ref`. Also provide `observations`, `shocks`, `evidence`, `costs` using PM-03's versioned decision-input shape. A missing/unknown market or stale/future target raises and cannot be backdated.
- `PM04_TICK`: same market/exposure/stress/cost input with no new target. A nonresetting instrument timer releases increases no earlier than first pending signal +300 seconds. Reductions and **consolidated-account** close-before-reverse are prioritized under `ASYMMETRIC` mode. An individual pod may be short while the consolidated position remains long; that is not a net broker reversal. Other comparison modes are `IMMEDIATE` and `BATCHED`.
- `PM04_RESTORE`: an explicit pod restoration authorization reference and eligible unused budget. Account RED/HALT prevents restoration. **No budget-reset-by-restoration**.
- `PM04_BROKER`: `pm04_broker_observation_v1` inside `input.observation`, with `evidence_id`, `kind`, `event_at`, `first_known_at`, and where applicable `order_id`, `instrument`, signed `quantity`, `provider_sequence`, cumulative fill, complete position snapshot, balance/equity, or fee/funding totals. Supported kinds: `ORDER_INTENT`, `ACK`, `PARTIAL_FILL`, `FILL`, `CANCEL`, `REJECT`, `POSITION_SNAPSHOT`, `BALANCE_SNAPSHOT`, `FEES_FUNDING`, `RECONNECT`.

`PM04_BROKER` is **read-only and untrusted synthetic/externally supplied evidence** unless the transport, signer, source-of-truth, provider semantics and account-specific broker contract are separately approved. Same-ID repeat is idempotent; conflicting duplicate rejects; order events preserve higher cumulative quantities across sequence reordering; cancellation/fill races stay unresolved without later full snapshots. **Timestamp invariant:** `event_at` is the source/provider state-as-of clock, while `first_known_at` is local receipt. Both must be causally known and no older than the configured `broker_max_age_seconds` at the decision; receiving stale source-state data now cannot make it fresh. Cancel/fill reservations may be discharged only when a complete position snapshot has both `event_at > order.last_event_at` and `first_known_at > order.last_known_at`, and is still fresh as of the current decision. `last_event_at` tracks the maximum effective order-event timestamp across even out-of-order observations. Reconnect similarly requires both a post-reconnect provider-state timestamp and a post-reconnect receipt; an old snapshot delivered after reconnect does **not** clear the gap or keep a previous canceled-order reservation discharged. The canceled-order quantity remains conservatively reserved again until a fresh post-reconnect complete position observation is available. Expired snapshots re-establish conservative outstanding reservations and, when broker evidence is required, latch HALT until independently authorized recovery. Full position/balance/fee and funding snapshots compare to PM-03's account and never inject fictitious matching fills. Unknown order and mismatches HALT; missing/stale/reconnected observations deny new-risk authorization under `broker_required=True`. A portfolio with broker-required evidence and no actual observations remains **NO TRADE**, not healthy.

## Risk and accounting

- **Pretrade:** model projected gross conservatively as current marked gross plus unsatisfied **increases** plus absolute unresolved in-flight order quantity at current marks. Never credit pending reductions against the exposure ceiling. Enforce max gross, concentration, stress, contractual equity floor and reserve, PM-03's graded classifier, stage/breach state and pod budgets before model fills. A RED/HALT state never permits a new net increase.
- **Ex post:** mark gaps can take actual exposure over the ceiling. Persist `risk_breaches`, `pending_reductions`, `pending_pod_reductions`, `pending_reversals`, RED/HALT and the **actual unresolved position**. `pending_reductions` is the signed safe **account-net exit-to-flat** amount, never the opposite-side new-risk leg; `pending_pod_reductions` separately preserves unfinished virtual pod exits when a net-flat account still contains opposing virtual positions. `pending_reversals` records the held opposite-net remainder and initial decision time; it cannot auto-open on later ticks or after restart without a separately approved net-reversal authorization contract. If execution capacity is zero, holdings are unchanged. It is incorrect to call the ceiling hard ex-post or treat a virtual pod exit as complete when only the net broker book has flattened.
- **Independent pod loss:** `pod_stats` contains executed marked P&L, daily loss, observed drawdown, stress loss, budget remaining, and `ACTIVE`/`REDUCED`/`SUSPENDED`/`RESTORED`. Suspending W028 does not automatically suspend W042. PM-03 account HALT supersedes all pods.
- **Attribution:** PM-03 retains all external modeled fills and virtual internal crosses; no opposing same-symbol pod fills are fabricated. PM-04 `economics` uses PM-03 `explain_economics` with intended mid P&L, executed virtual pod books, central overlay, explicit execution drag, fees and funding. It checks the precise accounting residual. A pod's synthetic modeled P&L is **not** the source wallet's realized P&L.

## Reproduction

Python 3.14 and uv; all commands are offline:

```bash
uv run --extra market --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
uv run --group dev ruff format --check src tests
uv build
git diff --check
```

The existing `copytrade-pm-shadow` CLI accepts `pm04_compare_input_v1`, `action=compare_pm04`, `mode=RESEARCH_SYNTHETIC`, a confirmed *synthetic* PM-03 rulebook, versioned PM-04 policy, frozen SHAs, and a chronological series of `PM04_SIGNAL`/`PM04_TICK`/read-only `PM04_BROKER` event envelopes. It replays identical synthetic inputs under all three policies, records PM-03 ledgers per scenario, and reports equity, sampled drawdown, worst observed day-level equity loss, gross peak, pod P&L, limit breaches, pending reductions, and accounting residual. Every report is content-addressed. The comparison is **not a statistically qualified challenge-pass probability**, and the selected three wallets remain research-only.

Example programmatic contract (for existing synthetic fixture construction):
```python
from pathlib import Path
from copytrade_pm.pm03_cli import execute

# spec must conform to pm04_compare_input_v1; see tests/test_pm04_compare.py
result = execute(spec, Path("/tmp/pm04-shadow-owner-private"))
print(result["sha"])
```

**Private evidence:** keep raw provider receipts, signed original statements, market data, account balances, keys and wallet aliases outside Git. Never reinterpret archived source timestamp as follower first-known.

## Engineering acceptance and recovery

The [PM-04 acceptance matrix](PM-04-acceptance.md) defines the 18 named Issue #12 scenarios, fault/reconnect and after-commit crash recovery tests, immutable replay verification, failure handling and the exact offline run command. Stale market input is a durable HALT without repricing, delayed-but-expired queued targets are recorded without retrospective execution, and gross-limit gaps automatically request reductions while preserving actual unfilled holdings. A pod-specific risk veto is latched independently and must not impose a blanket account HALT on otherwise authorized pods. PM-03 funding events refresh PM-04 attribution and queue loss-triggered exits without claiming fills. A PM-03 challenge-stage rulebook change invalidates the frozen PM-04 budget funding receipt, latching HALT until separately approved reauthorization rather than silently inheriting new terms.

The three-policy comparison now explicitly reports daily balance-derived floor headroom and contractual headroom, conservative queued/inflight reservations, marked gross peak, unresolved reduction inventory, and exact Decimal reconciliation residuals. None of these are broker fills or challenge-pass probabilities.

## Known limits / blocking acceptance

1. There is **no authenticated Propr broker evidence integration**. Signature authority, actual account market IDs and rulebook, reconciliation transport and fill semantics remain external. The synthetic observation contract alone cannot close that gate.
2. 1m market quotes/capacity and synthetic fills are not actual bid/ask depth or Propr broker confirmations; results are *modeled*, not executed economic observations.
3. A valid synthetic target is not a scientifically qualified prospectively measured pod. Independent matched OOS wallet outcomes and Propr account copying/API authorization remain required.
4. PM-36 draft PR #7 is intentionally unmerged. PM-04 does not import PM-36's in-sample wallet selection or claim its historical hindsight EV transferred into a prospective portfolio.
5. The PM-04 compare report is deterministic for a complete immutable input/output run. If an interrupted comparison leaves partial event ledgers but not its final cached report, use a **fresh isolated output root** for a forensic replay; do not rewrite or delete incomplete evidence.
6. The broker account reconciliation boundary assumes received observations accurately represent the provider but cannot validate source authenticity or an external signed transport. Until established, set `broker_required=True` and the account stays blocked.

**Status separation:** `IMPLEMENTED` and `ENGINEERING VERIFIED` describe code and repeatable synthetic tests only. `SCIENTIFICALLY QUALIFIED`, `AUTHORIZED` and `DEPLOYED` are separate and currently unproven.
