# Agent-native capability discovery and read-only operations

**Role:** CURRENT INTERFACE GUIDE. These are existing commands and boundaries. The proposed richer operation/result contracts and remaining work are in [Agent system design](AGENT-SYSTEM-DESIGN.md). [Architecture](ARCHITECTURE.md) owns the system map.

## Start with the requested operation

1. Resolve the task and authority through [INDEX](INDEX.md). State qualified target, as-of/policy and allowed read/write scope.
2. Discover the existing operation with `copytrade-pm capabilities list`, `show <id>` and `validate`; inspect its owner, required inputs, effect class and public tests.
3. Read the smallest sufficient evidence. Metadata questions use the [registry workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md); runtime, paper and research questions use their own evidence owners.
4. Preserve independent result dimensions and exact provenance. Explain a blocker in the scope of the requested operation.
5. For an authorized change, use the owning operation and verify its actual postcondition. Update its contract and catalog when public behavior changes.

The existing design is a discovery directory plus a small read-only facade. `wallet_registry` owns private metadata, not Git/runtime/finance. PM03/PM04 own paper finance; Guardian in prop-production owns protected finance. Discovery is descriptive and never grants permission.

## Known limitations at the reviewed baseline

These limitations were identified at `1c4ac38e76dc7ed31e3421273269750b2f03e086`. They are planned corrections, not fixes implemented by this documentation revision. Recheck the actual candidate before relying on a result.

