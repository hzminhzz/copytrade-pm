# Follower-wallet 5-minute backtest, 2026-09-01..2026-11-10

**Status:** modeled research replay, **retrospective and in-sample**. Not
follower PnL evidence, not a qualification, not a trading authorization. All
three portfolios remain `NO_TRADE`.

The three portfolios were registered 2026-11-02, 2026-11-04 and 2026-11-07; the
window starts 2026-09-01. Every member was chosen knowing this history, so the
result is in-sample and says nothing about forward performance.

Tool: `experiments/follower_5m_backtest.py` (self-check included).
Outputs: `data/private/backtest_20261112/` (private, not in Git).

## Question

If a follower wallet mirrored each of three current research portfolios with the
**current practice — sample the portfolio net every 5 minutes and trade to it**
(policy A, *not* event-driven T+300) — what would it have earned from
2026-09-01 to 2026-11-10?

## Portfolios (current SQLite registry identities)

| Portfolio | Version | Members | Registry sizing contract |
| --- | --- | --- | --- |
| `regime.macro/TriadA` | 2 | ACT04, ACT08, ACT09 | `NON_EXECUTABLE_SIGNED_RESEARCH` |
| `gemini.phase4/E3` | 1 | ACT04, CM-002, S053-HYPE | `GEMINI_REFERENCE_K_NOT_EXECUTABLE` |
| `Combo2` | 2 | CA-008, W015, W028 | `COMBO2_VIRTUAL_5000_USD_ACCOUNT_NOT_BROKER` |

No signed `k` exists for any of them, so the run uses the repository default
`FIXED_K_NATIVE_QUANTITY` with **k = 1** per member: the follower mirrors the
portfolio's net native quantity per symbol. This is a sizing-agnostic
replication of leader economics, not a calibrated copy ratio. TriadA and E3
share ACT04, so their results are not independent.

## Method

- **Members are netted before any order is sized** (long 2 + short 1 = net 1),
  so offsetting members never trade.
- **Policy A:** the leader's net as known at each 5-minute mark is the follower
  target for that minute; the order executes at that minute's open.
- **Costs:** 4.5 bps taker fee + 2 bps slippage on traded notional. The final
  open position is marked at the last close with no exit charge.
- **Scope:** main-DEX perpetuals only (`dex_name == 'HL'`). Spot-style symbols
  (`@NNN`, `#NNN`, `PURR/USDC`) and builder-DEX positions are excluded and
  listed per portfolio.

Evidence:

- **Fills** — vike `hl_wallet_activity view=fills`, 2026-09-01..2026-11-11,
  paged to cursor exhaustion. ACT04's fetch is a strict subset of the
  independently verified `data/private/triadA_verified` cache (the 200 extra
  rows there are builder-DEX `xyz:TSLA`).
- **Anchor** — vike `hl_archive` positions 2026-09-29,
  `state_ts 2026-09-29T23:52:34Z`. The position at START is the anchor minus
  every fill in `[START, anchor]`.
- **Prices** — ml4t-data 1m Hyperliquid OHLCV, with the vike 1m fills rollup
  closing the store's 2026-10-15..2026-11-09 ingestion hole for non-major
  symbols. On the overlap the two agree exactly on BTC/ETH/HYPE and to within
  0.4 % on the worst symbol. A symbol is admitted only if its longest bar gap
  is ≤ 180 minutes (a 1m bar exists only when a trade happened).

## Validation

1. **Position reconstruction** reproduces every main-DEX position of all eight
   wallets at 2026-11-10T23:59 exactly (6 residual rows, all spot symbols).
2. **PnL reconciliation** against leader economics
   (`Σ closed_pnl + Δ unrealized_pnl`, main DEX). The unrealized legs come from
   vike `positions_hourly`: the first 2026-09-01 snapshot for START, the last
   2026-11-10 snapshot (23:59 UTC) for END, and the anchor slice for the
   midpoint. The START snapshot is 00:56 UTC for the seven wallets that held a
   position that day; ACT08 has no 2026-09-01 row and was flat then, so its
   unrealized is 0. START is therefore aligned to within about 56 minutes, not
   exactly, and the September residual absorbs any intraday move in that hour.
