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

Change `--portfolio P1` to `--portfolio P14` for the five-pod challenger. Add `--include-subaccounts` to attempt a bounded parent-plus-discovered-subaccounts sweep. Add `--include-collateral` for separate public `spotClearinghouseState` and `userVaultEquities` reads per parent and discovered child. The two Info response bodies are bound by independent response hashes and local first-known clocks; they expose row counts only, not an inferred aggregate NAV. Because neither supplies a shared provider event clock, `source_event_at=null` and `source_equity=null` remain mandatory. Invalid or unavailable scopes are explicitly `BLOCKED_SCOPE_ACQUISITION` instead of zero holdings. This adds a roster lookup and up to 16 sequential account sessions per manager, so the total wall time can increase substantially. Even when every subject returns a frame, the sweep is **not atomic**: roster changes, cross/isolated collateral, spot balances, vault positions, source equity and marks remain unverified. Its status is always `BLOCKED_INCOMPLETE_WHOLE_WALLET`; it must never produce paper execution. The bounded command reports the per-parent receipt count, errors, frozen wallet ID resolution and explicit `BLOCKED_OBSERVATION_ONLY_NO_TRADE`. It does not start a daemon or a paper worker. One wallet's acquisition failure is reported without promoting the rest to an admitted portfolio.

## Verification and limits

- Fixture tests cover all P1 aliases, native owner-private address resolution, three account receipts, optional parent-plus-subaccount receipts and child failure isolation, registry unchanged, no broker orders, and continued fail-closed admission.
- Previous independent real public canaries observed S035/S051/S053/S064 with three receipts each and Whale `0x5f94…` with two receipts. These were bounded captures, not live trading or 24-hour continuity.
- New **2026-11-04 live read-only bounded family canary** used `--include-subaccounts` and 2-second/2-frame limits against the frozen P1 and P14 membership in the canonical private `paper_family_canary_20261104` journal. P1 captured 3/3 parent receipts; P14 captured 5/5 parent receipts; all five source addresses had zero subaccounts in that particular public discovery response. All statuses remained `BLOCKED_INCOMPLETE_WHOLE_WALLET`, frozen membership `wallet_id` linkage remained unresolved, and zero paper/broker orders were performed. The three overlapping wallet receipts persisted with sequential source cursors 1 then 2; these are *separate bounded observations*, not an atomic portfolio sample. A zero returned subaccount count is **not** verified absence of other margin, spot, vault, or collateral accounts.
- A second bounded real P1 canary at **2026-11-04 07:55 UTC**, with `--include-collateral`, fetched spot balance rows **6/11/3** and vault equity rows **0/0/0** for S035/S051/S053 respectively. These are response-row counts, **not** amounts, complete equity or evidence of zero economic exposure. The one-frame short WS subscriptions produced 0 new parent position receipts on that run (previous bounded reads remained in the source journal). Per-scope response SHA and first-known time were included only in the printed diagnostics; they are **not yet durably journaled** and cannot serve as prospective source admission evidence. All three still failed the source-equity/atomic-NAV gate.
- Complete source equity and collateral, independently complete parent/subaccount scope, spot/vault census, authoritative frozen `wallet_id` links, native marks, all-market executable volume, and protected worker identity remain blocked. No 72-hour pilot, 24-hour 50-wallet soak, or scientific OOS evidence is claimed.
