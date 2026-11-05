# ML4T-66 bounded batch recovery — 2026-11-05

**Scope:** owner-private `ml4t-strict-66` SQLite cohort. Read-only source reconciliation and historical-oracle execution diagnostics only; not a contract-pass study, prospective follower study, authorization or portfolio registration. Base code inspected at `58dc8ee1490238fb6f066fb3e27c548d75962c70`.

## Source authority and execution boundary

- SQLite registry (`/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite`) is authoritative for the cohort, exclusions and current aliases; query addresses with a read-only URI. Historical filenames and their aliases are not identities.
- Historical local JSON files are merged using exact 40-digit hex addresses and coin + trade ID. An economic conflict on a duplicate trade ID is quarantined, never silently overwritten. Archive pages and SHA records are immutable and private.
- Official Hyperliquid `/info` `userFillsByTime` historical reads are capped at 12 total calls, four pages per wallet, 3 seconds between requests, and five pre-identified missing wallets. The source generation is private and receipt-stamped. Those locally acquired pages **cannot restore the historical first-known follower clock** or whole-wallet NAV.
- Native market-day identity and SHA validation use `pm_offline_repository._market_day`, `native_instrument` and `VerifiedHyperliquidMinuteSource`. HIP-3 markets follow their DEX-specific `symbol=...` storage structure. Never substitute a different DEX, exchange or coin.
- Strict historical-oracle diagnostic: for each (wallet, market), take the first source fill, aggregate net quantity through its +1m/+2m/+5m delay cutoff, then model a strictly later minute-open order; apply the reference `w_i * min(.35,10000/E_i)` where `w_i=1/3`, and 3.5bps taker + 2.5bps adverse slippage **one way**. A single un-timestamped vendor equity scalar is *not* valid PIT follower sizing. The `$10` minimum is checked after reference scaling, not before. This is an unqualified fill-notional/market availability diagnostic, **not** a whole-wallet portfolio PnL computation.

## Verified acquisition and completeness checkpoint

On 2026-11-05 the live registry doctor passed SQLite integrity and recorded inventory SHA `3217b46450dcd4fe7b23c17079bf50eb99d585546002610e2e189779ef0f4bf8`. The target cohort has 66 distinct nonexcluded wallets.

| Measure | Result |
| --- | ---: |
| Initially matching raw-fill wallets across six local directories | 61 / 66 |
| Historical fill wallets after bounded official public recovery | 66 / 66 |
| Official `/info` requests | 9 |
| Paid HyperX requests | 0 |
| Newly acquired raw historical fills (five accounts) | 15,357 |
| Remaining source-ID conflicts | 1 (outside the two illustrative trios) |
| Diagnostic selected historical fills (six accounts) | 10,349 |
| Native (instrument, UTC date) pairs inspected | 347 |
| Missing / incomplete native market-day pairs before market repair | 27 |
| Missing / incomplete native market-day pairs after market repair | **3** |

Recovered raw fill counts: M20 1,552, M47 3,110, M11 1,742, M01 5,322 and M35 3,631. The owner-private immutable public source generation is `/home/quant/.local/share/copytrade/reports/ml4t66-public-fills-g20261105-01/`; its `report.json` SHA-256 is `91ac6800ff1c5f5a2c587e717d774c71f92fefb0b200a1ba4c50baf47819a9f5`.

The canonical `ml4t-data` native CHD writer filled previously missing ALGO (11,520 bars), OP (67,680 bars) and COMP (25,826 bars), 105,026 new one-minute bars across three batched symbol ranges. Per-day SHA sidecars were checked through the existing native verifier; the collector preserved existing partitions.

**Unresolved and fail-closed:** COMP 2026-10-16 and 2026-10-20 fall beyond the vendor's reconciled candle range; PONS 2026-08-31 is a SHA-valid **partial** 1,210-bar day, not a complete 1,440-bar session. No alternative/invented marks were substituted. The unqualified source TID conflict also requires independent reconciliation before reusing the affected wallet.

The six-wallet diagnostic after market recovery, using the historical first-event anchored model:

| Delay | Net-delta orders | Native-open scenario matches after $10 check | Missing-day instances | Partial-day instances | Below-$10 instances |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 minute | 1,091 | 1,064 | 4 | 3 | 20 |
| 2 minutes | 1,012 | 992 | 3 | 3 | 14 |
| 5 minutes | 924 | 907 | 3 | 3 | 11 |

The diagnostic cost totals and notional in the private report are *scenario only*. They are not independent follower-account realized costs or PnL, and do not include independently verified funding, source NAV or portfolio margin.

### SHA-pinned private evidence

- Historical official public recovery manifest: `91ac6800ff1c5f5a2c587e717d774c71f92fefb0b200a1ba4c50baf47819a9f5`.
- Latest six-wallet local source/native market report: `/home/quant/.local/share/copytrade/reports/ml4t66-batch-recovery-20261105/ml4t66_batch_audit_4f07c7e14eb45c83885b.json`, SHA-256 `4f07c7e14eb45c83885b9de2fd64d5bf4d5e5d8cbfaae3dfa8f16853c059e677`.

## Safe operator commands

Run from a clean isolated worktree at the recorded code revision:

```bash
uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev copytrade-pm capabilities show research.offline
uv run --frozen --group dev copytrade-pm capabilities show research.contract_selector

# Offline only: no external requests; emits new immutable private report.
uv run --frozen --extra market python -m copytrade_pm.pm_ml4t_batch_recovery \
  --db /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --source-root /home/quant/dev/copytrade-pm/data \
  --extra-source-dir /home/quant/.local/share/copytrade/reports/ml4t66-public-fills-g20261105-01/normalized \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --output-root /home/quant/.local/share/copytrade/reports/ml4t66-batch-recovery-20261105

# Collector below is a NETWORK MUTATION and its original generation cannot
# be reused. Run only after confirming newly missing wallets and choosing a
# distinct private --output-root; never replay against an existing generation.
# uv run --frozen --extra market python -m copytrade_pm.pm_ml4t_public_backfill \
#   --db /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
#   --source-root /home/quant/dev/copytrade-pm/data \
#   --output-root /home/quant/.local/share/copytrade/reports/NEW-PRIVATE-GENERATION \
#   --start-ms 1786060800000 --end-ms 1793836800000 --max-calls 12 \
#   --pages-per-wallet 3 --min-interval 3
```

The historical fill generation is deliberately **not** imported into the live SQLite portfolio registry, and neither sample trio is activated.

## Unresolved scientific gates

- Atomic parent/subaccount/DEX initial and continuing books, full hedge and collateral reconciliation.
- Point-in-time equity, funding, realized follower execution economics and first-local-observed signals.
- Complete native exact-minute markets and measured quote-side spread/depth/capacity, including the three unresolved days above.
- Independent sequential portfolio MTM through the rule-specific daily/trailing high-water state machine, out-of-sample/forward paper and matched controls.
- Native contract-selector `SCENARIO_ONLY` versus `BLOCKED` treatment; no synthesized return tape is an admissible qualified input.

Therefore both provisional 3-pod rosters remain `BLOCKED_ECONOMIC_EVIDENCE`, with contract pass odds, skew, funded payout EV and trading suitability **UNKNOWN**. `NO_AUTHORIZED_PURCHASE_RECOMMENDATION`.
