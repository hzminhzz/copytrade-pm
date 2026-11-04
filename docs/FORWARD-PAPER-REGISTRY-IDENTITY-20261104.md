# P1 / P14 identity reconciliation — 2026-11-04

**Read-only source-to-registry audit. No registry mutation, no paper admission.**

At current frozen registry version **2**, P1 lists exactly three and P14 exactly five aliases. Their owner-private source filenames and recorded full public wallet addresses agree with the `wallets` identity table for all five unique members, but all P1/P14 membership rows still have `wallet_id=NULL`. The historical wallet-address locator is NOT independently validated first-known wallet NAV and MUST NOT promote a source to a prospective paper trader.

| Frozen portfolio | Members | Registry address found | Frozen `wallet_id` resolved | Status |
| --- | ---: | ---: | ---: | --- |
| P1 (version 2) | 3 | 3/3 | **0/3** | BLOCKED |
| P14 (version 2) | 5 | 5/5 | **0/5** | BLOCKED |

Identity source: `wallet_registry.sqlite` is opened with SQLite URI `mode=ro` and query-only. Private source locator reads local `wallet_fills_90d` and `nansen_smart_money_fills_90d` files strictly for their stored `address` field and file SHA; it never fetches historical fills. Reports contain aliases, address SHA-256 and file SHA-256, never raw wallet addresses. A conflicting `wallet_id`, historical filename-vs-content mismatch, duplicate native addresses, missing or changed frozen membership, or missing sealed portfolio version fails closed.

Reproduce from the canonical `dev/copytrade-pm` checkout:

```bash
uv run --group dev copytrade-pm-paper-registry-audit \
 --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
 --primary-dir /home/quant/dev/copytrade-pm/data/wallet_fills_90d \
 --secondary-dir /home/quant/dev/copytrade-pm/data/nansen_smart_money_fills_90d \
 --portfolio P1
```

Run again with `--portfolio P14` for the challenger. The CLI is intentionally read-only. **Action needed in wallet-registry WR-06/PR #57:** independently verify the native identity chain, then seal the authoritative alias->wallet-id binding as a new, audited registry generation/version rather than overwriting frozen version 2 or mutating the live database in-place. This belongs to the registry owner and requires evidence, not an implicit FP workaround.

Separately, bounded official public `allDexsClearinghouseState` capture produced 3 account-scope receipts each for S035/S051/S053/S064 and 2 for the Whale candidate. None proves simultaneous whole-wallet account NAV; all remain BLOCKED with `source_equity=None`. The parent-only observations and private receipt hashes are in `/home/quant/dev/copytrade-pm/data/private/paper_scope_observations_20261104`. No paper fills, orders or scientific claims.