3. **Netting invariant.** Portfolio gross equals the sum of the members' gross
   exactly (0 difference on all three), and netting saves 0 / 0 / 1 USD of
   cost. Members are netted before sizing, so the portfolio PnL is the sum of
   the member PnLs, not a different quantity.

| Portfolio | [START, anchor] leader | follower | diff | [anchor, END] leader | follower | diff |
| --- | --- | --- | --- | --- | --- | --- |
| TriadA | +1,556,937 | +1,555,331 | −1,606 | −816,839 | −791,448 | +25,390 |
| E3 | +1,142,287 | +1,139,866 | −2,421 | −638,669 | −634,837 | +3,832 |
| Combo2 | +28,744 | +28,575 | −169 | −23,440 | −25,441 | −2,001 |

The September leg is 0.1 % / 0.2 % / 0.6 % below leader economics, smaller than
the modeled cost of 9,096 / 10,478 / 1,477. The October–November leg is *above*
leader economics by more than its cost. Neither sign is a general result: both
are path artefacts on these particular books, the START leg additionally
carries up to 56 minutes of unaccounted unrealized move, and this comparison
cannot separate the lag effect from the cost effect.

## Result — policy A, k = 1

| Portfolio | Net | Gross | Cost | Trades | Traded notional | Max drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| `regime.macro/TriadA` | **+763,353** | +783,043 | 19,690 | 1,469 | 30.29 M | −1,412,743 |
| `gemini.phase4/E3` | **+504,495** | +526,838 | 22,343 | 1,876 | 34.37 M | −1,097,426 |
| `Combo2` | **+3,120** | +5,872 | 2,752 | 962 | 4.23 M | −38,973 |

Monthly:

| Portfolio | 2026-09 | 2026-10 | 2026-11-01..10 |
| --- | --- | --- | --- |
| TriadA | +1,688,600 | −490,811 | −434,442 |
| E3 | +1,175,400 | −302,509 | −368,435 |
| Combo2 | +30,657 | −16,359 | −11,179 |

The whole result is September. **October and the first ten days of November are
negative for all three portfolios** (−925,253 / −670,944 / −27,538). The
30-day realized-PnL figures quoted for these portfolios are leader-account
realized PnL; they are not what a follower replicating the same books earned.

A zero-lag replication of the same books (policy L) ends at +761,293 / +509,763
/ +2,871, so the policy-A terminal net differs from it by +2,060 / −5,268 /
+249. Policy L also pays the same modeled cost, so this is a terminal-net
difference between two policies, not an attribution of that difference to lag.

Daily dispersion is large: TriadA's best day is +376,474 and its worst
−319,747; 38 of 71 days are positive.

## Excluded symbols

- TriadA: `#167120`, `#167161`, `@107`, `@151`, `@700` (spot only).
- E3: `@107`, `@151`, `@156`, `@700`, `PURR/USDC` (spot only).
- Combo2: `@182`, `@272`, `@496` (spot only).

No main-DEX perp was dropped for missing prices.

## Limits

This is an **uncalibrated exposure sensitivity**, not follower-wallet PnL. It
prices the leader books; it does not model a funded follower.

- **No PM-03/PM-04 finance.** No starting equity, no headroom, no pod budgets,
  no daily/trailing floors, no HALT, no order authorization. Inventory is
  assumed free and pre-existing, so no position is ever constrained by capital.
- **Funding is not modeled.** Positions are held for weeks; a perp funding
  debit is a real cost that this run omits.
- k = 1 is a mirror, not a risk-budgeted copy ratio. The registry has no signed
  k for these portfolios.
- **In-sample.** Members were selected in November on this same history.
- Parent address only: subaccount fills are not in the parent's fill stream.
- Builder-DEX (HIP-3) exposure is excluded, so the follower is not a complete
  replica of any member's whole book.
- Prices are 1m bars; a 5-minute decision executes at a single minute open with
  no participation or capacity limit.
