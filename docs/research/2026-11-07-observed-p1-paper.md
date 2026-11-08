# Observed P1 forward-paper execution — 2026-11-07

This is a research-only, locally first-known, model-executed P1 paper follower. It is NOT a broker route, official Guardian account, real demo fill, scientifically qualified strategy or deployed current TriadA/TriadChop selection.

## Architecture and accounting

The existing public P1/P14 observer is read-only and unchanged. The new observed-paper consumer reads its SHA-linked selected-parent perp position receipts and Hyperliquid CCXT L2 receipts in SQLite read-only mode. A new *private*, separate PM03 ShadowRun ledger owns simulated entry/exit/mark-to-market PnL, fees, attribution, independent pod budgets, risk status and hash-chained replay. Source receipts with first-known times before run creation cannot open retrospective positions. A new first-known whole selected-perp book is treated as a catch-up snapshot, not a leader historical fill.

The old P1 baseline has S035 k=0.0282, S051 k=0.0430 and S053 k=0.0296, each with a nominal $200 pod drawdown stop, a $150 daily pod loss budget, combined $600 nominal pod risk, $10,000 virtual starting cash. These k parameters are from docs/decisions/2026-11-03-gemini-phase3-adoption-180d.md. Other nominal paper rules: $500 daily account allowance, $1,000 static account loss, $20,000 account gross, $5,000 per-market intent, 2x account maximum gross leverage, 300-second native asymmetric batching. These are experimental assumptions, NOT an authenticated prop contract. Loss triggers cannot guarantee execution at the budget.

For every new selected position book, the consumer binds alias and selected account-address SHA to canonical as-of SQLite, validates account all-DEX coverage, source event/local receipt clocks, market quote hashes, native market identity, native lot step and minimum notional. Selected parent-perp exposure uses fixed-k native signed quantity, not whole-account NAV. Unrelated child/spot/vault equity does not veto this fixed-k study. HIP-3 instruments without independent session attestation remain blocked. All source legs must be observable; do not silently skip unknown source markets.

Paper fills use current best ask to buy or best bid to sell, plus 2 bps adverse adjustment and 5 bps fee. Capacity per hypothetical fill is at most 10% of the *displayed* best-level quantity. This is NOT actual exchange depth trajectory, trade volume, executable order admission or a promise of a real fill. Native PM03 and PM04 handle netting, independent pod budgets, 5-minute entry batching, immediate permitted exits/reductions, partial-fill retries, unrealized/realized PnL, cash and fee attribution. Market/source gaps and stale quotes return explicit blockers; no synthetic closure is fabricated. Funding is marked UNAVAILABLE_NOT_POSTED, not silently treated as verified zero.

The output reports net and per-pod virtual positions, account/pod modeled PnL, costs, drawdown, risk state and a private ledger head. It always reports no broker route and zero real broker fills. A positive paper curve is not scientific alpha.

## One-shot research smoke

Run from isolated /home/quant/dev/copytrade-0711 (branch research/0711):

    uv run --frozen --extra market-stream --group dev copytrade-pm-paper-observed \
      --source-db /home/quant/.local/share/copytrade/prospective/p1p14-observer-20261105/paper-events.sqlite3 \
      --registry-db /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
      --state-root /home/quant/dev/copytrade-0711/.workspace/p1-observed-paper \
      --run-id p1_live_0711

Append --watch --poll-seconds 30 for continuous research polling. One public REST market metadata lookup occurs at process startup, no extra WebSockets, no orders and no production Guardian changes. The CLI requires a singleton runner lock and private local state. Continue only from the same persisted manifest and pinned policy; never reset positions to conceal a gap.

## Acceptance and status

Use pytest: tests/test_pm_forward_observed_paper.py, tests/test_pm_forward_observed_l2_execution.py, tests/test_pm04_shadow.py, tests/test_pm04_acceptance.py, tests/test_pm04_faults.py and relevant PM03/market regressions. Test output is engineering evidence, not actual live paper trades.

The existing observer is degraded, and P1/P14 are older baselines distinct from the **current SQLite-selected TriadA/TriadChop**. An observed source frame for ACT04/ACT08/ACT09/ACT10 is not supplied by the P1 observer. Do not pretend those are paper-running; their true selection needs separate approved source feed and independently pinned paper-account identity. Real Demo order execution, live fees/funding, broker reconciliation and independent protective account authorization are separate unresolved evidence classes. Long-running ShadowRun can face per-event replay O(n^2) and requires bounded operational measurement before scaling.
