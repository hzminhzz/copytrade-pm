# Mandatory registry-first workflow for wallet and portfolio agents

**Mandatory source-sizing clarification (2026-11-06):** SQLite remains metadata authority, not source-NAV authority. New default fixed-k copytrading [requires selected source position scope and follower risk, **not leader whole-account NAV**](RISK-BUDGETED-K-SIZING-20261106.md). Do not stop agents or demand leader NAV unless the selected policy is explicitly `ALLOCATION_OVER_LIVE_NAV`. Continue registry signature/identity and actual operational/readiness gates independently.

**Owner-approved operating contract (2026-11-04).** Read this after `AGENTS.md` and before answering any question about **which wallets exist, are being evaluated, excluded, watched, or belong to a portfolio**, or which portfolios are **saved, selected, frozen, paper-running, or eligible for deployment**. Use this same procedure before implementing wallet/portfolio changes or documenting their operational state. OptMem and Markdown are navigation and dated decisions, **not** substitutes for the current indexed source.

## SQLite write authority and legacy freeze — 2026-11-05

`doctor` and `native status` inspect the SQLite registry first. The full SQLite `inventory_sha256` is the current version identity. `source_manifest_sha256` is historical evidence lineage; CSV/JSON/Markdown cannot replace current wallet/cohort/selection state. To enforce this across old writers, the explicit reviewed `native lock --apply` takes a private online backup and installs SQLite triggers. Once locked, use `native register` for new, separately versioned cohorts and a distinct protected `native exclude` for reviewed append-only exclusion decisions; never `sync --apply`. Exclusions must be registered-wallet-only, private SHA-pinned and known-at on receipt; no automatic revocation. Old frozen PM-01 evidence stays intact. Tracker subscriptions, paper NAV and authorization remain independent. [Full migration and rollback policy](SQLITE-NATIVE-LEGACY-LOCK-20261105.md).

## SQLite is metadata authority — 2026-11-05

The owner-private SQLite database governs current wallet/cohort/alias/exclusion
membership and versioned research portfolios. `doctor` must establish the
SQLite integrity/FK/schema state and `inventory_sha256`; last import-source SHA
and age are audit metadata, **not** an overriding roster. A later database-only
cohort remains registered even when missing from old CSVs. `doctor --legacy-audit`
may report `DRIFT`, `MATCHED_IMPORT_SUBSET` or `UNAVAILABLE` without
invalidating a structurally valid SQLite ledger. Cohorts using non-content-
addressed provenance labels remain `UNVERIFIED_IMPORT_LABEL`, which never
becomes scientific qualification. A pinned release must verify its actual
SQLite inventory and independent paper/no-trade invariants.

## Authority and meaning

| Question | Authoritative source to inspect | What it does **not** establish |
| --- | --- | --- |
| What was approved or frozen, and when? | Versioned, SHA-pinned Git decision JSON + `portfolio_versions` / `portfolio_seals` | A live paper worker or authorization |
| Which research portfolios are currently indexed? | Private SQLite `research_selections` through `portfolio --current`, with `selection_known_at` and source SHA | Current positions, enrollment, or executable sizing |
| Which wallet belongs to which selection/cohort? | `wallet --alias`, `cohort`, and `portfolio` through registry CLI, using qualified names and as-of | Whole source account equity, historical first-known identity, or followability |
| Which addresses are configured or subscribed? | Registry `status`/`doctor` bound to deployed tracker config and read-only subscriber source | `RUNTIME_ADMITTED` or complete healthy receipts |
| Is a paper portfolio actually operating? | Independent *real* paper-worker run manifest, verified journal, process and fresh source/market heartbeat; inspect `paper` and actual services | A saved registry row or synthetic HALT event is not `PAPER_RUNNING` |
| Is it economically qualified or authorized? | Independently verified mature matched follower/control economics, protected risk/review and explicit authorization | Vendor PnL, model k, passing tests, registry alias mapping or a paper-only release |

The Git decision is the **immutable evidence/decision provenance**; the owner-private SQLite registry is the **authoritative indexed metadata ledger** for imported and directly registered decisions, cohorts and monitoring inventory. A read model does not own financial journals, broker orders or subscriptions. The real service/financial system remains the authority for its own operation. Always separate observed facts from inferred or unknown status.

