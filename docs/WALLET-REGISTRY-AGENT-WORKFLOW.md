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

## Scoped read-only sequence

Registry-first means establish metadata from its owner. It does not mean read every service or financial journal for every task. For code/documentation-only work, inspect contracts without accessing private runtime data unless the requested claim requires it.

1. Inspect the actual repository/revision and task owner. Discover `portfolio.current` or `wallet.lookup` through `copytrade-pm capabilities show <id>`; read [agent operations](AGENT-NATIVE-OPERATIONS.md), including the documented facade limitations.
2. For an authorized metadata question, use native `doctor` to establish SQLite integrity and inventory identity, then the narrow wallet/cohort/portfolio reader. Use `native status` when writer-lock/native metadata state matters.
3. Assess the requested selection's proof independently. Doctor exit 2 with verified database integrity and blocked research-selection proof is not physical corruption. Unrelated independently valid historical lookups may continue.
4. Add release/process, source or finance checks only for the corresponding deployment, continuity or financial claim. Each has its own authority and authorized read scope.
5. Report the resolved identity, known-at, inventory/proof identity and actual limitations. Preserve absent or conflicted evidence as unknown.

Use the existing environment; do not implicitly install packages or widen data access. Check `--help` against the exact revision. Examples are alternatives selected by the task, not a script to run in full:

```bash
git status --short --branch
git rev-parse HEAD

# Metadata integrity and native state.
copytrade-wallet-registry doctor
copytrade-wallet-registry native status

# Resolve one actual requested identity or selection.
copytrade-wallet-registry portfolio --current
copytrade-wallet-registry portfolio q3/B --asof <UTC-offset-timestamp>
copytrade-wallet-registry wallet --alias W083 --asof <UTC-offset-timestamp>
copytrade-wallet-registry cohort research-108

# Aggregate registry status (broader: includes monitoring/paper summary; prefer doctor + scoped readers above for metadata-only lookups).
copytrade-wallet-registry status
```

Use the cutoff when this system knew the identity/selection, not a retrospective fill date. `portfolio` lists saved sealed definitions; `portfolio --current` lists research selections. Neither establishes running portfolios. `q3/B` and `gemini.phase5/B` are distinct; ambiguous bare names fail closed.