| Limitation | Safe interpretation now | Planned owner |
| --- | --- | --- |
| Facade generation emits VERIFIED but its reader compares with CURRENT | A facade STALE label alone does not invalidate native SQLite metadata; inspect the native fields | [D1](AGENT-SYSTEM-DESIGN.md#d1--truthful-registry-diagnostics) |
| Original baseline facade doctor mapped exit 2 to integrity failure even for a valid SQLite database with blocked selection proof | ANOS-04 separates `database_integrity` (`VERIFIED`) from `research_selection_integrity` (`BLOCKED_MISSING_EXTERNAL_PROOF`) in `pm_operations._doctor` and `DashboardReader.wallets`, and validates each requested portfolio's own seal/proof in `pm_contract_selector._registry_identity`; retain blocked admission for unverified selections | [D1](AGENT-SYSTEM-DESIGN.md#d1--truthful-registry-diagnostics), including contract-selector callers |
| Facade generation calls broad registry `status` | Do not use it for a task that forbids financial-journal reads; use scoped native metadata readers | D1 |
| Catalog validation does not cover every public parser leaf; Chapter 2 leaves are missing | Follow the [Chapter 2 runbook](CWSA-CHAPTER2-20261112.md) and CLI help; catalog success is not proof of exhaustive discovery (resolved by ANOS-08 below) | [D3](AGENT-SYSTEM-DESIGN.md#d3--complete-operation-discovery); resolved by ANOS-08 below |
| Original Chapter 2 runtime check did not independently bind a live PID to the configured application release | New ANOS-05 runtime verifier below independently binds the observed process; do not use the original pre-fix verifier or interpret a Git SHA plus PID as sufficient | [D2](AGENT-SYSTEM-DESIGN.md#d2--truthful-running-release-evidence) |

Do not invent a command to work around a missing catalog record or modify a proof to make a result green. Inspect the existing owner and preserve exact negative evidence.

## Discovery and effects

The catalog discovers project scripts from `pyproject.toml`, checks installed distribution entrypoints and maintains explicit module-only and reviewed registry-operation records. Flat argparse required arguments are derived from source AST; subcommand-dependent/module-only requirements can remain null. Null does not mean no required inputs.

Operations are classified `READ_ONLY`, `LOCAL_MUTATION`, `PROTECTED_MUTATION` or `BROKER_OR_TRADING`. Unknown entrypoints are `UNCLASSIFIED` and fail validation. A parent CLI classification never permits arbitrary child commands or `--apply`. Each capability entry also carries backward-compatible `access` metadata (`read_targets`, `write_targets`, `network`, `credentials`, `privacy`), using explicit `"UNKNOWN"` for unverified `GROUPS`, `NATIVE` and `EXTRA_MODULES` entries rather than inferring permissions from safety classes.

For `copytrade-wallet-registry` (`src/copytrade_pm/wallet_registry.py`), `validate` enforces fail-closed AST checks on parser leaves, `--apply` operations (disallowing `READ_ONLY`), parser-required flags vs dispatch-level requirements (`paper --apply`, `qualification --apply`), explicit access metadata, and unsupported parser constructs (`UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:*`).

As of ANOS-08 (`#342`), discovery and fail-closed validation cover all CLI entrypoints:
- Missing `copytrade-pm` leaves (`cwsa chapter2 verify|projection|explain`, `capabilities list|show|validate`, `portfolios list`, `research show|preflight`, `contracts rules`, `status`) are cataloged as `SUBCOMMAND` records with verified `access`, preserving the 8 existing `NATIVE` `copytrade-pm` capability IDs without duplicate rows.
- `GROUP_OPERATIONS` adds explicit `SUBCOMMAND` mode variants (`source.public_trades.*`, `paper.public_unit.*`, `account.pm03.simulate.*`, `source.receipts.*`, `paper.unit_bundle.*`, `production.export.cli.*`, `paper.standby.*`, `agent.trace.eval.*`, `paper.observed_execution.*`, `paper.observer.*`, `paper.observer_health.heartbeat`, `paper.identity.audit`, `market.ccxt.*`) with verified `access`, retaining conservative parent `GROUPS` classifications and keeping unverified entries explicitly `"UNKNOWN"`.
- Entries separate argparse-enforced `required_arguments` from conditional/mode-specific `runtime_required_arguments`.
- Owner-specific bounded AST inspectors validate `pm_operations.py` (+ `pm_cwsa_chapter2_gate.add_arguments`), all 39 flat `GROUPS` parsers, and `pm03_cli.execute` dynamic JSON `spec.action` dispatch (`UNLISTED_*`, `STALE_*`, `UNSAFE_*`, `UNSUPPORTED_*`), while `capabilities validate` reports explicit `limitations` instead of claiming universal Python completeness. Baseline historical limitations remain recorded above.

Before adding a module or data path, resolve the capability, read the public owner/tests, then reuse or deepen that owner. Introduce a new responsibility only when the existing boundary cannot express the behavior without exposing internals or violating authority. Update discovery, its guide and behavioral checks in the same change.

## Existing command routes

Examples below use an already installed environment or the reviewed repository environment. Check `--help` on the exact revision; placeholders are inputs to resolve, not defaults. Discovery does not authorize package installation or private data access.

```bash
copytrade-pm --help
copytrade-pm capabilities list
copytrade-pm capabilities show portfolio.current
copytrade-pm capabilities show wallet.lookup
copytrade-pm capabilities show research.offline
copytrade-pm capabilities validate
```

| Need | Existing route | Scope |
| --- | --- | --- |
| List/current/frozen portfolio | `copytrade-pm portfolios list`, `current`, `show q3/B` | Registry-backed; known facade limitations above |
| Wallet lookup/inventory | `copytrade-pm wallets show W083`; `wallets list --cohort research-108 --limit 50` | Address-redacted metadata, not source/finance health |
| Scoped native identity lookup | `copytrade-wallet-registry wallet --alias W083`; `portfolio q3/B --asof <UTC>` | Native SQLite owner; verify integrity and requested identity |
| Immutable executed research & reuse preflight | `copytrade-pm research list --cache-root PRIVATE_CACHE`; `research show JOB_ID --cache-root PRIVATE_CACHE`; `research preflight --cache-root PRIVATE_CACHE --request REQUEST_JSON` | Only canonical `pm_offline_job` reports and `coverage_receipt` entries under that explicit root |
| Aggregate diagnostics | `copytrade-pm status`, `copytrade-pm health` | Multiple owners; use only when their read scope is appropriate |
| One paper run | `copytrade-pm-paper-status --db PRIVATE_DB --run-id RUN_ID` | Authorized independent journal/worker evidence |
| Registry installed release | `python scripts/registry_release.py verify` | Registry release only, not all trading services |
| Chapter 2 gates/projection | `copytrade-pm cwsa chapter2 --help` and [owning runbook](CWSA-CHAPTER2-20261112.md) | Premerge, predeploy and postdeploy are separate; runtime limitation applies |

For contract comparisons, discover `research.contract_selector`, then use `copytrade-pm contracts rules` and `contracts compare --portfolio NAMESPACE/ID --tape PRIVATE_TAPE`. Missing complete matched net follower evidence is BLOCKED. See [contract EV](CONTRACT-PORTFOLIO-EV-TOOL-20261105.md).

`research.actuary` / `copytrade-pm-actuary` is a separate synthetic scenario capability. Its outputs remain scenario assumptions, not observed profitability; see [actuarial research](CONTRACT-ACTUARY-RESEARCH-20261105.md).

## Result interpretation

Registry reads return `copytrade_read_result_v1` with query status, authority, source identity, query/source clocks, data, limitations and error code. Native SQLite `inventory_sha256` identifies current metadata; historical import `source_manifest_sha256` and its age are lineage, not a replacement roster or automatic staleness veto. Git HEAD and installed release revision are separate identities.

Read the full component fields. Exit 2 can mean missing evidence or a blocked selected query; it does not by itself prove corruption. A successful aggregate process can contain UNKNOWN/BLOCKED components. Preserve native dimensions when a facade translation disagrees. Qualification and authorization are not inferred from successful JSON or a healthy observer.

### Wallet and research bounds

- `wallets list` is capped at 200 rows. It supports alias-substring `--query`, `--cohort`, exclusion/subscription filters and `--asof`; addresses and exclusion reasons are redacted.
- `registry_wallet_id` is generation-local, not durable across imports. Qualified namespaces and known-at alias resolution prevent collisions and retroactive membership.
- Monitoring flags describe their recorded snapshot, not a reconstructed historical subscription series. Missing stays null/UNKNOWN.
- `research list/show` verifies canonical job manifests, dependency keys and payload SHA. Arbitrary JSON, raw vendor pages and unpublished experiments are not completed jobs.
- `copytrade-pm research preflight` (`research.preflight` -> `pm_offline_job_catalog.assess_reuse` and `pm_bounded_acquisition.plan_bounded_acquisition`; bounded execution via `research.bounded_acquisition` -> `pm_bounded_acquisition.execute_bounded_acquisition`) performs read-only reuse & bounded acquisition preflight over the existing `ImmutableCache` root (`job_report`, `coverage_receipt`, `acquired_unit`, `acquisition_run`/`acquisition_attempt`) and optional `--partition-root` immutable partitions (with `--plan-acquisition` or an `"acquisition"` section in the request JSON). States: `VERIFIED_CACHE_HIT`, `VERIFIED_EMPTY`, `UNCOLLECTED_OR_BLOCKED_PERIOD`, `INCOMPLETE_WALLET_DEX_SCOPE`, `INVALIDATED_BINDING_CHANGED`, `BLOCKED_EX_POST_COHORT_NOT_PIT`, `BLOCKED_HOLDOUT_VIOLATION`, `BLOCKED_DISALLOWED_DEX`, `REMOTE_METADATA_UNAVAILABLE`, `CORRUPT_RECEIPT`, `CORRUPT_LOCAL_PARTITION`, `BUDGET_EXHAUSTED`, `CACHE_MISS`, `REFUSED_NOT_REUSABLE_FOR_PURPOSE`.
  - **Bounded cost & recovery (`ANOS-14`):** `pm_bounded_acquisition.plan_bounded_acquisition` and `execute_bounded_acquisition` check declared wallet/DEX/date scope, Hive local SHA-verified partitions (`{source|market}/{dex}/[wallet/]year=YYYY/month=MM/day=DD`), cross-study `market_coverage` receipts, and T13 coverage receipts; plan only missing verified `source`/`market` units without per-wallet remote rescans; predict remote compressed column/row-group bytes (accounting for absent vs pruning column statistics) and request counts strictly separately from filtered return rows and report `forecast` vs observable `actual`; stop fail-closed on credential failure, permission expiry, missing unit metadata, corrupt remote pages/ETag drift, scope expansion, cancellation, or budget exhaustion without inventing zero data; and resume interrupted runs only for independently SHA-verified missing units under original scope, caps, and input hashes. No new Reservoir campaign, AWS credential discovery, protected service scheduling, or paper rollout is ever auto-authorized.
  - **Binding:** Requests and cached reports bind and attest `cohort`, canonical normalized `wallets`, `dexes`, UTC window (`utc_start`, `utc_end`), `as_of`, `job_sha256`, `input_sha256`, `source_sha256`, `market_sha256`, `software_sha256`, `cost_assumption`, `policy` and `report_schema` into `artifact_binding_sha256`/`request_binding_sha256`. Unbound legacy `pm_offline_job` reports or mismatched fields return `INVALIDATED_BINDING_CHANGED` with `mismatch_fields`. Coverage is verified only from SHA-bound on-disk `coverage_receipt` (`pm_coverage_receipt_v1`) artifacts matching `input_sha256`, `source_sha256`, and `known_at <= as_of`; `row_count=0` counts as `VERIFIED_EMPTY` only when `source_verified=True` and `empty_verified=True`.
  - **PIT:** A window starting before `selection_known_at` (or with `selection_known_at=None`) is flagged `EX_POST_FIXED_COHORT_NOT_PIT` (never inferred prospective first-known or executable follower P&L); `--require-pit` / `require_pit=True` blocks reuse (`BLOCKED_EX_POST_COHORT_NOT_PIT`), and reports claiming `PROSPECTIVE_FIRST_KNOWN` for an ex-post window fail closed as `CORRUPT_RECEIPT`.
  - **History:** Negative, inconclusive, and superseded trial receipts remain immutable; `supersedes` and `depends_on_cache_keys` expose `dependent_results_needing_refresh` alongside `prior_reports`, truncation flags, and `history_scan_complete`. Damage at the requested report or any cited coverage receipt returns `CORRUPT_RECEIPT` while isolating unrelated corrupt entries.
  - **Authority:** A hit is research evidence only (`RESEARCH_EVIDENCE_ONLY` / `EX_POST_RESEARCH_EVIDENCE_ONLY`). It never grants fresh account balances, quotes, HALT clearance, Copy Mandates, paper-financial proof, scientific qualification or trading authorization.
  - **Inspection boundaries (`origin/main` `d7d59d6`):** `wallet_store` is absent from `origin/main` (untracked in `/home/quant/dev/copytrade-pm`), PR #332 remained unmerged when inspected, and installed checkouts under `~/.local/share/copytrade/releases/` reflect older pre-ANOS commits. This preflight depends on none of them.
- Duplicate job IDs need `--cache-key`; a missing explicit root is UNKNOWN. Discovery creates no cache directory. Job execution may write immutable research evidence and is not read-only.
- These research reports do not themselves establish real financial certification, scientific qualification or trading authorization.

SQLite readers use `mode=ro`; this protects table/data writes but may create WAL/SHM coordination files. Do not force immutable mode against an active WAL writer to evade coordination. Respect the task's authorized filesystem/read footprint.

## Runtime and observer diagnostics

The aggregate health adapter delegates to the original registry release verifier and independently checks known P1/P14/watchdog units in both system and user systemd managers. It does not start or stop them. Active unit state alone remains insufficient for financial paper health; inaccessible system-manager evidence is UNKNOWN, not proof a unit is absent.

**Process-to-release evidence (ANOS-05):** `pm_runtime_readonly.verify_unit_release(unit, expected_sha=..., manager=...)` is the read-only shared owner for the allowlisted V4 protected P1/P14/watchdog units (explicit `system` or legacy `user` manager) and CWSA Chapter 2 source/paper units (`user` manager only). It obtains systemd's configured ExecStart, unit/PID, invocation ID, cgroup and monotonic start; checks a detached, clean, allowlisted release checkout, non-writable tracked source and non-writable interpreter target; independently reads `/proc/<pid>/stat`, `cmdline`, `cwd`, `exe`, `cgroup`, `status` and `environ`, plus boot ID; and rechecks systemd, PID birth and release identity to catch restart and path races. ANOS-06 (#340) integrates this owner into the public Chapter 2 postdeploy gate. T05 deliberately left that gate unchanged until T06. The gate now maps running release launch `VERIFIED` to PASS, genuinely stopped or mismatched to FAIL, and inaccessible, unpinned or raced process evidence to BLOCKED_EVIDENCE. An additional `observe_unit_liveness` call independently binds systemd's live process with its actual `/proc` identity and restart-sensitive birth; this does not establish the immutable release or financial proof. `VERIFIED` proves the inspected launch was bound to the pinned release at the inspection clock, **not** that all loaded Python/dependency bytes, the finance journal, deployment publisher, or trading authorization are attested. `NOT_RUNNING` requires an observed stable inactive systemd unit; a proven different process or revision is `MISMATCH`; inaccessible metadata, mutable trees and races are `UNKNOWN` with a reason. A running but unproved application remains `BLOCKED_EVIDENCE`; it is not `PAPER_SERVICE_NOT_RUNNING`. An unobserved process is not an inferred stop. Finance still fails closed for genuinely stopped/mismatched workers and due changed-event stalls, and postdeploy `financially_active` requires every acceptance check to PASS. The supported release roots are `/opt/copytrade-paper/releases` and `~/.local/share/copytrade/releases`; outside locations and writable worker-owned checkouts cannot be verified. There is no privileged inspector, service mutation or automatic release promotion.

Optional `health --observer-state-root PRIVATE_DIR` reads the existing observer evidence. The watchdog checks a consistent tape snapshot and heartbeat-sealed source/quote/collateral chain prefixes. Verified append-only advance after heartbeat is `DEGRADED_OBSERVER_ONLY` / `UNATTESTED_TAPE_ADVANCE_AFTER_HEARTBEAT`, not PAPER_RUNNING. Rewritten/truncated/conflicting prefixes remain unknown. Liveness-only heartbeat does not refresh provider evidence.

Discover `paper.observer.preflight`, `paper.observer.continuous`, `paper.observer.continuous_health`, `paper.observer.continuous_watchdog`, `paper.observer.shadow_report` and `market.continuous_canary` through the catalog. They have different read/write classes; the [continuous observer contract](FORWARD-PAPER-CONTINUOUS-OBSERVER.md) owns arguments, rate budgets, restart and evidence.

`source.public_trades` observes public trades or plans provisional buckets into a private evidence journal. It is classified PROTECTED_MUTATION despite having no broker route. It does not prove a complete selected position book or produce financial paper admission. Use the [public-trade contract](FORWARD-PAPER-PUBLIC-TRADES-20261105.md); [dated market/socket layouts](FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.md) are evidence to revalidate against the actual scope and shared-IP budget.

`paper.public_unit` resolves the existing public-observer unit tool. Default behavior proposes a unit; `--apply` can write a reviewed user unit after its documented checks. It never starts/stops units or grants financial admission. See [observer deployment](FORWARD-PAPER-PUBLIC-OBSERVER-SERVICE-20261105.md) and [protected staging](FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md).

## Native metadata mutations

`copytrade-wallet-registry native status` is read-only. `native lock`, `native register` and `native exclude` have reviewed previews; `--apply` requires the protected native contract, private backup and expected inventory SHA. Exclusions also require registered identity and exact private manifest SHA, and cannot revoke earlier exclusions. A locked database rejects legacy `sync --apply`. The read-only facade does not expose these writes. See [native controls](SQLITE-NATIVE-LEGACY-LOCK-20261105.md).

## Site and presentation

The approved ANOS-12 operator UI is the existing public **Ops Control Center** at `ops.hzminhzz.space` (`ops/control-center/src/`, `scripts/dashboard_server.py`); it replaces ChatGPT Sites integration for this ticket. The Chapter 2 evidence/lineage/unknown-value contract still belongs to [the Chapter 2 runbook](CWSA-CHAPTER2-20261112.md). Historical [dashboard phase 3](DASHBOARD-PHASE3.md) and [audit](DASHBOARD-FINAL-AUDIT-20261107.md) describe earlier interfaces, not an installed Ops revision.

Preserve bounded scalar filters, privacy-safe native projections, source clocks and evidence grades. Read saturation must remain unavailable, and unknown P&L remains null. **ANOS-12 Ops candidate:** `copytrade-pm cwsa chapter2 site-view --portfolio A --inspection evidence` returns a redacted, read-only view derived from the same `explain_task` assessment as `copytrade-pm cwsa chapter2 explain`. The existing Ops server exposes `GET /api/owner-view?portfolio=A&inspection=evidence`, with a fixed six-portfolio allowlist, bounded source read and no caller-controlled journal paths. The existing Gates & blockers page presents the returned owner schema, original checkpoint/first-known/publication clocks, independently scoped dimensions, affected/unaffected portfolios, causal blockers, null modeled economics, and descriptive READ_ONLY next operation. Neither CLI nor HTTP/UI grants trading or paper-financial permission. The deployed Ops release must be verified separately; the untracked historical Site and pinned dirty release are preserved. Ops HTTP is public read-only, not authenticated. Browser/fixture tests establish candidate parity but not a runtime promotion.

## Bounded causal evidence comparisons (ANOS-10)

For one Chapter 2 portfolio, `copytrade-pm cwsa chapter2 explain --portfolio A --inspection evidence` exposes original native source checkpoint/receipt clocks and owner-specific heads. Optionally add `--prior-snapshot PATH` to compare against a previous JSON explanation for **the same portfolio and inspection**. This opens only one bounded caller-selected prior file (maximum 1,000,000 bytes); it never creates a shared status store or renews stale evidence. The causal delta distinguishes changed selected-wallet evidence from an unrelated 14-wallet aggregate head advance.

Use `scope.new_risk_source_status` to see portfolio-local complete-position source readiness, and read `fault_isolation` to identify additional affected source portfolios. These are **not** Guardian account-risk or broker permissions. The separate Chapter 2 Site projection carries the same new-risk source distinction and preserves owner-paper history. Mixed native source policy epochs produce `MIXED`; independently sampled release/quote/mandate/Guardian generations remain `UNVERIFIED` absent external cross-owner proofs. Neither outcome is a globally VERIFIED snapshot. See [Chapter 2 runbook](CWSA-CHAPTER2-20261112.md#anos-10-causal-source-head-deltas-and-wallet-local-fault-isolation).

## Recovery and proof of improvement

Use [blocker recovery](BLOCKER-RECOVERY.md) and retain the exact affected authority and reason. Continue independent authorized work. A saved portfolio, zero indexed runs or missing known service does not establish that every possible external program is absent.

Existing `tests/test_pm_agent_native.py` and `tests/test_pm_operational_discovery.py` exercise routing, PIT/registry parity, cache integrity and read-only/runtime failure behavior. Scripted CLI cases do not measure live model tool selection.

The [host trace evaluation](AGENT-TRACE-EVAL-20261105.md) accepts independently captured and signed tool-event traces for its fixed tasks. Synthetic or manually transcribed traces remain UNVERIFIED_TOOL_TRACE. Without independent host capture, empirical agent effectiveness remains BLOCKED_NO_INDEPENDENT_HOST_TRACE. The [system plan](AGENT-SYSTEM-DESIGN.md#d6--measure-and-retain-the-improvement) adds end-to-end comparison targets without claiming a measured improvement.
