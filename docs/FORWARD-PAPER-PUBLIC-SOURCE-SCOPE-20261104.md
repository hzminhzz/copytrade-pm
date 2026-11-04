# Public Hyperliquid all-DEX account scope — 2026-11-04

**Evidence tier: locally first-known PER-ACCOUNT observations; whole-wallet admission remains BLOCKED.**

`pm_forward_source_observation.read_public_all_dex_scope` reuses the native E4 `_account_state`, `_dex_universe` and `_subaccount_roster` validators for one official `allDexsClearinghouseState` WS frame. Its timestamp is the first local receipt, not the retrospective position event clock. Source data retain distinct provider/native per-DEX time and the private frame SHA. Parent/subaccount addresses are represented in reports only as SHA256 identifiers; production alias mapping remains owner-private.

One all-DEX frame **does not establish** a simultaneous parent/subaccount, spot, vault, collateral, source equity and account-wide NAV. Even with per-DEX census parity, the contract explicitly carries `account_scope_complete=false`, `source_equity=null`, `spot_scope_known=false`, `vault_scope_known=false`, `synthetic_fixture=false`, `whole_wallet_equity_attested=false`. No hypothetical follower fill is admitted from it. The same `admit_source_book` fail-closed verifier remains the final gate.

`pm_forward_source_stream.bounded_source_scope_capture` is an optional, bounded public-only WS consumer: one official `perpDexs` catalog REST query, one `subAccounts` census query, one parent WS subscription, and capped frame/time budgets. Historical provider snapshot backfills (`isSnapshot=true`) are skipped. Unknown/invalid per-DEX timestamp, future event, missing DEX, wrong account or provider disconnect is an explicit blocked condition; **no fills, broker calls, historical reacquisition, or tracker service mutation**. Subaccounts discovered through REST are NOT silently assumed observed; the output says `observed_subject=PARENT_ONLY_NOT_ALL_SUBACCOUNTS`.

Reproduction for an **owner-approved public wallet address**, without repeating the private address in this document:

```bash
uv run --extra source --group dev copytrade-pm-source-scope \
  --alias <owner-private-alias> --address <owner-private-wallet-address> \
  --state-root /home/quant/dev/copytrade-pm/data/private/paper_scope_observations \
  --seconds 10 --max-frames 10
```

Private state stays under canonical `/home/quant/dev/copytrade-pm/data/private/` rather than `.devspace`. The command does not run until invoked, is not a protected deployed financial service, and never reports real paper fill readiness. Tests inject public fake websockets to verify snapshots excluded, signed positions/hedges preserved, no incomplete whole-wallet promotion, and missing provider times blocked.

**Outstanding P0:** independent native complete parent/subaccount/spot/vault NAV and source collateral, continuous same-epoch source coverage, point-in-time marks, independently verified full market trade capacity. A per-parent WS account stream cannot satisfy those alone.
