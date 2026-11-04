# Wallet research, monitoring and paper-run status

**Verified source cut: 2026-11-04 03:22:31 UTC.** This is a **dated redacted snapshot**, not a live claim. Re-run `copytrade-wallet-registry doctor` and `status` against the **owner-private SQLite registry** before taking operational action. If the source SHA or freshness differs, this page is stale and must be refreshed through a reviewed update.

The authoritative files remain private under `/home/quant/.local/share/copytrade/`. Never publish raw addresses, subscriber chat IDs, account IDs, credentials or the SQLite database to Git.

| Independent predicate | Verified state | Interpretation |
| --- | --- | --- |
| RESEARCH_UNIVERSE | **158** (108 baseline + 20 Nansen + 30 HyperX) | Research candidates; **not** subscriptions |
| OWNER_REJECTED | **22** (14 short-span, 5 underwater, 3 passive makers) | Intentionally excluded owner identities, source SHA `06b90eed43ce...` |
| RESEARCH vs REJECTED | **0** overlap | Current research universe excludes all 22 rejected addresses |
| CONFIGURED_FOR_OBSERVATION | **215** | Desired addresses in deployed tracker configuration only |
| SUBSCRIBED | **150** | Distinct subscriber SQLite addresses only; no chat IDs exported |
| RESEARCH vs CONFIGURED | **19** overlap | This does not prove runtime admission |
| RESEARCH vs SUBSCRIBED | **9** overlap | This does not prove healthy receipts |
| RUNTIME_ADMITTED | **UNKNOWN** | Outbox activity is not an authoritative admission decision |
| SOURCE_RECEIPT_HEALTHY | **UNKNOWN** | Missing signed continuous receipt/coverage evidence |
| SHA-SEALED PORTFOLIO DEFINITIONS | **7** (P1, P14, P16, A, B, C, Combo2) | Verified Git-source-backed selections, not running workers |
| REGISTERED PAPER RUNS | **0** at source inspection | No registered publisher; absence does **not** mean no external paper program runs |
| GLOBAL PAPER/DEMO RUNNING | **UNKNOWN** | Needs independently produced current manifest, worker, journal and heartbeats |
| SCIENTIFICALLY_QUALIFIED | **NOT ESTABLISHED** | No independently signed follower/control economics qualification |
| TRADING_AUTHORIZED | **NOT ESTABLISHED** | Neither registry status nor test passes grant trading risk |

Private source-manifest hash at this cut: `562750974cc7f3746483c9bbaab38c1294c87f970acea2584f6c59ca88684202`.

The 50 newly acquired wallets have **113,273 vendor fill records, 1,196 vendor-listed pairs and 1,197 pages** with independent source/integrity SHA references. That is **historical vendor** coverage, not a complete source account, prospective first-known receipt, independent follower economics or science qualification.

## Inspect, diagnose, and safely refresh

```bash
# From the copytrade-pm registry feature worktree.
uv run --group dev copytrade-wallet-registry doctor
uv run --group dev copytrade-wallet-registry status
uv run --group dev copytrade-wallet-registry portfolio P1
uv run --group dev copytrade-wallet-registry paper
uv run --group dev copytrade-wallet-registry sync --dry-run
```

An explicit `sync --apply` affects **only** the new private SQLite inventory; it requires a private backup and reviewed source drift. The paper observer never writes to a publisher's journal or any connector. No additional tracker subscriptions, production source changes, broker order routes, qualified managers or active paper workers are established by these commands.

Reference: [registry operational checkpoint](WALLET-REGISTRY-STATUS-20261104.md), [portfolio/run contract](WALLET-REGISTRY-PAPER-CONTRACT-20261104.md), [adoption plan](WALLET-REGISTRY-SQLITE-ADOPTION-PLAN-20261104.md). Current implementation is staged in **draft PR #57**, tickets #44–#55 remain subject to their actual acceptance and scientific authorization gates.
