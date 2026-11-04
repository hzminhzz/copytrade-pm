# Wallet registry to paper-runtime boundary — engineering contract

**2026-11-04 status:** standalone read-only metadata registry at `5d7b4d7` is active and verified; the registry's *paper-runtime observer* is still a private, synthetic-tested read-only journal adapter. **No protected P1/P14 paper worker is installed or registered.** This is not a paper-worker activation, live/demo broker integration or scientific qualification. FP-10 issue #67 remains open.

## Mainline V2 catalog and frozen P1/P14 boundary (2026-11-04)

The newer mainline `wallet_registry_catalog` (SQLite v7, merged by `5d7b4d7`, PR #79) supersedes the older draft PR #57 CLI overlay. Its only canonical new-study query is `copytrade-wallet-registry portfolio --current`; it exposes **E6 primary, E2 challenger, P1 incumbent and P14 archived** with separate SHA-sealed versioned research IDs. It does **not** promote a new paper worker, replace P1/P14 frozen run hashes, or authorize trading. Live registry `doctor` now matches 264 configured/264 subscribed, 158 research, 22 excluded and 11 sealed portfolio definitions at source manifest `e2836aab...`; the on-demand registry-only pinned read-only release is verified at `5d7b4d7`. Do not confuse this with an installed protected FP worker.

**Version-2 integrity warning:** the current mainline importer has a retroactive NULL-`wallet_id` assignment path in historical frozen portfolio membership. It has already executed during the newer private registry generation. Although matching native addresses exist, later Phase-4 alias evidence cannot be reclassified as known on the original historical seal date. FP PR #73 repairs this path *in its integration branch* and checks true first-known alias chronology against the original seal: **P1 3/3, P14 5/5 are post-seal bindings**, not proof of frozen PIT identity. The read-only FP registry audit therefore reports `BLOCKED` and no paper admission; it never rewrites the live registry to pretend otherwise. A separate reviewed source-of-truth migration is required before any protected paper cutover.

Read-only cross-program contract:

```bash
uv run --group dev copytrade-wallet-registry portfolio --current
uv run --group dev python scripts/verify_wr_fp_journal_contract.py \
  --fp-worktree /home/quant/.devspace/worktrees/copytrade-pm-569e8bef \
  --audit-native-source --portfolio P1 \
  --primary-dir /home/quant/dev/copytrade-pm/data/wallet_fills_90d \
  --secondary-dir /home/quant/dev/copytrade-pm/data/nansen_smart_money_fills_90d
```

This live private census checks roster/selection SHA/version and side-effect absence, **not** future-first-known full account NAV or trading capacity. No private source material is committed.

## Registry v7 frozen-member as-of correction (2026-11-04)

After the mainline research-catalog integration at `5d7b4d7`, a code audit found that `wallet_registry.apply()` **retroactively replaced NULL `portfolio_memberships.wallet_id` values in existing P1/P14 v2 sealed selections** using Phase-4 aliases first known on 2026-11-04, after the original November 2 selection seal. A matching address is not proof the alias was known to the follower at that older selection time. The active private registry-only release was already observed with those retrofilled rows. No evidence is backdated, no historical fill is reinterpreted as prospective, and this change does **not** reverse a production DB mutation.

The corrective patch removes the cross-version `UPDATE portfolio_memberships` entirely. The registry now resolves source wallet aliases through `wallet_aliases` at the *requested as-of cutoff* without rewriting any frozen membership. It rejects conflicting preassigned and observed IDs. New V2 portfolio versions continue to be created by the existing approved `research_selections` schema. A regression reproduces the old defect in a temporary v1->v2->v7 SQLite upgrade and verifies that all original frozen IDs remain NULL while new as-of alias lookups work, early as-of lookups remain unresolved, the same import is idempotent, and status/authorization remain research-only. This is an engineering fix, **not** a scientific wallet-identity attestation or permission to repair private v2 rows without a separate reviewed migration and rollback record.

Current new-study priority is still E6 primary / E2 challenger via `copytrade-wallet-registry portfolio --current`. P1/P14 remain independently frozen FP-09 engineering baselines, not equivalent to prospective paper admission. Protected paper workers remain undeployed.

## WR-06 — versioned research portfolio selections

A registry source migration imports seven **SHA-sealed** decision declarations from reviewed Git document versions:

| Portfolio | Contract | Status |
| --- | --- | --- |
| P1 | S035-ENA / S051-BTC / S053-HYPE, virtual $10,000, combined nominal budget $600 | PAPER_RESEARCH_PRIMARY, **not running** |
| P14 | P1 trio + S064-xyz:BRENTOIL + Whale_0x5f94, virtual $10,000, **same** nominal $600 budget | PAPER_RESEARCH_CHALLENGER, **not running** |
| P16 | P1 trio + Whale_0x5f94, illustrative $600 total | OPTIONAL_CONTROL |
| A/B/C | Frozen historical three-wallet research configurations | HISTORICAL_RESEARCH_ONLY |
| Combo2 | W028, CA-008, W015, hypothetical $5,000 paper account | PAPER_RESEARCH_EXPERIMENT |

Selection source: the reviewed document's exact bytes SHA-256, immutable Git revision and a conservative observed Git commit date. Current changes to a selected source document fail closed until a new, approved version is pinned. The selection contract JSON is hashed canonically as `wallet_portfolio_definition_v1`. Source alias-to-address resolution is **different from** independently verified account-book and trader-identity proof; P1/P14 have unresolved source identities here and no trade authorization. A legacy unsealed v1 entry never provides a SHA for a paper run.

Query e.g.:

```bash
uv run --group dev copytrade-wallet-registry portfolio P1
uv run --group dev copytrade-wallet-registry portfolio P14 --asof 2026-11-02T00:00:00+00:00
```

Do **not** infer active workers from these selection records. Keep paper source wallets, current source equity, subaccount book and PM03 risk in their separate authorities.

## WR-07 — FP journal interoperability (partial FP-10)

**Resolved for journal identity and accounting separation (2026-11-04):** the
registry now natively reads FP draft PR #73's authoritative owner-private
`paper-events.sqlite3` using SQLite `mode=ro` and `query_only`. It does not
rewrite FP's `paper_run_manifest_v1`, import its financial writer module, or
substitute an `events.jsonl` journal.

| Source | Exact FP authority | Registry read-only interpretation |
| --- | --- | --- |
| Selection | FP `PaperPortfolioView` requires `portfolio_sha` = `FrozenPaperPortfolio.sha` (`frozen_paper_portfolio_v1`) | Registry recomputes that **distinct FP SHA** and compares it to FP manifest, then binds the exact approved P1/P14 aliases, $600 total nominal risk and source-known time to a **separate WR-06 `wallet_portfolio_definition_v1` SHA**; no wallet-address identity assumption |
| Manifest | `run_id`, `account_id`, policy/release/market SHA, `selected_at`, `started_at`, paper-only route | Canonical JSON digest must equal FP `runs.manifest_sha`; account and clocks validated, raw account redacted |
| Finance | PM-03 `Account` and private WAL/FULL `PaperJournal`, tables `runs` and `events` | `runs.snapshot_sha`, cursor, last event time and bounded recent event chain checked; **not** a full independent economic replay |
| Worker | FP `PaperCampaign.status` currently reports `worker_status=NOT_RUNNING`, `admission=BLOCKED`; no durable heartbeat producer | Native journal observations are **NOT_RUNNING** (`FP_JOURNAL_ONLY_WORKER_UNVERIFIED`) even if events exist. No healthy/active worker claim |
| Ownership | FP journal owns real paper-account state; registry is metadata | Registry writes only to its own private index on explicit `paper --apply` and cannot alter cursor, cash, HALT, position or P&L |

The actual FP `FrozenPaperPortfolio` + `PaperPortfolioView` +
`PaperCampaign` + `PaperJournal` integration was exercised against
FP PR #73 commit `8a6ee5e` for **both P1 and P14**. Each completely
synthetic $10k portfolio registered through FP's own SHA gate and committed
a test HALT event. WR independently checked the canonical FP manifest SHA,
its own distinct source-known definition SHA, the exact explicit alias bridge,
cursor 1 and the recent event hash chain, returning **NOT_RUNNING**.
All source database bytes remained unchanged during the read; no synthetic
run was indexed in the owner-private live registry. Neither exercise proves
source account completeness, genuine prospective evidence or future alpha.

**Later FP-11 negative-status cross-check (2026-11-04):** the same P1 and
P14 synthetic journals were checked against the current FP
`paper_operator_status_v1` implementation. Before HALT, its private
read-only report was `NOT_RUNNING`; after a committed synthetic PM03 HALT,
it reported `HALT`. In both states `real_worker_evidence=false` and
`paper_admitted=false`, while WR's journal-only liveness stayed
`NOT_RUNNING`. The FP worktree was otherwise dirty with parallel source
research: the six journal/status contract modules were checked unchanged
relative to its current HEAD, but this is still a local smoke, not a
deployed independent worker publisher.

Reproduce this cross-branch contract (requires an FP branch checkout):

```bash
uv run --group dev python scripts/verify_wr_fp_journal_contract.py \
  --fp-worktree /home/quant/.devspace/worktrees/copytrade-pm-569e8bef \
  --portfolio P1
uv run --group dev python scripts/verify_wr_fp_journal_contract.py \
  --fp-worktree /home/quant/.devspace/worktrees/copytrade-pm-569e8bef \
  --portfolio P14
```

```bash
# Canonical FP source. Explicit portfolio choice prevents guessed identity:
uv run --group dev copytrade-wallet-registry paper \
  --portfolio P1 --run-id <existing-run-id> \
  --run-dir /owner-private/forward-paper/run-root

# Only after separate operator review: index an already-existing FP run in
# the owner-private inventory. NO writes to FP, tracker or broker.
uv run --group dev copytrade-wallet-registry paper \
  --portfolio P1 --run-id <existing-run-id> \
  --run-dir /owner-private/forward-paper/run-root --apply
```

A missing/stale/unsafe source, inconsistent **FP and WR** portfolio SHAs, mismatched P1/P14 aliases/risk, unreconciled event
clock, changed account identity, or event chain/hash defect fails closed to
UNKNOWN. Reports expose only redacted identities and hashes, never raw
account names or journal paths. The observer scans at most 64 recent events
per run and explicitly labels this **bounded hash-tail validation**, not
full journal replay or certified economics. A run with no verified worker
heartbeat remains NOT_RUNNING regardless of its historical cursor.

**FP-10 remains partly open:** FP-09/FP-11 must establish the real independent
paper worker and a durable status/heartbeat publisher (including transport
and quote freshness). Only then may the registry consume the authoritative
worker status and independently confirm `PAPER_RUNNING_OBSERVED`. Without it,
`global_running_count=UNKNOWN` and no scientific qualification or trade
authorization is possible. Work proceeds in separate WR and FP branches.


**Deprecated prototype removed:** the earlier `manifest.json` +
`status.json` + `events.jsonl` v1 path was never an FP financial journal.
It is now rejected (`UNSUPPORTED_LEGACY_PROJECTION_OR_MISSING_JOURNAL`)
even if it claims a recent heartbeat and RUNNING. The canonical FP SQLite
journal is the only supported source for this reader. A later independent
worker-status publisher must specify its own reconciled versioned projection;
do not reuse these incompatible prototype fields as though they were FP v1.

`paper` re-reads the private SQLite source at every query (bounded to 500
registered runs), compares indexed manifest/account/journal identities and
fails closed when they drift. It does **not** query or alter paper journal
financial state outside read-only indexed rows. Zero registered runs means
`global_running_count=UNKNOWN`, not proof that no independently managed
paper programs exist.

## Boundaries still open

- FP-10 (#67) has a **verified journal/portfolio SHA read-only adapter** against the actual FP-02 writer implementation, but still needs genuine supervised worker-status/transport/quote heartbeat publication and an isolation test under registry outage. There is no live/demo provider deployment from this change.
- WR-08 (#51) has a [signed negative-only evidence importer](WALLET-REGISTRY-SIGNED-NEGATIVE-EVIDENCE-20261104.md); independently verified *positive* scientific attestation remains unavailable; no prospective matched outcome is imported, and `SCIENTIFICALLY_QUALIFIED` remains NOT_ESTABLISHED. SQLite v5 triggers now restrict research verdict writes to `UNQUALIFIED`, `BLOCKED` or `NOT_ESTABLISHED`, preventing any unreviewed positive/authorized promotion through this inventory. A verified signoff producer is still unavailable.
- WR-10/11 require full independent fault matrix, backup/restore and controlled activation signoff. A successful fixture/mock status is **engineering** evidence only.
- Any production order route is out of scope and rejected by this paper-only contract.
