# Portfolio C E4 — faithful whole-wallet sizing, research-only

**Scope:** Branch `research/portfolio-c-e4-wallet-fidelity`, built on Portfolio C E1/E2/E3 `3b613d7`, as of **2026-10-31**. **Implemented mathematical sizing and PM-04 research integration** are separate from the admissibility of historical source data or actual broker execution.

## Why E4 exists

E1/E2/E3 normalize **each** source trade episode to $200/$2,000. That erases important original wallet allocation information. E4 consumes a **single complete signed account book per wallet at a known-as-of event time**, never independent per-episode anchors, and applies **one common scale factor across every instrument in that wallet**.

For source wallet `p`, source signed quantities `q[p,i,t]`, verified point-in-time source account equity `V[p,t]`, and a synthetic $2,000 share of follower portfolio capital:

```text
base_scale[p,t]    = 2,000 USD / V[p,t]
base_target[p,i,t] = q[p,i,t] * base_scale[p,t]
stress[p,t]        = sum_i(abs(base_target[p,i,t] * mark[i,t])
                          * (source_independent_shock[i] + modeled_turn_cost))
scale[p,t]         = base_scale[p,t] * min(1, 57 USD / stress[p,t])
target[p,i,t]      = round_toward_zero_1e-12(q[p,i,t] * scale[p,t])
```

The same multiplier applies to **longs, shorts, cross-instrument hedges, all supported DEX instruments** and changes when new complete-book/equity snapshots arrive. E4 refuses missing hedges or a position that rounds away. $57 is a 5% headroom margin within each pod's existing $60 stress budget. It is not a claim about real source risk, leverage, lot sizes or margin.

The original wallet-relative `q_i/q_j` allocation and signed notional ratio are preserved at intended target creation, subject to rounding tolerance **10⁻⁹**. PM-04 separately enforces the central $10k account, frozen pod budgets, $3k overall gross cap, $50 reserve, internal crossing, queueing, liquidity and contractual shadow floors. **Actual PM-04 simulated fills need not maintain original ratios** when partial fills or risk vetoes occur. E4 records source-target proportionality checks and *post-decision signed-position tracking error* separately. It does not claim 1:1 live copy-trading.

## Data contract and as-of requirements

An explicitly fabricated [synthetic E4 input fixture](../examples/e4_full_wallet_books_SYNTHETIC_UNVERIFIED.json) is included to test validation/CLI without exposing wallet identities. Its attestation flags and source SHA strings are **test data**, not evidence of a real exchange-account audit. Core: `src/copytrade_pm/pm36_e4.py` with `pm_c_e4_full_wallet_books_v1`, `validate_full_book_manifest`, `e4_size`, `compare_wallet_ratios` and `to_pm04_manifest`. Research driver: `pm_portfolio_c_driver.run_one(..., method="E4")`. Existing E1/E2/E3 inputs are explicitly rejected.

A frozen input must contain **exactly CO-001, W015, VS066**, each with:

- SHA-identified frozen wallet identity; one **whole** `hyperliquid/mainnet:perp:<dex>/<symbol>` signed position map including all zero/nonzero positions, with no guessed ticker stripping or dropped external hedge.
- Positive source account `wallet_equity_usd`, reconciled with collateral/funding; account-event sequence without gaps; all-DEX census attested complete.
- Independent `source_event_at` and `first_known_at` clocks, monotonically increasing, with `source_event_at <= first_known_at`, and a book seen **at or before Q3 begins**.
- Source evidence SHA; every derived E4 input *embeds and rechecks* the original full-book contract rather than trusting only transformed events. **Source SHA/attestation flags themselves are NOT authentication of historical exchange truth** without separately validated original exchange data and receipts.
- Synthetic loss budget and PM-04 market inputs unchanged. A first-known snapshot is used only from the **next minute's open**, not the bar used to observe it; no unknown first-known timestamps are inferred from vendor fill time.

The per-pod sizing is keyed by wallet-equity **as of its complete snapshot**. Trading other pods' positions does not change source sizing. An existing source book can be held across hourly marks; no new wallet sizing decision is invented merely because a price changes. PM-04 may reduce exposure on risk breaches.

The existing PM-04 target payload retains the **actual known source receipt time** per pod. The PM-04 event envelope's `first_known_at` remains the current decision/market quote availability clock, which cannot precede the new quote. Simulated fees, liquidity participation, cash and funding still use the canonical PM-03 ledger. E4 result class: `E4_FULL_BOOK_CONTRACT_NOT_EXTERNAL_ECONOMIC_PROOF`, and `broker_executable=false`.

## Independently inspected current Q3 source readiness

**Private SHA-addressed preflight:** `/home/quant/.local/share/copytrade/reports/portfolio-c-e123-20261031/e4-readiness/e4-readiness-29a78a803525f39f0fbf.json`, raw SHA-256 `29a78a803525f39f0fbf7c84e93545d36a43ae75cf7fcfa45c583c864124714b`. The audit reuses the unchanged 36-wallet manifests, vendor fill/economic source reconstruction, four independently verified overlay generations and recorded retrospective account history. No private addresses or raw wallet maps go to Git.

