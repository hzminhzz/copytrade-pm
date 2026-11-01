# SafeBroker and Propr integration specification

Status: DESIGN IMPLEMENTED; OFFLINE CONTRACT ONLY; NOT A LIVE ADAPTER.
Issues: [14](https://github.com/hzminhzz/copytrade-pm/issues/14),
[12](https://github.com/hzminhzz/copytrade-pm/issues/12).
Inspected 2026-11-01. The execution request permits this specification and pure
offline contract tests; it does not permit credentials, orders, challenge purchases,
a production route, or changing the dirty connector checkout.

## 1. Decision and evidence

There will be exactly one authoritative real account record: authenticated,
independently reconciled Propr observations for one explicitly approved account and
environment. The durable observation journal is an evidence store, not a second
cash/PnL engine. PM03 remains the sole financial authority for existing offline
ShadowRun replay. Its per-pod inventory, signed netting, virtual crossing, attribution,
five-minute non-resetting batching and HALT semantics remain intact.

| Component inspected | Version / baseline | Exact inspected file SHA256 |
| --- | --- | --- |
| Installed ml4t-live, safety.py | 0.1.2, quant-research Python 3.14 environment | fb19ee64631e0a4349f44cfe254b4f764a0ea0687d5cc19514fa3847f746f43e |
| ml4t/live/protocols.py | same installation | 6b59de4b848f78621bdae3c3d1eb67cbc41efd5492f7380ae3c71ea04bdf4d16 |
| ml4t/live/persistence.py | same installation | 29d701082719135607c1bd7d8705d2bd7e5ac11697829e9bb84cc9981fa6eade |
| trading-connector, ml4t_bridge.py | package 0.1.0; HEAD 6175a948e6d253ba6f4b610b97b34d8433662e77 | 30b26ee611bf95165914335c7d6c16daddc8600caa878824e073c6febbb5b5bc |
| connectors/propr/models.py | same checkout | c31aae71dcfbb10510ce867774ef99923364324a38b6544a005f4f9cd550eea6 |
| connectors/propr/sdk.py | repository-owned wrapper, not an assumed upstream SDK release | d0186287c7be7537b1aa988ec06df9a0e28c6a9abbe9a05baeb4c18c05d2f163 |
| PM03/PM04 baseline | PR13 merge 8dd0c97971b41cd8d1c0e177050ed4cb059f30ec | Existing source and acceptance fixtures in this repository |
| Recovery integration | PR18, 4d6dc6e934155ffbb398ca0f42e28e7a3ee39f1a | Whole-wallet handoff and read-only source capture; no broker route |

The connector is dirty and has concurrent work. Its inspected file hashes are more
precise than its HEAD for this review; none of its files were changed. Version labels
alone do not prove an installed distribution equals upstream source.

### Findings that affect the interface

1. SafeBroker defaults fail_on_reconciliation_mismatch to False. Setting it to True
   is necessary but insufficient: connect only raises on mismatch outside shadow
   mode. Its shadow snapshot path returns VirtualPortfolio positions and no pending
   orders, rather than real broker inventory. A shadow-mode success therefore cannot
   authenticate or reconcile a real Propr account.
2. In the inspected reconciliation serializer, pending orders lose native order IDs,
   cumulative filled quantities and client-intent IDs. Fingerprints are keyed by
   asset/side/quantity/type/prices; dictionaries can collapse two identical-shaped
   orders. An identity-aware reconciliation gate must run before this lossy view.
3. ProprLiveBroker._sync_state publishes both asset and base-symbol aliases pointing
   to one position. BTC and BTC/USDC are therefore two dictionary keys for one row;
   separate quote markets can collide on BTC. SafeBroker's strict key/position.asset
   validator can reject the alias row, while other cache consumers risk duplication.
   Existing InstrumentRegistry checks do not repair this separate live-cache path.
4. The live bridge supplies fallback timestamps using local current time, defaults
   missing quotes to USDC, and defaults some unknown order enums. Those defaults
   cannot establish native identity, event time or a valid order state.
5. Position/order/account reads are sequential, without demonstrated common provider
   watermark. A successful HTTP sequence is not a coherent account snapshot.
6. The bridge's local journal improves traceability, but observed submit calls do
   not establish a provider-enforced idempotency key. A timeout followed by a new
   submission remains unsafe. Cancel acknowledgement is not terminal inventory.
7. SafeBroker's generic daily loss uses a session-start equity reference; restart
   handling uses host-local date.today(). Its percentage drawdown compares to HWM
   and breaches on greater-than. Those mechanics are not the Propr contract below.
   SafeBroker's durable kill switch and compare-and-swap persistence remain useful.

These are source-level findings. No real broker was instantiated to obtain them.
The offline oracle does not claim to repair these third-party/connector behaviors.

## 2. Ownership and veto order

| Responsibility | Authority |
| --- | --- |
| Source book, one wallet scale, research evidence and PM02 proposals | copytrade-pm; never order permission |
| Pod books, loss budgets, batch clocks, net intent and attribution | PM03/PM04 |
| Real cash, equity, balances, positions, fills, fees and funding | Authenticated Propr account observations |
| Account-specific daily/static/trailing floor and session events | Versioned thin Propr rule gate |
| Generic size/exposure checks and latched kill switch | SafeBroker, with explicit mode and mandatory reconciliation setting |
| Native API transport, market IDs and order lifecycle | trading-connector Propr adapter, future separate scope |
| Persistent mismatch/unknown-state veto | Identity-aware reconciliation gate, mandatory in every mode |
| Any future order authorization | Separately recorded owner/account authorization, absent today |

Permission is the conjunction of every gate. UNKNOWN, stale, incomplete, mismatched,
RED or HALT denies an increase. Neither a PM02 R proposal, a clean offline replay,
a public market listing, a successful SafeBroker connect, nor a provider environment
named Beta supplies authorization.

SafeBroker.VirtualPortfolio can serve isolated tests. It must not become an additional
real cash/inventory ledger. A future live mode reads the authoritative broker record;
any local reservations are explicitly unfilled intentions and remain separate.

## 3. Native identity and observations

A signed registry must bind provider, environment, account class, native market ID,
base/quote/settlement asset, contract multiplier, precision/tick/lot size, margin and
hedge mode, effective time, first receipt, and raw metadata digest. No ticker-only,
USD-to-USDC, gold/SP500 or DEX substitution is allowed. Unknown metadata is NO TRADE.

Display aliases are lookup conveniences only. BTC may resolve only if the registry
proves a unique native identity. BTC/USDC must not erase another quote market,
HIP-3 namespace, account, or hedge-side position. Keep exactly one inventory entry
per provider position identity. Multiple lots/sides require an approved lossless
aggregation policy; otherwise reject, without netting them into a fictional position.

The offline NativeRegistry oracle is deliberately strict: bijective native mappings,
ambiguous-alias rejection, account isolation, duplicate position/order rejection,
decimal quantities, and explicit rejection of unsupported multiple native lots.
It is not a production market registry or a signed observation verifier.

Required observation envelope:

| Field group | Contract |
| --- | --- |
| Identity | Schema, provider/environment/account, stream epoch and native record IDs |
| Evidence | Raw bytes hash, transport provenance, independent verifier identity/signature, append-only journal hash |
| Clocks | Provider event time; local first application receipt before parse; reconciliation/decision time; actual provider fill time where applicable |
| Completeness | Full account scope; positions, pending orders, balance/equity, cumulative fees/funding; explicit missing fields and gaps |
| Sequence | Native monotonic sequence/cursor and deduplication identity; no synthetic claim of a provider sequence |
| Money/quantity | Lossless decimals/native integer units, currency and multiplier; no float tolerance that hides a native tick |
| Orders | Stable client intent, native order ID, side, type, reduce-only, original quantity, cumulative fill and terminal status |
| Account rules | Pinned account contract, daily reference, HWM, payout/stage events and effective-time lineage |

event <= first receipt <= decision must hold. Both event and receipt freshness must
pass the registered policy. Unknown provider clocks stay unknown; local now cannot
replace them. If the provider lacks an atomic snapshot, acquire a documented bounded
barrier/cursor and prove that intervening events are reconciled; otherwise remain
incomplete. Authentication/signatures do not themselves prove financial completeness.

Keep source-event, source-receipt, strategy decision, hypothetical follower fill,
broker ACK, broker fill and cancel clocks distinct. Public source collection is not
authenticated broker collection. pm04_broker_observation_v1 remains an offline
externally supplied observation contract, not proof of broker identity.

## 4. Reconciliation, persistence and races

Run identity-aware reconciliation against the last accepted broker snapshot and
all intervening native lifecycle events before producing the SafeBroker view.
Compare order IDs and multiplicity, signed quantities, cumulative fills, cash,
equity, fees/funding, currencies, positions and unresolved reservations.

A mismatch must latch HALT before any baseline replacement. Preserve both sides and
their hashes. Setting a flag in SafeBroker alone is insufficient. A later clean
snapshot does not automatically clear the latch. Reconnect requires source-event
and receipt clocks newer than the reconnect and relevant cancel/fill events.

For a future separately authorized execution adapter:

1. Freeze an intent containing account, registry/policy/authorization hashes,
   PM04 net revision, pod attribution, decimal order parameters and stable client ID.
2. Append and fsync the intent before transport; reserve worst-case unresolved size.
3. Use provider-enforced idempotency if verified. Without it, an ambiguous submission
   can only be resolved by authoritative native lookup, never blind retry.
4. Record ACK, partial/cumulative fill, reject, cancel-request, cancel-ACK and final
   post-event account reconciliation separately. Late fills remain possible after
   cancel acknowledgement. Retain reservations until the required post-cancel proof.
5. Crash before send, during send, after accept/before ACK, after fill/before commit,
   and during cancellation each replay the same intent identity. Unknown remains
   HALT. Journal hash/CAS generations prevent two writers from advancing authority.
6. Replay does not reset batch clocks, pod loss budgets, HWM, session references,
   audit history, cancellation uncertainty or HALT. A cancel/replace needs verified
   old-order terminal state and a new independently authorized revision.

PM04 already covers these *offline* behavioral requirements in its own journal and
18-case/adversarial tests. A future external adapter must pass the differential
suite; this document does not assert it currently does.

## 5. Propr floors and contract versioning

Primary source: [Propr rules](https://www.propr.xyz/rules), re-read 2026-11-01.
The displayed changelog still identifies daily-loss rule v1.0.5 dated 2026-07-27.
The public text agrees with the existing PM03 daily/static/trailing calculation for
the three supported program variants, but is not the user's activated account
contract. Do not backdate its observation or silently expand the frozen rulebook.

Let B0 be initial balance, Bd the independently established 00:00 UTC realized
balance, E current equity including floating PnL, and H the highest observed equity
including floating gains. For the currently supported public variants:

- Daily floor: Bd * (1 - d), with d=0.03 for the supported 1-step variants and
  d=0.05 for Classic 2-Step. A restart must not replace Bd with current equity.
- Classic 1-Step static floor: B0 * 0.94. Turbo static floor: B0 * 0.97.
- Classic 2-Step trailing floor: min(B0, H - 0.08 * B0). H does not fall during
  ordinary drawdown.
- The effective floor is the maximum applicable floor; E <= floor is a breach.
  New risk additionally needs stressed-loss and reserve headroom above the floor.

These formulas remain PM03 shadow policy until an account-specific attestation
confirms program, stage, permitted instruments, timestamps, rates and units.
The public site also discusses another program and contains internally inconsistent
leverage/payout wording. Its trailing section says payout resets HWM to starting
balance, while a payout bullet describes reducing HWM by the payout amount.
Do not resolve those differences by invention. Payout, transfer and stage changes
require authoritative provider events and a separately versioned policy; absent
that proof, HALT. Existing shadow evidence is preserved.

Generic SafeBroker max_daily_loss/max_drawdown_pct are additional vetoes, not
substitutes for these monetary floors. In particular, a ratio to HWM, host-local
day reset, strict greater-than comparison and session-start equity cannot reproduce
the above semantics without the provider-specific gate.

## 6. Deterministic acceptance and rollout

Run the existing financial authority and the new pure contract oracle:

```bash
uv run --frozen --group dev python -m pytest -q tests/test_pm_ml4t_contract.py
uv run --frozen --group dev python -m pytest -q tests/test_pm04_broker_timestamps.py
uv run --frozen --group dev python -m pytest -q tests
uv run --frozen --group dev --extra market python -m pytest -q tests
uv run --frozen --group dev ruff check src tests
uv run --frozen --group dev ruff format --check src tests
uv build
git diff --check
```

The contract tests cover BTC alias collisions, distinct quote inventory, duplicate
native lots, cross-account rows, identical-shaped orders with distinct IDs, partial
fill changes, exact decimal differences, stale source/fresh receipt, every permitted
non-executing mode, persistent HALT, and deterministic non-mutating evaluation.
All fixtures are explicitly synthetic; no keys, provider objects or network calls.

The future differential fixture must carry the *same* signed native input sequence,
clock and rulebook into PM03 and the proposed adapter. Compare every event's signed
net position, pending size, virtual pod attribution, cash/cost/funding conservation,
daily/trailing floors and veto state; deterministic equality is required, with
native-unit rounding declared before replay. Include all 18 PM04 cases, opposing
+3/-2 pod targets, suspended exits/reversals, stale-source fresh-receipt attacks,
duplicate aliases, identical-shaped orders, cancel/fill races and every crash point.
An implementation that does not yet exist cannot claim this differential acceptance.

Stages and rollback:

| Stage | Current permission | Rollback |
| --- | --- | --- |
| Pure fixtures/specification | Authorized and testable now | Revert code/spec commit; preserve evidence |
| Authenticated read-only account observation | EXTERNAL: owner account, permission and verifier required | Stop observer; preserve raw evidence/HALT |
| Shadow differential against real observations | Depends on complete account scope and approved adapter | Retain PM03 baseline; stop candidate |
| Paper or live routing | Not authorized; separate reviewed implementation and owner go/no-go | Disable route; reconcile outstanding native orders, do not blindly flatten or resubmit |

Pin source hashes and dependency lockfiles at each stage. A rollback never points
a service at a dirty checkout, discards broker evidence, rewrites a frozen research
artifact, or clears HALT. Do not deprecate PM03's pod books, replay, attribution or
Propr floor semantics as part of a generic broker-library migration.

## 7. Unresolved acceptance

- EXTERNAL: actual Propr account/environment, API permissions, copy/aggregation
  permission, native market metadata, account rules, signer and authenticated clocks.
- EXTERNAL: reviewed provider support for native idempotency, snapshot coherence,
  fee/margin/payout semantics and route classification.
- EXTERNAL: separate authorization and implementation of any executable adapter.
- TEMPORAL: independent prospective qualification of managers; zero currently pass.
- JUDGE_UNAVAILABLE: no external judge verdict is claimed for the new interface.

Issue14's specification/offline-contract work is complete as described, but its
account-specific and future-adapter acceptance conditions remain unchecked.
