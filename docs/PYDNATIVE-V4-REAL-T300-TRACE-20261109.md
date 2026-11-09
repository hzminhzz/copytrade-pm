# First authentic Pydantic-native V4 T+300 modeled entry — 2026-11-09

## Result / boundaries

**P1 authentic forward source-to-paper T+300 attempt: VERIFIED**, with a
`PARTIAL` modeled terminal outcome, strict source and independent market
evidence, faithful native-quantity fixed-k targets and an unbroken PM03/04
journal. This is evidence of *one* real-source P1 virtual-paper opportunity,
**not** a broker order, full-quantity real fill, scientific trading validation,
or a demonstration that every newly deployed 16-portfolio account has traded.

**FORWARD_EXIT_NOT_YET_OBSERVED**. There is no genuine post-entry selected-source
reduction/close and modeled exit on this P1 journal as of this receipt.
The separate newly deployed 16-ledger Pydantic SHADOW R2 was verified 16/16
operational with no forward entry/exit at its last check; its upstream 14-account
source has repeated restarts and gaps.

Existing deployment context:
- Original P1 canary unit: `copytrade-pydnative-v4-paper-p1-0911.service`,
  running PID `555771`, no restarts, `quant`, original Pydantic release
  `1989e65fb0a8bfa8bf48baeacecd4355dbd998e3`.
- Shared *official* P1 source: existing
  `copytrade-v4-selected-positions-0811.service` (older source implementation)
  and its `.../prospective/v4-selected-positions-0811/paper-events.sqlite3`.
- Independent Vike price tape:
  `.../prospective/v4-minute-0811/paper-events.sqlite3`.
- P1 state journal: `.../prospective/pydnative-v4-paper-p1-0911/pydnative_p1_shadow_0911/events.jsonl`.
- Separate expanded R2 sixteen-portfolio consumer:
  `copytrade-pydnative-v4-sixteen-paper-0911.service`, PID `624197`,
  pinned to `7de2f03c327ca98ef06cc0e64d8429ccd9589980`. These are
  different portfolio ledgers; do not merge performance or run identities.

## Exact source and timing evidence

| Property | Verified original value |
| --- | --- |
| Selected wallet alias | `S051` / `S051-BTC` pod (account address stays private) |
| SHA-256 selected account identity | `b81f7ae9bbf6f676eb1bcb4a9436c58b0f28466183e3eb16d4c5ae37df720c80` |
| Official selected-position receipt | `S051` seq `13635` |
| Committed source receipt SHA | `006033171c9e3a3279d947c223be35402f59696e608e09c9ce3ebd9857acf95d` |
| Source position book SHA | `bd757f496eb65b9366332e519066732ed6c6a5cb9df15b0da6c84abf7c516e45` |
| Stream epoch | `a963ea0605524e4d8165c7c4486e6b57` |
| Original source event (UTC) | `2026-11-09T10:09:35.715000+00:00` |
| First local complete selected-position knowledge T0 (UTC) | `2026-11-09T10:09:36.032617+00:00` |
| Scheduled due = T0+300s (UTC) | `2026-11-09T10:14:36.032617+00:00` |
| Real modeled attempt at (UTC) | `2026-11-09T10:14:38.250828+00:00` |
| Observed lateness | **2.218211 seconds**, inside original 30-second grace |
| Opportunity/intent SHA | `b7eafa0753f606d4e17b6f146b854f253b4cceefd8e876f2ac7020cbba5fc8fc` |
| Committed attempt ID | `attempt_b7eafa0753f606d4e17b6f146b854f253b4cceefd8e876f2ac7020cbba5fc8fc` |
| Terminal state | `PARTIAL` (two virtual fills, one capacity-unverified leg) |

The read-only `_read_source` independently passed original receipt SHA,
chain predecessor, selected alias, selected account and clocks.
`verify_official_position_transition` returned **True** for this exact
source receipt: it is an actual `OBSERVED_STATE_CHANGE`, not baseline,
retroactive fill reconstruction or a fabricated position. The live
`verify_streams` audit reports `integrity=VERIFIED` for all five original
selected source streams, a valid current S051 baseline and linked
`OBSERVATION` transaction. The verified source book contained three nonzero
positions and 11 DEX margin/census entries. The original source is a
first-party official Hyperliquid read-only observer, not an exchange-signed
financial permit; its independent local journal SHA is the attestation here.

## Independent market evidence, exact fixed-k and modeled results

All three quote inputs were verified by comparing the original committed
`vike_minute_receipts` row and its `payload_sha` against the actual
`PM04_PAPER_EXECUTE` quote, `quote_sha` and inner `observation_sha`.
The original Vike read-only `validate_observation` passed for every row.
The quote's `first_known_at` was
`2026-11-09T10:14:36.408362+00:00`: independently known *after* due
and before the modeled attempt. Every observed market row was a first-known
minute-rollup of actual trades, **not verified executable L2 liquidity**.