| Evidence as of 2026-10-31 | CO-001 | W015 | VS066 |
|---|---:|---:|---:|
| Vendor-listed instruments | 26 | 15 | 22 |
| Q3 vendor fills | 2,902 | 628 | 1,221 |
| Instrument first observed only after Q3 start | 11 | 11 | 7 |
| Source chain/gap issues | 1 | 0 | 0 |
| Unmappable raw source instruments | 2 | 0 | 0 |
| Retrospective Q3 account-value timestamps identified | 0 | 17 | 0 |
| Independently admissible complete-book + PIT-equity events | **0** | **0** | **0** |

Retrospective account-value samples retrieved **October 29** are not proof of original Q3 knowledge, full collateral, full all-DEX account census or contemporaneous follower observation. Missing book entries cannot be filled with zero. Lack of first-known history cannot be repaired by assigning old vendor trade timestamps as knowledge clocks. Unmapped instruments/hedges cannot be discarded to make Propr coverage look better.

**E4 historical scientific verdict: BLOCKED_E4_SOURCE_EVIDENCE for all three wallets.** The verified 2026Q3 E1–E3 source episode manifest (`pm_c_historical_oracle_input_v1`) is *not* a valid E4 input, and the E4 workflow refuses it. **There are no legitimate real-wallet E4 Q3 PnL, return, drawdown or challenge-pass probability outputs.**

## Commands

Source audit (read-only original vendor cache; emits private content-addressed report):

```bash
uv run --frozen --group dev --extra market python -m copytrade_pm.pm36_e4_readiness \
  --research-root /home/quant/.local/share/copytrade/reports/five-pod-20261029-research \
  --fill-report /home/quant/.local/share/copytrade/reports/pm36-q3-independent/pm36-2026q3-fills-57f4eb4e6b5abdb755a4.json \
  --episode-report /home/quant/.local/share/copytrade/reports/pm36-q3-independent/pm36-2026q3-episodes-0f10be09d577bfef9e74.json \
  --hyperx-generations \
    /home/quant/.local/share/copytrade/reports/pm01-hyperx-gaps/g20261030t1710a \
    /home/quant/.local/share/copytrade/reports/pm01-hyperx-gaps/g20261030t1745b \
    /home/quant/.local/share/copytrade/reports/pm01-hyperx-gaps/g20261030t1755c \
    /home/quant/.local/share/copytrade/reports/pm01-hyperx-gaps/g20261030t1815d \
  --out /home/quant/.local/share/copytrade/reports/portfolio-c-e123-20261031/e4-new-readiness
```

For a **separately and independently verified** original all-wallet snapshot dataset (not currently present for 2026Q3), use:

```bash
ROOT=/home/quant/.local/share/copytrade/reports/portfolio-c-e123-20261031
MARKET=/home/quant/dev/quant/ml4t-data/.data/store
uv run --frozen --group dev --extra market python -m copytrade_pm.pm_portfolio_c_driver \
  --prepare-e4 --e4-books /private/attested-complete-wallet-books.json \
  --market-root "$MARKET" --out "$ROOT/e4-new-prepared"
# Use the exact printed SHA-addressed `portfolio-c-input-<sha20>.json` path:
uv run --frozen --group dev --extra market python -m copytrade_pm.pm_portfolio_c_driver \
  --input /private/portfolio-c-input-EXACTSHA.json --method E4 \
  --execution IMMEDIATE --cost-multiplier 1 \
  --market-root "$MARKET" --out "$ROOT/e4-new-shadow"
```

These E4 preparation/replay examples are **not** claims that `/private/...` evidence exists. The replay operates through PM-04 → PM-03 and writes a private SHA-verified research ledger, with no broker credentials or order pathway. `pm_portfolio_c_stress` can re-read the E4 sealed account ledger without a second simulator.

## Required source work before real-wallet E4 replay

1. Independently capture or reconcile **all DEX wallet positions**, historical balances, collateral flows, realized and unrealized account equity, funding and liquidation events at each source decision. Confirm *complete* instrument census, not merely the coins HyperX returned.
2. Obtain **genuinely contemporaneous first-known receipts** and a gap-free account event stream for future periods. Historic October snapshots alone cannot establish July's receipt clock.
3. Validate exact Hyperliquid and **real Propr broker** instrument identities, all unsupported hedges, native market opens/depth and executable exit capacity. Never silently substitute CFDs/Binance for HIP-3.
4. Only then freeze an E4 input with audited provenance and repeat PM-04 follower stress/cost/capacity testing; compare to E1–E3 on equal observed windows. Separate modeling fidelity, broker permission and economic follower qualification.

**State:** Sizing algorithm and synthetic PM-04 integration engineered. Historical E4 source admissibility **BLOCKED**. Independent actual exchange/follower execution **NOT VERIFIED**. **NO TRADE, NO LIVE AUTHORIZATION.**
