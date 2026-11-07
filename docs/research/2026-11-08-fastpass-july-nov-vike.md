# Fast-pass wallet research: July 1–November 7, 2026

**Status: HISTORICAL_SOURCE_SCREEN_ONLY.** This is retrospective evidence from source wallets, not authenticated first-known follower receipts, executable PnL, an actual prop-challenge pass or broker authorization.

## Authoritative context

- Git worktree: /home/quant/dev/copytrade-0711, branch research/0711, base 613dbd975188e820ff8762e3d6ca87fd9bad09b4.
- Registry: /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite (read-only); inventory SHA-256 6553b8b7a725474b73a3924fcce63c198e42656d8064c82144816240ca0a762d. SQLite physical integrity VERIFIED; 284 distinct research wallets, 32 owner exclusions.
- Current signed research selection: regime.macro/TriadA and regime.macro/TriadChop, known 2026-11-07T01:08:46.706481Z, not trading-authorized.
- Current private registry: 13 distinct latest named portfolio definitions; doctor counts 15 seals, a different denominator. The user's 16 may include external dashboard or other saved definitions.
- Full study window: [2026-07-01T00:00:00Z, 2026-11-08T00:00:00Z). Volatile subwindow: [2026-11-01T00:00:00Z, 2026-11-08T00:00:00Z). Vike MCP provided targeted wallet fills through November 7; independently published all-venue daily archive then listed through November 6.
- Vike 7d summary source: /tmp/vike7d_432.json, SHA-256 d3158770a376d9d4cb0e448edc84a6001f0909d907a066aeb7b989f72e6ed75c. Its rolling 7d realized window is **not** the same as exact UTC November 1–7 PnL.
- Local 159-source-file content-addressed set SHA-256: 27fc98ffd8cea118dda1eabe4cb60c16523cf50b74e9941767fab2dae444b6b3, as emitted by the Polars inventory. This binds input bytes, not atomic publication across the original six source directories.
- Immutable, owner-private Vike recovery: /home/quant/.local/share/copytrade/reports/fastpass-july-nov-recovery-20261108/g-f27027f91fa930437048, generation SHA-256 f27027f91fa9304370488a1b718af500b03aaa6040aa987ebafa0d9de352c14b.

## Fill freshness and recovery

Six private local JSON collections had 159 wallet-address files; 144 wallets yielded 653,058 unique supported native-perp trade IDs within the full study window after across-generation deduplication. Of those 144, 142 are present in current SQLite and 23 have owner exclusions. Only 18 had a local July fill. 65 had at least one local fill after November 1. The directory named ml4t_jul1_to_now_fills contained seven **zero-fill** records: this is an acquisition gap, not proven inactivity.

Comparing Vike's November 7 wallet summary with stored last-fill timestamps, 118 locally known wallets had newer Vike timestamps by more than two hours. This is a *prioritization signal*, not a full proven missing-fill census.

The targeted Vike MCP recovery avoided full multi-gigabyte all-wallet archive downloads:
- 10,669 unique November-tail fills across 10 wallet addresses. Nine requested November windows reached nextCursor=null. DEX-11's larger October 15–November 8 request remains incomplete for the October part, but reached fills from November 1 onward.
- 5,072 closed roundtrip-trade records for six wallets with exact July 1–November 8 requested boundaries; all six requests had null final cursors. 5,053 had is_complete=true and close_observed=true.
- 89 original provider JSON chunks preserved with hashes in a 0700 directory and 0600 files: 15,741 raw mixed fill/trade rows, **not** 15,741 distinct fills. An exact second publication verified existing bytes. SQLite, HyperX vendor caches, signed selections, and services were untouched.
- Vike MCP's 5,000-record result and an oversized DevSpace write caused size-limit failures; after reducing Vike page size to <=1,000 and file chunk size to 150–200, returned pages and nextCursor were handled without counting incomplete pages as complete.
- Retrospective Vike event timestamps are not verified local first-known signal times. Missing first-known remains null.

## Genuine source CLOSED trade results

All dollar numbers below are **source-wallet closed-trade realized PnL after reported source trading fees**, but before funding and unrealized position changes. This is neither follower PnL nor source account total return. Current account equity must not be retroactively used as historical initial capital.

| Registry identity | Complete observed closed trades | July–Nov source realized net USD | Median holding period | Nov 1–7 realized net USD | Nov 1–7 profitable close days | Vendor max DD | Maker share of recent fills |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ID 238 | 2,664 | +37,796.02 | 1.50h | +4,781.49 | 7/7 | 8.7% | 68.4% |
| ID 267 | 1,266 | +9,296.51 | 1.30h | +1,142.42 | 7/7 | 9.2% | 83.0% |
| ID 179 | 499 | +6,399.47 | 1.67h | +972.04 | 7/7 | 6.3% | 0.0% |
| M56 | 166 | +62,362.77 (Sep–Nov only) | 18.56h | +22,948.49 | 5 active profitable days | 20.5% | 94.4% |
| M22 | 335 | +57,408.81 | 13.46h | +451.55 | 2 positive, 2 negative days | 24.1% | 20.4% |
| M43 | 123 | -62,389.82 | 198.82h | +5,889.81 | 5 positive close days | 23.9% | Not acquired |