**Facade limitation:** at the reviewed baseline, unified registry reads can mislabel VERIFIED metadata as STALE, and aggregate doctor can misclassify a selection-proof block as integrity failure. Generation lookup reaches broad `status`, which can inspect paper runtime. For metadata-only or privacy-restricted tasks, use the native scoped readers above and preserve their separate fields. [D1](AGENT-SYSTEM-DESIGN.md#d1--truthful-registry-diagnostics) plans the correction; this document does not implement it.

| Additional claim | Required evidence branch |
| --- | --- |
| Monitoring/subscription snapshot | Native metadata (`copytrade-wallet-registry status` when monitoring scope is authorized) plus the explicitly authorized tracker/subscriber source; not a reconstructed historical series |
| Installed registry release | `python scripts/registry_release.py verify`; registry-only scope |
| Running application release | Actual manager/unit and independently bound process/release identity; configured ExecStart and PID existence alone are insufficient |
| Source continuity or market freshness | Original scope-bound source/quote receipts and their clocks |
| Paper operating/economics | Requested run manifest, independently replayed paper journal, actual worker/source/market evidence |
| Economic/scientific qualification or trading | Independent matched follower evidence and the appropriate protected authority |

Use `copytrade-pm wallets list --query W083 --asof <UTC>` only within its documented read scope and current facade limitations. It is bounded/address-redacted; local wallet IDs are not durable across generations. `research list --cache-root PRIVATE_CACHE` indexes only verified canonical job reports. Aggregate `status`/`health` are broader diagnostics, not prerequisites for a narrow lookup.

A missing known paper unit or zero indexed runs means no verified PAPER_RUNNING from those sources; it does not prove every possible external program is absent. Never infer paper health from a proposal, directory, PID string, stale heartbeat or synthetic test. For agent performance, use [independent host traces](AGENT-TRACE-EVAL-20261105.md), not a model-authored transcript.

## Fail-closed conditions

1. **Registry unavailable or not imported:** report the requested live status as `UNKNOWN` or `NOT_REGISTERED_AT_ASOF` as appropriate; cite the last versioned Git decision with its known-at timestamp and explicitly label it *historical*, not current. Do not guess from OptMem, Telegram messages, wallet filenames or narrative reports.
2. **`doctor` reports `database_integrity=FAILED`:** do not trust any indexed membership. Legacy parity differences alone do not invalidate SQLite metadata. Preserve the observed SHA and compare with `sync --dry-run` only; follow the [registry release/rollback runbook](WALLET-REGISTRY-RELEASE-RUNBOOK.md) and obtain reviewed private backup/source lineage before any `sync --apply` or release activation. These commands are **writes**, not ordinary inspection.
3. **Wallet alias absent, colliding, or incomplete:** report unresolved. A generic display name such as `HL Perps Whale` is not a unique identity. Do not silently map a source wallet to a different portfolio or copy a member between frozen versions.
4. **Historical frozen membership:** never backfill an older `portfolio_memberships.wallet_id` in place from later alias evidence. Resolve `wallet_aliases` at the actual as-of cutoff; if the binding was first known *after* the original P1/P14 v2 seal, it is **post-seal and blocked for that historical decision** even if the address matches now. Mainline safety fix [PR #91](https://github.com/hzminhzz/copytrade-pm/pull/91), merge `e5d9933`, prevents future retroactive writes. Historical records previously touched by the older release need a separately reviewed, backed-up, versioned repair, not a silent fix.
5. **Research priority versus paper baseline:** The historical Gemini V2 `gemini.phase4/E6` primary and `gemini.phase4/E2` challenger were new-research choices at that decision cutoff; resolve current selections from SQLite. Sealed `P1`/`P14` Forward-Paper engineering baselines are different contracts; V2 never replaces their run SHA, source wallet equity, risk policy, account identity or first-known clock. The comparison policy is not authorization to launch a worker.
6. **Promotion:** `alias_resolution_complete=true` is indexed identity resolution **only**. Keep `RUNTIME_ADMITTED`, source receipt health, `SCIENTIFICALLY_QUALIFIED`, `TRADING_AUTHORIZED`, `DEPLOYED`, and `PAPER_RUNNING` separate. Default fixed-k requires complete selected perp positions, follower equity/risk, executable markets and independent follower economics; leader NAV, collateral and unselected subaccounts are optional diagnostics. Explicit legacy allocation-over-NAV remains strict.
7. **Selection proof blocked while SQLite verifies:** doctor returns exit 2 with `database_integrity=VERIFIED` and `research_selection_integrity=BLOCKED_MISSING_EXTERNAL_PROOF`. Preserve the unsigned rows and diagnose their exact source. Independently valid wallet/cohort/frozen-version queries may continue; do not admit the blocked selection. The read-only release controller accepts only this explicitly classified negative result, with science/trading false and physical integrity verified. No signature, membership or source hash is rewritten.

## Historical integration and installed-release checkpoint

- The source foundation from old draft [PR #57](https://github.com/hzminhzz/copytrade-pm/pull/57) was incorporated into mainline commit `5d7b4d7` (research catalog integration #79); **#57 was closed as superseded, not merged**.
- Focused frozen-membership safety [PR #91](https://github.com/hzminhzz/copytrade-pm/pull/91) merged to `main` as `e5d9933`.
- Forward-Paper [PR #73](https://github.com/hzminhzz/copytrade-pm/pull/73) was reconciled on top of `e5d9933` at `47f0730` and remained **draft** at the 2026-11-04 checkpoint. Check GitHub again; this is not an evergreen PR status.
- At the verified 2026-11-04 09:36:57 UTC generation, registry `doctor` reported `CURRENT` / `counts_match=true`, **264 configured / 264 subscribed, 158 research, 22 exclusions and 11 source-sealed definitions**, SHA `e2836aab5ef6ef79306e9dfe732d8768c3b1ca6af29efbda066b37f03646a18f`. The installed *registry-only* pinned read-only release still reported `5d7b4d7`, **not** `e5d9933`. No protected P1/P14 worker was verified. These are historical observations; always rerun the commands.
- Code merge, installed read-only registry release, verified paper-worker deployment, science qualification and broker authorization are **separate gates**. Never silently upgrade a status because GitHub CI is green.

## Mandatory agent closeout and OptMem discipline

For a queried wallet/portfolio decision, report the **queried Git revision**, **SQLite inventory identity and observed-at**, **selection version/known-at**, relevant source/proof lineage, and the **exact independently evidenced state**. If any necessary evidence is unavailable, state `UNKNOWN` with the missing authority; do not fill it from recollection.

Use relevant durable OptMem recall when it helps locate an established decision; follow its wake/pagination protocol when invoked. On an accepted durable policy/workflow change, retain a bounded note with the canonical owner path and complete `memo nap` if prompted. OptMem preserves the **instruction to recheck**, not a live wallet count, temporary worktree, source identity or acceptance verdict. Never edit `~/.optmem/memory` directly.

Changes to this contract must update `AGENTS.md`, [INDEX](INDEX.md), the [operator runbook](RUNBOOK.md) and affected public behavior/tests together. Validate the existing registry documentation contract; a prose-only correction does not establish runtime behavior or require a duplicate test suite. Keep source and financial data private; never commit the private SQLite registry, raw wallet addresses, credentials, chats, account IDs or subscriber records.