## Required read-only sequence

First discover the matching owner with `copytrade-pm capabilities show
portfolio.current` or `copytrade-pm capabilities show wallet.lookup` and
[the agent-native guide](AGENT-NATIVE-OPERATIONS.md). Unified queries do not
replace the independent registry `doctor`, release or paper-worker checks.
Use `copytrade-pm wallets list --query W083 --asof <UTC>` for a bounded,
address-redacted inventory query; its local wallet IDs are not durable
identities, and monitored/subscribed flags are current-snapshot observations.
Use `copytrade-pm research list --cache-root PRIVATE_CACHE` only for
SHA-verified canonical Polars job reports; this is not a general research
ledger. The `copytrade-pm health` adapter now delegates installed release
verification and OS unit queries but does not establish protected trading
readiness. For agent performance claims, see the independently captured
[host trace benchmark](AGENT-TRACE-EVAL-20261105.md); normal CLI tests and
ChatGPT-written transcripts are not empirical tool-choice evidence.


From a clean checkout or an isolated worktree of `hzminhzz/copytrade-pm`, compare the actual Git revision with the remote before trusting code or a dated note:

```bash
git status --short --branch
git fetch origin main
git rev-parse HEAD origin/main

# Source generation and index health: verify *before* relying on answers.
uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev copytrade-wallet-registry status
uv run --frozen --group dev python scripts/registry_release.py verify

# Which portfolios are selected for NEW research, not which ones are running?
uv run --frozen --group dev copytrade-wallet-registry portfolio --current

# Frozen and namespace-qualified portfolios; do not treat a bare B as unique.
uv run --frozen --group dev copytrade-wallet-registry portfolio P1
uv run --frozen --group dev copytrade-wallet-registry portfolio gemini.phase4/E6
uv run --frozen --group dev copytrade-wallet-registry portfolio q3/B
uv run --frozen --group dev copytrade-wallet-registry portfolio gemini.phase5/B

# Wallet identity and membership; substitute the requested actual alias.
uv run --frozen --group dev copytrade-wallet-registry wallet --alias W083
uv run --frozen --group dev copytrade-wallet-registry cohort research-108
uv run --frozen --group dev copytrade-wallet-registry cohort nansen-20
uv run --frozen --group dev copytrade-wallet-registry cohort hyperx-30

# Separate evidence: indexed paper observation and qualification.
uv run --frozen --group dev copytrade-wallet-registry paper
uv run --frozen --group dev copytrade-wallet-registry qualification
```

Use `portfolio <canonical-name> --asof <UTC-offset-timestamp>` or `wallet --alias <alias> --asof <UTC-offset-timestamp>` for a point-in-time question; the requested cutoff must be **when the system knew the identity/selection**, not a retrospective vendor fill date. The `portfolio` command without a name lists saved sealed definitions; `portfolio --current` lists the **approved new-study research selection**. They are not synonymous. Names like `q3/B` and `gemini.phase5/B` refer to distinct portfolios; ambiguous `B` must fail closed.

For actual operational claims, check independent status/provenance beyond this list:

```bash
systemctl --user show copytrade-tracker.service copytrade-source-abc.service \
  copytrade-ensemble.service copytrade-paper-p1.service copytrade-paper-p14.service \
  -p Id -p LoadState -p ActiveState -p MainPID --no-pager
```

A missing paper unit or zero indexed runs does **not** prove that no independent external program exists. It does mean there is no authoritative verified `PAPER_RUNNING` state from those sources. Never infer `PAPER_RUNNING_OBSERVED` from a proposal, directory, PID string, stale heartbeat, or synthetic test.

## Fail-closed conditions