| Instrument | Source qty | Frozen k | Lot step | Verified target qty | Modeled leg |
| --- | ---: | ---: | ---: | ---: | --- |
| BTC | 0.47237 | 0.0430 | 0.00001 | 0.02031 | FILLED (virtual) |
| HYPE | 480.2 | 0.0430 | 0.01 | 20.64 | FILLED (virtual) |
| xyz:XYZ100 | 0.93 | 0.0430 | 0.0001 | 0.0399 | `UNPRICEABLE_CAPACITY_NOT_VERIFIED` |

Exact Decimal multiplication plus floor-to-lot independently re-derived
**all three target quantities** from the frozen k and source native positions.
No whole-wallet NAV is required by the frozen fixed-k policy.

| Instrument | Matched original Vike observation SHA |
| --- | --- |
| BTC | `97e16cc45b38c8d05f97e3c3ba7bbbad95433b209660dd5891ba36e05bdd1154` |
| HYPE | `84a873577bd2d9ba6fdb77ef826061b70ed2edb075490fd6a776769777193fbe` |
| xyz:XYZ100 | `127849c5f28aaf3831f5e1fb56051597df70450f393125040cf11e6bda25125d` |

The BTC modeled quantity was `0.02031`, model vwap
`74226.24920060`, fee `0.75376756`. HYPE modeled quantity `20.64`,
model vwap `72.95955252`, fee `0.75294258`. These are
hypothetical model outcomes, not broker fills; the capacity-unverified
XYZ100 leg was correctly **not** filled. Recorded fees sum to
`1.50671014` in the P1 virtual account.

## Durable accounting and no-broker verification

A read-only independent pass over 695 P1 journal events checked
`pm03_memory.Event.validate`, original `digest(previous,event)`
chain integrity, unique event IDs and nondecreasing decision times.

The P1 journal had exactly one `PM04_CONFIG`, one
`PM04_PAPER_SOURCE` with ID `src_S051_13635`, and **one**
`PM04_PAPER_EXECUTE` for the opportunity, with 692 subsequent
MARK events at the snapshot. It had **zero EXIT events**.
This chain keeps advancing via MARKET MARKs; do not treat a later
head SHA or event count as immutable reference.

The P1 runtime after the modeled attempt reported:
`risk=GREEN`, `cash=6985.0730045830140`,
`equity=9991.2967145830140`, `costs=1.50671014`,
portfolio inventory `BTC=0.02031`, `HYPE=20.64`,
`real_broker_fills=0`, `order_route=NONE`,
`trading_authorized=false`, `unresolved_exposures={}`,
`pending_exits={}`. This is independently simulated financial accounting
with a separate $10,000 virtual account, not executable follower PnL.

### Acceptance disposition

| Dimension | Result |
| --- | --- |
| P1 original official post-start event and complete selected book | VERIFIED |
| First-known T0, immutable T0+300 due and modeled attempt | VERIFIED |
| Actual lateness within policy | VERIFIED, +2.218211 sec |
| Independent original Vike market observations | VERIFIED, 3 matched SHA rows |
| Native-quantity frozen k, amount-step quantization | VERIFIED, 3 legs |
| One terminal P1 modeled attempt and journal chain | VERIFIED, outcome `PARTIAL` |
| P1 fees/accounting | VERIFIED as *hypothetical PM03/04*, not broker economics |
| P1 real source reduction and exit | **FORWARD_EXIT_NOT_YET_OBSERVED** |
| Post-attempt crash/restart with same financial effect | UNKNOWN; prior empty-state rollback cannot substitute |
| Expanded new R2 sixteen-portfolio genuine entry/exit | **NOT YET OBSERVED** |
| Scientifically qualified | NO |
| Trading authorized | NO |

Original issue #229 calls terminal result one of
`MODELED_FILL/BLOCKED/EXPIRED`; the actual model represents this mixed
three-leg outcome as **PARTIAL**, with real modeled fills and one capacity
block. Preserve the distinct real status instead of silently relabeling
it as a full fill or proof of venue liquidity.

R2 sixteen-portfolio supervisor and original P1 source service were left
running so they may record the next authentic change and later reduction.
No source position was fabricated, no trading order sent, no Guardian or
signer pin changed. Leave #229 **OPEN** until a genuine exit and remaining
required operational/consumer-restart evidence is assessed. Optional #230
and parent #213 stay separately open while required work remains.

## Read-only reproduction (private VPS only)

- Exact source: `_read_source(_readonly(source_db), "S051", 13635)`,
  `verify_official_position_transition(...receipt_id,...receipt_sha...)`,
  and `verify_streams(source_db)` in the pinned P1 release.
- Market: query the original `vike_minute_receipts` by
  `instrument,payload_sha`, then independently recompute
  `digest(quote)`, `validate_observation(observation)`, and
  quantized native fixed-k targets.
- Paper: iterate the isolated P1 `events.jsonl` with
  `pm03_memory.Event.validate` and `pm03_account.digest` to
  verify every original chain link and a unique terminal attempt.
- OS: `systemctl --user show copytrade-pydnative-v4-paper-p1-0911.service
  copytrade-pydnative-v4-sixteen-paper-0911.service
  -p Id -p ActiveState -p MainPID -p NRestarts`.

All evidence above was read from real pre-existing original VPS journals
and installed release source, not from a synthetic test fixture or
retrospective restaging.
