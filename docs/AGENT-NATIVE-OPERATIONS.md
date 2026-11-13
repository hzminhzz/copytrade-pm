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
| Facade doctor maps exit 2 to integrity failure even for a valid SQLite database with blocked selection proof | Read `database_integrity` and `research_selection_integrity` separately; retain blocked selection admission | D1, including contract-selector callers |
| Facade generation calls broad registry `status` | Do not use it for a task that forbids financial-journal reads; use scoped native metadata readers | D1 |
| Catalog validation does not cover every public parser leaf; Chapter 2 leaves are missing | Follow the [Chapter 2 runbook](CWSA-CHAPTER2-20261112.md) and CLI help; catalog success is not proof of exhaustive discovery | [D3](AGENT-SYSTEM-DESIGN.md#d3--complete-operation-discovery) |
| Original Chapter 2 runtime check did not independently bind a live PID to the configured application release | New ANOS-05 runtime verifier below independently binds the observed process; do not use the original pre-fix verifier or interpret a Git SHA plus PID as sufficient | [D2](AGENT-SYSTEM-DESIGN.md#d2--truthful-running-release-evidence) |

Do not invent a command to work around a missing catalog record or modify a proof to make a result green. Inspect the existing owner and preserve exact negative evidence.

## Discovery and effects

The catalog discovers project scripts from `pyproject.toml`, checks installed distribution entrypoints and maintains explicit module-only and reviewed registry-operation records. Flat argparse required arguments are derived from source AST; subcommand-dependent/module-only requirements can remain null. Null does not mean no required inputs.

Operations are classified `READ_ONLY`, `LOCAL_MUTATION`, `PROTECTED_MUTATION` or `BROKER_OR_TRADING`. Unknown entrypoints are `UNCLASSIFIED` and fail validation. A parent CLI classification never permits arbitrary child commands or `--apply`. Existing coverage limits are listed above.

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
| Immutable executed research | `copytrade-pm research list --cache-root PRIVATE_CACHE`; `research show JOB_ID --cache-root PRIVATE_CACHE` | Only canonical `pm_offline_job` reports under that explicit root |
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
- Duplicate job IDs need `--cache-key`; a missing explicit root is UNKNOWN. Discovery creates no cache directory. Job execution may write immutable research evidence and is not read-only.
- These research reports do not themselves establish real financial certification, scientific qualification or trading authorization.

SQLite readers use `mode=ro`; this protects table/data writes but may create WAL/SHM coordination files. Do not force immutable mode against an active WAL writer to evade coordination. Respect the task's authorized filesystem/read footprint.

## Runtime and observer diagnostics

The aggregate health adapter delegates to the original registry release verifier and independently checks known P1/P14/watchdog units in both system and user systemd managers. It does not start or stop them. Active unit state alone remains insufficient for financial paper health; inaccessible system-manager evidence is UNKNOWN, not proof a unit is absent.

**Process-to-release evidence (ANOS-05):** `pm_runtime_readonly.verify_unit_release(unit, expected_sha=..., manager=...)` is the read-only shared owner for the allowlisted V4 protected P1/P14/watchdog units (explicit `system` or legacy `user` manager) and CWSA Chapter 2 source/paper units (`user` manager only). It obtains systemd's configured ExecStart, unit/PID, invocation ID, cgroup and monotonic start; checks a detached, clean, allowlisted release checkout and non-writable tracked source; independently reads `/proc/<pid>/stat`, `cmdline`, `cwd`, `exe`, `cgroup`, `status` and `environ`, plus boot ID; and rechecks systemd, PID birth and release identity to catch restart and path races. The Chapter 2 postdeploy gate consumes this single owner rather than combining a configured Git SHA with an unrelated live PID. `VERIFIED` proves the inspected launch was bound to the pinned release at the inspection clock, **not** that all loaded Python/dependency bytes, the finance journal, deployment publisher, or trading authorization are attested. `NOT_RUNNING` requires an observed stable inactive systemd unit; a proven different process or revision is `MISMATCH`; inaccessible metadata, mutable trees and races are `UNKNOWN` with a reason. Chapter 2 maps an unproved active service to `BLOCKED_EVIDENCE`, not `PAPER_SERVICE_NOT_RUNNING`. The supported release roots are `/opt/copytrade-paper/releases` and `~/.local/share/copytrade/releases`; outside locations and writable worker-owned checkouts cannot be verified. There is no privileged inspector, service mutation or automatic release promotion.

Optional `health --observer-state-root PRIVATE_DIR` reads the existing observer evidence. The watchdog checks a consistent tape snapshot and heartbeat-sealed source/quote/collateral chain prefixes. Verified append-only advance after heartbeat is `DEGRADED_OBSERVER_ONLY` / `UNATTESTED_TAPE_ADVANCE_AFTER_HEARTBEAT`, not PAPER_RUNNING. Rewritten/truncated/conflicting prefixes remain unknown. Liveness-only heartbeat does not refresh provider evidence.

Discover `paper.observer.preflight`, `paper.observer.continuous`, `paper.observer.continuous_health`, `paper.observer.continuous_watchdog`, `paper.observer.shadow_report` and `market.continuous_canary` through the catalog. They have different read/write classes; the [continuous observer contract](FORWARD-PAPER-CONTINUOUS-OBSERVER.md) owns arguments, rate budgets, restart and evidence.

`source.public_trades` observes public trades or plans provisional buckets into a private evidence journal. It is classified PROTECTED_MUTATION despite having no broker route. It does not prove a complete selected position book or produce financial paper admission. Use the [public-trade contract](FORWARD-PAPER-PUBLIC-TRADES-20261105.md); [dated market/socket layouts](FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.md) are evidence to revalidate against the actual scope and shared-IP budget.

`paper.public_unit` resolves the existing public-observer unit tool. Default behavior proposes a unit; `--apply` can write a reviewed user unit after its documented checks. It never starts/stops units or grants financial admission. See [observer deployment](FORWARD-PAPER-PUBLIC-OBSERVER-SERVICE-20261105.md) and [protected staging](FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md).

## Native metadata mutations

`copytrade-wallet-registry native status` is read-only. `native lock`, `native register` and `native exclude` have reviewed previews; `--apply` requires the protected native contract, private backup and expected inventory SHA. Exclusions also require registered identity and exact private manifest SHA, and cannot revoke earlier exclusions. A locked database rejects legacy `sync --apply`. The read-only facade does not expose these writes. See [native controls](SQLITE-NATIVE-LEGACY-LOCK-20261105.md).

## Site and presentation

The intended operator UI is the authenticated Site. Its current Chapter 2 evidence/lineage/unknown-value contract belongs to [the Chapter 2 runbook](CWSA-CHAPTER2-20261112.md). Historical [dashboard phase 3](DASHBOARD-PHASE3.md) and [audit](DASHBOARD-FINAL-AUDIT-20261107.md) document an earlier implementation, not current Site acceptance.

Preserve bounded scalar filters, privacy-safe native projections, source clocks and evidence grades. Read saturation must remain unavailable, and unknown P&L remains null. The target CLI/Site parity is part of D4; neither a local status file nor an HTTP 200 independently proves deployed publisher lineage.

## Recovery and proof of improvement

Use [blocker recovery](BLOCKER-RECOVERY.md) and retain the exact affected authority and reason. Continue independent authorized work. A saved portfolio, zero indexed runs or missing known service does not establish that every possible external program is absent.

Existing `tests/test_pm_agent_native.py` and `tests/test_pm_operational_discovery.py` exercise routing, PIT/registry parity, cache integrity and read-only/runtime failure behavior. Scripted CLI cases do not measure live model tool selection.

The [host trace evaluation](AGENT-TRACE-EVAL-20261105.md) accepts independently captured and signed tool-event traces for its fixed tasks. Synthetic or manually transcribed traces remain UNVERIFIED_TOOL_TRACE. Without independent host capture, empirical agent effectiveness remains BLOCKED_NO_INDEPENDENT_HOST_TRACE. The [system plan](AGENT-SYSTEM-DESIGN.md#d6--measure-and-retain-the-improvement) adds end-to-end comparison targets without claiming a measured improvement.