1. **Registry unavailable or not imported:** report the requested live status as `UNKNOWN` or `NOT_REGISTERED_AT_ASOF` as appropriate; cite the last versioned Git decision with its known-at timestamp and explicitly label it *historical*, not current. Do not guess from OptMem, Telegram messages, wallet filenames or narrative reports.
2. **`doctor` reports `database_integrity=FAILED`:** do not trust any indexed membership. Legacy parity differences alone do not invalidate SQLite metadata. Preserve the observed SHA and compare with `sync --dry-run` only; follow the [registry release/rollback runbook](WALLET-REGISTRY-RELEASE-RUNBOOK.md) and obtain reviewed private backup/source lineage before any `sync --apply` or release activation. These commands are **writes**, not ordinary inspection.
3. **Wallet alias absent, colliding, or incomplete:** report unresolved. A generic display name such as `HL Perps Whale` is not a unique identity. Do not silently map a source wallet to a different portfolio or copy a member between frozen versions.
4. **Historical frozen membership:** never backfill an older `portfolio_memberships.wallet_id` in place from later alias evidence. Resolve `wallet_aliases` at the actual as-of cutoff; if the binding was first known *after* the original P1/P14 v2 seal, it is **post-seal and blocked for that historical decision** even if the address matches now. Mainline safety fix [PR #91](https://github.com/hzminhzz/copytrade-pm/pull/91), merge `e5d9933`, prevents future retroactive writes. Historical records previously touched by the older release need a separately reviewed, backed-up, versioned repair, not a silent fix.
5. **Research priority versus paper baseline:** Gemini V2 `gemini.phase4/E6` primary and `gemini.phase4/E2` challenger are new-research choices. Sealed `P1`/`P14` Forward-Paper engineering baselines are different contracts; V2 never replaces their run SHA, source wallet equity, risk policy, account identity or first-known clock. The comparison policy is not authorization to launch a worker.
6. **Promotion:** `alias_resolution_complete=true` is indexed identity resolution **only**. Keep `RUNTIME_ADMITTED`, source receipt health, `SCIENTIFICALLY_QUALIFIED`, `TRADING_AUTHORIZED`, `DEPLOYED`, and `PAPER_RUNNING` separate. Unknown independent source NAV, collateral, subaccounts, tradable volume, HIP-3 session or matched economics implies no positive promotion.

## Historical integration and installed-release checkpoint

- The source foundation from old draft [PR #57](https://github.com/hzminhzz/copytrade-pm/pull/57) was incorporated into mainline commit `5d7b4d7` (research catalog integration #79); **#57 was closed as superseded, not merged**.
- Focused frozen-membership safety [PR #91](https://github.com/hzminhzz/copytrade-pm/pull/91) merged to `main` as `e5d9933`.
- Forward-Paper [PR #73](https://github.com/hzminhzz/copytrade-pm/pull/73) was reconciled on top of `e5d9933` at `47f0730` and remained **draft** at the 2026-11-04 checkpoint. Check GitHub again; this is not an evergreen PR status.
- At the verified 2026-11-04 09:36:57 UTC generation, registry `doctor` reported `CURRENT` / `counts_match=true`, **264 configured / 264 subscribed, 158 research, 22 exclusions and 11 source-sealed definitions**, SHA `e2836aab5ef6ef79306e9dfe732d8768c3b1ca6af29efbda066b37f03646a18f`. The installed *registry-only* pinned read-only release still reported `5d7b4d7`, **not** `e5d9933`. No protected P1/P14 worker was verified. These are historical observations; always rerun the commands.
- Code merge, installed read-only registry release, verified paper-worker deployment, science qualification and broker authorization are **separate gates**. Never silently upgrade a status because GitHub CI is green.

## Mandatory agent closeout and OptMem discipline

Before answering or modifying a wallet/portfolio decision, report the **queried Git HEAD/main**, **source generation SHA and observed-at**, **selection version/known-at**, and the **exact independently evidenced state**. If any necessary evidence is unavailable, state `UNKNOWN` with the missing authority; do not fill it from recollection.

Agents must run `~/.optmem/memo wake` as directed by `AGENTS.md`, read **this workflow**, then use live registry/Git/release/worker sources. On a durable policy or workflow change, `~/.optmem/memo note "<max-280-byte summary and canonical doc path>"`; complete `memo nap` if prompted. OptMem preserves the **instruction to recheck**, not a live wallet count, stale PR SHA, source identity or acceptance verdict. Never edit `~/.optmem/memory` directly.

Changes to this contract must update `AGENTS.md`, [INDEX](INDEX.md), the [operator runbook](RUNBOOK.md), tests and the registry documentation audit in the same PR. Keep source and financial data private; never commit the private SQLite registry, raw wallet addresses, credentials, chats, account IDs or subscriber records.