The IDs are **SQLite-generation-local**, not stable cross-registry identifiers. The three ID-wallets have no current versioned canonical alias; private addresses can be resolved in the verified SQLite generation.

### Why high realized returns can fail the user's fast-pass objective

- ID 238 had 125 positive and 5 negative closed-trade days over the full period. Worst historical source closed-trade day: -$3,474.05. Median per-trade source net: $6.08 on $1,477 median turnover; 68.4% maker. November snapshot open unrealized PnL: approximately -$15,516.
- ID 267 had 120 positive and 1 negative closed-trade day. Worst: -$58.84. Median per-trade source net: $3.39 on $1,284 turnover; 83.0% maker. Snapshot open unrealized: approximately -$95.
- ID 179 had 108 positive and 1 negative closed-trade day. Worst: -$2.32. Median per-trade source net: $2.44 on $902 turnover; 0% maker fills during recovered November period. Snapshot open unrealized: approximately +$324.
- **Very high small-win frequency and passive maker fill share are copyability red flags.** Five-minute delayed taker entries plus a new spread/commission can erase source economics. High win rate is not proof of follower alpha.
- **Closed-trade speed does not mean the whole wallet is non-swing.** The November 7 Vike position snapshot shows ID 238 holding 11 positions (gross ~$180,206, 0.25x current equity) with oldest opened April 2; ID 267 holding 4 (gross ~$15,423, 0.045x) also with oldest opened April 2; and ID 179 holding 3 (gross ~$99,397, 2.03x) also with oldest opened April 2. Copying the full selected perp scope would inherit those older carry exposures. The strategy must be explicitly defined as *new short-lived source episodes* and needs real inventory/handoff evidence; do not silently ignore retained source hedges to make a wallet look fast-only.
- M56: 94.4% maker, 20.5% vendor maximum DD, snapshot unrealized -$13,578 (~12.5% of that snapshot's native account value). Its returned complete trade history starts only September 15.
- M22: despite positive July–November source PnL, a negative -$2,759.54 source closed-PnL day occurred during Nov 1–7, and median trade net was -$13.40. Reject fast-pass resilience.
- M43: full study was -$62.4k, September alone approximately -$93.4k, median hold ~199h. Reject swing manager despite profitable recent week.
- Source closed-only daily PnL correlations for the three primary candidates: 238/267=0.435, 238/179=0.300, 267/179=0.530. Closure-free days were zero for this **descriptive** correlation; it does not measure synchronized marked exposure risk.

## Portfolio hypotheses, not approved selections

**F01 research hypothesis:** {Registry-ID 238, Registry-ID 267, Registry-ID 179}, three independent pod risk budgets. It has the best source recurrence/turnover balance of the studied full-window candidates but is exposed to two maker-dominated managers and small per-trade profits. No executed 5-minute-lag follower result supports a fast-pass probability.

**F02 exploratory challenger:** {Registry-ID 238, Registry-ID 267, M56}. Maker dependence is worse and July–August Vike trade history for M56 is unavailable. Do not promote over F01.

The 30-portfolio target is **not scientifically achieved**. Forming 17 near-identical triples from only 3–4 source-screened managers would not demonstrate diversification or contract-pass performance. Nothing was registered in SQLite or added to the production roster.

## Native PM acceptance boundary

The mandatory native copytrade-pm contracts rules command was run. Its three archetypes are user-supplied and unverified; contract compare requires a **sealed SQLite portfolio, 42+ complete UTC days of joint follower NET mark-to-market PnL, fees, spread, slippage, funding, market impact and account-specific rules**. This research produced no such follower tape. The native negative-control call, copytrade-pm contracts compare --portfolio regime.macro/TriadA, verified the true registry generation and returned status BLOCKED / MISSING_COMPLETE_NET_FOLLOWER_MTM_TAPE, no scorecard and no authorized purchase recommendation. This is the correct contract gate, not a financial performance test.

For F01, use the established PM-03/PM-04 fixed-k selected-native-quantity policy, T+5m batching, $200 nominal pod-loss triggers, gross/concentration limits, daily/trailing challenge floors, and causal quote checks. A $200 trigger cannot guarantee a $200 stop in a gap. Use the existing Polars native market-oracle path for bounded historical screening (label as hindsight). Only authentic first-known receipts plus independently matched follower outcomes can support financial qualification. Do not demand leader whole-account NAV for the adopted fixed-k policy. Missing follower evidence => NO TRADE.

**Verified engineering:** private Vike archive published and existing-generation verification repeated. **Unknown:** follower net PnL, time-to-pass, prop pass probability, first-known economic edge, complete synchronized source account books and broker orderability. No order, protected service change or trading permit was attempted.

## Read-only reproduction

~~~
uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev --extra market python scripts/research_fastpass_history_20261108.py
uv run --frozen --group dev --extra market python scripts/research_vike_recovery_audit_20261108.py
uv run --frozen --group dev --extra market python scripts/research_fastpass_trade_panel_20261108.py
uv run --frozen --group dev --extra market python scripts/research_fastpass_rank_20261108.py
uv run --frozen --group dev --extra market python scripts/research_publish_vike_fastpass_20261108.py
~~~

The publish script has an explicit --publish for private *append-only* acquisition evidence, not registry/protected mutations. Raw address material stays in owner-private storage. This document contains no raw wallet addresses or secrets.