- The vike `positions_hourly` unrealized-PnL reconciliation is a source-derived
  comparison, not official account-state continuity for every minute.

## $10,000 prop challenge with portfolio k sizing

Tool: `experiments/follower_prop10k_backtest.py`. Same engine and evidence; each
member is scaled by the portfolio's own k instead of 1.

### k availability

| Portfolio | k | Source |
| --- | --- | --- |
| `gemini.phase4/E3` | ACT04 0.00428, CM-002 0.00384, S053-HYPE 0.04708 | `k_factors_reported_100k` in the private eligibility file, ×0.1 for a $10,000 account per the V4 sixteen-portfolio paper decision. Published 2026-11-04. |
| `regime.macro/TriadA` | **none** | Supervisor config (2026-11-12): $10,000, `nominal_risk` $600, `pod_risk` $200, contract `NON_EXECUTABLE_SIGNED_RESEARCH`. The signed selection proof carries members only. |
| `Combo2` | **none** | Supervisor config (2026-11-12): $5,000, `nominal_risk` $300, `pod_risk` $100, contract `COMBO2_VIRTUAL_5000_USD_ACCOUNT_NOT_BROKER` — an equity-scaled policy, not fixed k. |

No k is derived, fitted or inferred. A k solved from this window's own worst
loss would be hindsight, not a sizing policy. TriadA and Combo2 are **BLOCKED**.

Live confirmation: the active 5-minute supervisor
(`copytrade-cwsa-5m-paper-chapter2.service`, `pm_cwsa_six_paper`) takes k from a
signed copy mandate (`copy_mandate_heads`) — its `PORTFOLIO_CONFIGS` carry
members, `starting_balance`, `nominal_risk` and `pod_risk` but no k. Its
2026-11-12 status reports all six portfolios as `BLOCKED_EVIDENCE` with an empty
mandate table, zero positions and equity still at the starting balance. That
status string (`CHECKPOINT_SIGNED_MANDATES_OR_RUN_MISSING`) does not by itself
distinguish a missing mandate from a missing run, so the correct statement is
that **admission is blocked and no signed k is available to replay** — not that
the status proves no k exists. The registry contract and the signed selection
proof independently carry members only.

### E3 at its published k

| | |
| --- | --- |
| Net over the window | +3,026 |
| Final equity | 13,026 |
| Worst UTC day | −1,162 (11.6 % of the account) |
| Max trailing drawdown | −4,415 (44.2 %) |
| Cost | 251 |
| Traded notional | 385,561 |

Both rulebooks are breached: standard (daily 5 % / trailing 10 %) and Propr
1-Step (3 % / 6 %).

### Which floor binds first

Both the worst day and the trailing drawdown scale with k, so their ratio does
not. The floors are **fixed dollars**, so a small enough k always satisfies
both; what the ratio fixes is which floor binds first.

| Portfolio | trailing DD / worst day | rulebook ratio | daily allowance usable |
| --- | --- | --- | --- |
| TriadA (unit book) | 4.42 | 2.00 | 45 % |
| E3 (published k) | 3.80 | 2.00 | 53 % |
| Combo2 (unit book) | 3.06 | 2.00 | 65 % |

At the largest k the trailing floor permits, the worst day uses only 45–65 % of
the daily allowance. Sizing is therefore capped by the trailing floor well
before the daily floor, and no k can use the full daily budget on these books.
That is a statement about the shape of the path, not a pass/fail verdict.

**No pass/fail verdict is possible here.** The replay is unconstrained: it
implements no per-pod stop, no floor-triggered HALT, no margin, no headroom, no
funding and no PM-03/04 finance, and it does not model the profit target a
challenge requires. E3 at its published k breaches both floors on the
unconstrained path.

Adding the pod stop would not settle it either. The binding sizing policy is
explicit that a $200 stop is **a trigger, not a guaranteed maximum loss** under
gaps and slippage, and a per-pod trigger cannot by itself guarantee the account
daily floor: several pods can stop out in the same day, and a gap can fill well
past the trigger. Whether a properly stopped follower passes depends on stop
behaviour that this replay does not model.
