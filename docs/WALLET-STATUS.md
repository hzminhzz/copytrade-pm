# Wallet research, monitoring and paper-run status

**Live answer protocol:** [mandatory registry-first agent workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md). This page below contains a historical source generation and must **never** override a current `copytrade-wallet-registry doctor`, `status`, `portfolio --current`, and independently verified paper-worker evidence. A newer versioned selection is not a running or authorized account.

**Dated v7 source cut.** The research catalog adds Gemini E6/E2/E3/Phase-5-B under namespace-qualified IDs and preserves the original seven frozen portfolio definitions. For a current query use `copytrade-wallet-registry portfolio --current` and inspect its `selection_known_at`, data-generation SHA and alias-resolution status; read [Gemini Portfolio Freeze V2](decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.md). A newer selection changes **new-study priority only**, not the running paper worker, tracker admission or scientific status.

**Verified source cut: 2026-11-04 09:36:57 UTC.** This is a **dated redacted snapshot**, not a perpetual live claim. Re-run `copytrade-wallet-registry doctor` and `status` against the **owner-private SQLite registry** before taking operational action. If the source SHA or freshness differs, this page is stale and must be refreshed through a reviewed update.

The authoritative files remain private under `/home/quant/.local/share/copytrade/`. Never publish raw addresses, subscriber chat IDs, account IDs, credentials or the SQLite database to Git.

| Independent predicate | Verified state | Interpretation |
| --- | --- | --- |
| RESEARCH_UNIVERSE | **158** (108 baseline + 20 Nansen + 30 HyperX) | Research candidates; **not** subscriptions |
| OWNER_REJECTED | **22** (14 short-span, 5 underwater, 3 passive makers) | Intentionally excluded owner identities, source SHA `06b90eed43ce...` |
| RESEARCH vs REJECTED | **0** overlap | Current research universe excludes all 22 rejected addresses |
| CONFIGURED_FOR_OBSERVATION | **264** | Desired addresses in deployed tracker configuration only |
| SUBSCRIBED | **264** | Distinct subscriber SQLite addresses only; no chat IDs exported |
| RESEARCH vs CONFIGURED | **131** overlap | This does not prove runtime admission |
| RESEARCH vs SUBSCRIBED | **131** overlap | This does not prove healthy receipts |
| RUNTIME_ADMITTED | **UNKNOWN** | Outbox activity is not an authoritative admission decision |
| SOURCE_RECEIPT_HEALTHY | **UNKNOWN** | Missing signed continuous receipt/coverage evidence |
| SHA-SEALED PORTFOLIO DEFINITIONS | **11** (seven historical, four additional Gemini research definitions) | Verified Git-source-backed selections, not running workers |
| REGISTERED PAPER RUNS | **0** at source inspection | No registered publisher; absence does **not** mean no external paper program runs |
| GLOBAL PAPER/DEMO RUNNING | **UNKNOWN** | Needs independently produced current manifest, worker, journal and heartbeats |
| SCIENTIFICALLY_QUALIFIED | **NOT ESTABLISHED** | No independently signed follower/control economics qualification; v5 database guards reject positive verdict writes |
| TRADING_AUTHORIZED | **NOT ESTABLISHED** | Neither registry status nor test passes grant trading risk |

Private source-manifest hash at this cut: `e2836aab5ef6ef79306e9dfe732d8768c3b1ca6af29efbda066b37f03646a18f`.

Earlier **v6 historical cut (2026-11-04 03:22:31 UTC):** 215 configured, 150 subscribed, research overlaps 19/9, seven sealed definitions; historical manifest SHA `562750974cc7f3746483c9bbaab38c1294c87f970acea2584f6c59ca88684202`. Keep this distinct from the newer v7 materialized registry. At the v7 cut, the on-demand registry-only release was pinned to `5d7b4d7` even though source hotfix #91 (`e5d9933`) had merged into Git `main`; there was no automatic release upgrade. Existing P1/P14 historical member-ID retrofills must not be treated as first-known source identity evidence. The read-only FP audit treats affected P1/P14 IDs as BLOCKED for the original selection; reviewed recovery is required before worker admission.

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

Reference: [WR-01–WR-12 acceptance matrix](WALLET-REGISTRY-ACCEPTANCE-20261104.md), [registry operational checkpoint](WALLET-REGISTRY-STATUS-20261104.md), [portfolio/run contract](WALLET-REGISTRY-PAPER-CONTRACT-20261104.md), [adoption plan](WALLET-REGISTRY-SQLITE-ADOPTION-PLAN-20261104.md). The original registry foundation in draft PR #57 was superseded by mainline `5d7b4d7` (#79); PR #57 was **closed without merging**. Source-only frozen-membership PIT hotfix PR #91 was merged as `e5d9933`, but the last observed pinned registry release was still `5d7b4d7`. Do not infer deployment from a Git merge. Tickets #44–#55 retain their independent acceptance, paper-health and scientific authorization gates; recheck Git and the installed release.
