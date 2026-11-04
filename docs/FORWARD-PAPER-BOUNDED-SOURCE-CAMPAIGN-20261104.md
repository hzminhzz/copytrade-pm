# Frozen P1/P14 bounded source-capture campaign — 2026-11-04

**Scope:** Public Hyperliquid observation only. No paper execution, orders, synthetic source equity, historical-fill replay, wallet-registry mutation, or unattended service installation.

`pm_forward_source_campaign.observe_frozen_portfolio_readonly` obtains the exact approved frozen P1/P14 member aliases from the existing registry audit and matches each to an owner-private local address locator. By default it invokes the bounded public all-DEX source collector for each parent independently. An explicit `--include-subaccounts` option now discovers that parent's currently reported subaccount roster and observes each subject sequentially into the same SHA-chained wallet source tape, preserving distinct account-address hashes and per-account clocks. Native account parser, per-DEX catalog, signed inventory, and SHA-chained SQLite source receipts remain the authority. The collector never treats parent-account observations as a complete parent/subaccount/spot/vault NAV.

## Command

```bash
uv run --extra source --group dev copytrade-pm-paper-source-campaign \
  --portfolio P1 \
  --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --primary-dir /home/quant/dev/copytrade-pm/data/wallet_fills_90d \
  --secondary-dir /home/quant/dev/copytrade-pm/data/nansen_smart_money_fills_90d \
  --state-root /home/quant/dev/copytrade-pm/data/private/paper_scope_observations_20261104 \
  --seconds-per-wallet 8 --max-frames 10
```

Change `--portfolio P1` to `--portfolio P14` for the five-pod challenger. Add `--include-subaccounts` to attempt a bounded parent-plus-discovered-subaccounts sweep. This adds a roster lookup and up to 16 sequential account sessions per manager, so the total wall time can increase substantially. Even when every subject returns a frame, the sweep is **not atomic**: roster changes, cross/isolated collateral, spot balances, vault positions, source equity and marks remain unverified. Its status is always `BLOCKED_INCOMPLETE_WHOLE_WALLET`; it must never produce paper execution. The bounded command reports the per-parent receipt count, errors, frozen wallet ID resolution and explicit `BLOCKED_OBSERVATION_ONLY_NO_TRADE`. It does not start a daemon or a paper worker. One wallet's acquisition failure is reported without promoting the rest to an admitted portfolio.

## Verification and limits

- Fixture tests cover all P1 aliases, native owner-private address resolution, three account receipts, optional parent-plus-subaccount receipts and child failure isolation, registry unchanged, no broker orders, and continued fail-closed admission.
- Previous independent real public canaries observed S035/S051/S053/S064 with three receipts each and Whale `0x5f94…` with two receipts. These were bounded captures, not live trading or 24-hour continuity.
- Complete source equity and collateral, subaccounts, spot/vault census, authoritative frozen `wallet_id` links, native marks, all-market executable volume, and protected worker identity remain blocked. No 72-hour pilot, 24-hour 50-wallet soak, or scientific OOS evidence is claimed.
