# SQLite Wallet Registry Adoption Plan — 2026-11-04

**Status:** IMPLEMENTATION PLAN ONLY. No database migration, source-document deletion, production service modification, enrollment, trading permission, or wallet qualification has been executed by this plan.

**Repository:** hzminhzz/copytrade-pm. Plan inspected against origin/main at 309a71c6c2179c7b1975b42f50e634ad6e1f975d, the current Rust tracker checkout, and deployed local systemd configuration on 2026-11-04 UTC. Reverify live state before each phase; counts below are dated observations, not eternal invariants.

## 1. Objective and boundaries

Build a **private, versioned SQLite inventory and evidence index** so agents can ask: which addresses are research candidates, which have which historical datasets, which portfolios were only proposed versus observed running, which are configured/subscribed/admitted for monitoring, and which (if any) have independently qualified follower evidence.

The deep module is **wallet inventory and provenance reconciliation**. Its narrow public interface returns typed, evidence-backed, as-of statuses or explicit UNKNOWN/BLOCKED. It **does not** become an execution gateway, wallet-position ledger, market-data store, portfolio risk authority, or independent scientific adjudicator.

DO NOT replace or write to:
- Rust tracker subscriber watchlist SQLite or its 3.9 GB observation ledger;
- production ensemble/Telegram services or tracker.env;
- existing PM-01 frozen 36-wallet manifests and pm01_fill_only_replay_v2 / PM-02 SHA parity;
- existing Propr/Bybit/trading-connector IntentJournal / PM03-PM04 risk boundaries;
- raw HyperX pages, native ML4T Parquet, historical files, and signed source evidence.

User-visible phrases MUST distinguish RESEARCH_UNIVERSE, CONFIGURED_FOR_OBSERVATION, SUBSCRIBED, RUNTIME_ADMITTED, SOURCE_RECEIPT_HEALTHY, PAPER_ACCOUNT_RUNNING, DEMO_ACCOUNT_RUNNING, SCIENTIFICALLY_QUALIFIED, TRADING_AUTHORIZED, and DEPLOYED. No single mutable stage enum may claim all these meanings.

## 2. Verified baseline (2026-11-04)

| Source | Count / condition | Authority |
| --- | ---: | --- |
| Original roster | 108 distinct | Private WALLET_FILL_RESEARCH_CURRENT_108_20261103.csv; older fill completeness varies |
| Nansen cohort | 20 distinct | Private NANSEN_STRICT_NEW_20_20261103.csv |
| HyperX cohort | 30 distinct | Private HYPERX_STRICT_NEW_30_20261103.csv |
| Research union | **158** distinct | Checked union of those three files; no overlap |
| New 50 fill acquisition | 50/50 wallets; 1,196 wallet-instrument pairs; 1,197 pages; 113,273 fills | Private new50_hyperx_90d_full_vendor_v2/INDEPENDENT_INTEGRITY_50_20261103.json |
| New 50 opaque instruments | 108 #numeric source IDs, not fully mapped to broker instruments | Separate immutable supplement + final v2 manifest |
| Tracker desired addresses | **215** | Deployed TRACKER_DESIRED_WALLETS in /home/quant/.config/copytrade/tracker.env |
| Tracker subscription addresses | **150** distinct; subset of configured desired | Deployed subscriber SQLite, read-only |
| Research vs desired | 19 overlap | Read-only three-source set reconciliation |
| Research vs subscribed | 9 overlap | Read-only three-source set reconciliation |
| Research vs desired union | 354 identities before adding distinct excluded/other discovered addresses | 158 + 215 - 19; aliases never create new wallets; not a research-candidate count |
| PM-01 frozen cohort | 36 = 6+10+20 | Existing pm_sources loader; separate source-era study contract |
| Production admitted wallets | **UNKNOWN from this inspection** | Must derive from authoritative ledger coverage/admission events plus freshness; configuration is not proof |
| Scientific source/follower qualification | No evidence of qualified managers at this inspection | PM02 evidence protocol; no automatic promotion |

Deployed services observed active: copytrade-tracker.service, copytrade-ensemble.service, copytrade-source-abc.service. Tracker database schema has subscriptions(chat_id,address,label). Observation ledger has ledger_meta, outbox_events, position_checkpoints, receipts. The ledger is approximately 3.9 GB; no full-table copy or unbounded full replay in a periodic inventory refresh.

The final new-50 source is private under:
 /home/quant/.local/share/copytrade/reports/five-pod-20261029-research/new50_hyperx_90d_full_vendor_v2

Do not confuse a successful vendor coin-census audit with complete exchange capital, hedging, funding, independent episodes, first-known receipts, or executable follower PnL.

## 3. Design decision

**ADOPT:** Rebuildable, private SQLite **materialized inventory** with versioned research declarations and evidence pointers. Original manifests and signed/evidenced runtime systems remain authoritative at their respective seams.

**REJECT FOR NOW:** Make SQLite the new authority for source positions, source account equity, watchlist membership, order routing, scientific decisions, or fill rows. That would create competing writers and erase existing ownership boundaries.

**REJECT FOR NOW:** A new PostgreSQL/Redis service. The expected few hundred public wallet identities and modest versioned metadata do not justify distributed operation. The high-volume fill/market/observation events already belong elsewhere.

### Storage placement and safety

Planned owner-private location:
 /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite

Paths are illustrative until implementation. Store backups and immutable sanitized snapshot manifests under the same 0700 private root, with SQLite and exported files 0600 and no public bind address. For the registry itself enable foreign_keys, WAL, busy_timeout, synchronous=FULL and durable transactions; one updater process protected by an OS lock. No SQLite ATTACH that could accidentally write to an operational database. Connect to tracker SQLite ONLY with read-only URI; do not change its schema, WAL settings, subscriber records, or permissions.

No wallet addresses, per-subscriber chat IDs, raw provider responses, credentials, secret-bearing configuration contents, private source payloads, or SQLite database files in Git. A nonsecret owner-private root path may appear in an operations guide, but published status reports contain only redacted aggregates, source schema identifiers, and vetted hashes.

### Proposed narrow interface (not yet implemented)

- wallet-registry sync --dry-run : validate prospective import, expose a redacted diff, do not commit.
- wallet-registry sync --apply : one explicit atomic database snapshot/cutover after validation.
- wallet-registry status --json : source-specific counts, observed_at, source SHAs, freshness, unknowns and blocked reasons.
- wallet-registry wallet --alias ALIAS --asof UTC : private lookup only; no inferred identity equivalence.
- wallet-registry portfolio list / portfolio show : versioned documented research selections, not running services.
- wallet-registry doctor : compare live authoritative sources with the latest verified registry generation; report drift and errors.
- wallet-registry report --redacted : generate a reviewable docs/WALLET-STATUS.md preview and a private full internal snapshot from one verified cut. Writing the tracked document is an explicit reviewed documentation step, **not** a timer side effect.

Prefer one module for normalization, validation and transactional reconciliation, with thin read-only adapters at genuine source seams. The names above are acceptance targets, not claims that commands currently exist.

## 4. Proposed minimal data model

| Table / logical relation | Key columns | Contract |
| --- | --- | --- |
| wallets | wallet_id, venue, network, canonical_address | One address identity per venue/network; lowercased 0x prefix plus 40 hexadecimal digits for Hyperliquid; not an independent trader |
| wallet_aliases | namespace, alias, wallet_id, valid_from, valid_to | Unique point-in-time alias meaning; conflicting aliases fail closed rather than overwrite |
| cohorts / cohort_memberships | immutable cohort_id+version, wallet_id, selected_known_at, evidence_id | Multiple simultaneous cohorts and frozen selection versions; do not mutate 36-wallet PM-01 |
| exclusion_decisions | wallet_id, reason, decided_known_at, authority_ref | Exclusion is a versioned decision; never erase earlier membership or silently revive a rejected wallet |
| evidence_artifacts / wallet_evidence | evidence_id, SHA-256, source type, observed/known times, path, audit result | Index original immutable external files; never treat a path alone as verified evidence |
| portfolio_versions / portfolio_memberships | portfolio_id, version, chosen_by, asof, wallet_id, role, sizing_contract_ref | Do not store every exploratory Cartesian combination; store intentionally frozen proposed/tested portfolios |
| monitoring_snapshots / monitoring_wallet_status | source_id, read_at, source_cut, wallet_id, desired, subscribed, admitted, receipt_health | Explicit tri-state/unknown observations; snapshot validity, not permanent wallet stage |
| qualification_decisions | wallet_id, policy_version, evidence_digest, decision, valid_asof | Import independently adjudicated results only; no qualification from PF, synthetic PnL, or regression tests |
| import_runs / schema_migrations | run_id, schema_version, manifest_hash, success, error | Reproducible immutable audit trail, atomic change boundary and rebuildability |

Keep table count and indexes minimal; use foreign keys and uniqueness checks. Explicit valid_time, observed_at and known_at fields where the distinction matters. A later vendor response may restate history but must not acquire an earlier known_at timestamp.

Do not store per-fill trades, full order books, OHLCV, Telegram message contents or high-frequency source events in this SQLite inventory.

## 5. Authoritative import contracts

### Research cohorts

- Import exactly 108 + 20 + 30 from the three **current** private source CSVs, verify path/permissions and SHA, normalize addresses, check exclusion membership and duplicate aliases.
- Link the 50 new wallets to the independent raw-source audit; record 113,273 fill records and 1,196 vendor-listed instrument pairs as aggregate evidence, not reinsert all fills.
- For older 108, preserve per-wallet unknown/partial coverage; do not claim the same uniform pagination audit as new 50.
- Do not auto-enroll 158 in the fixed 36-wallet PM-01 API. A new versioned research consumer is a separate future task with independent tests.
- Import the 28 current user-exclusion decisions and related owner rejected addresses with explicit lineage. An excluded identity may exist in the global inventory while remaining excluded from eligible research queries.

### Monitoring (read-only)

- Parse only TRACKER_DESIRED_WALLETS and TRACKER_DB_PATH from approved deployed tracker.env. Never log or hash a full credential-bearing env file. Fingerprint a normalized, redacted desired-address set.
- Read the live subscriptions table through a read-only SQLite transaction; exclude chat IDs and subscriber-specific labels from exports. Record distinct subscribed addresses and source read time.
- Only if supported by current schemas, derive admitted/coverage from the tracker ledger's committed ledger_meta and bounded/indexed outbox_events (UNIVERSE_CHANGE/COVERAGE_CHANGE). Inspect actual event payload contracts before any parser is implemented. Never query the multi-GB receipt history wholesale on scheduled refresh.
- Config desired / subscriptions / runtime-admitted are three **different** measurements and are not atomically observed across all files/services. Record independent time cuts and uncertainty. If admission is not provable: admitted=UNKNOWN, not desired.
- Reflect active systemd state as an observation only; active process alone does not imply healthy wallet receipts or economic readiness.

### Portfolio and paper monitoring

- Import committed dated decision records (P1, P14 challenger, P16 optional, Combo2/A/B/C) as proposals/experiments with source and version. Research selection is not deployment.
- PAPER_RUNNING or DEMO_RUNNING requires an actual run manifest, separately identifiable virtual account or provider environment, durable journal state, fresh heartbeat, and verified account/run identity. Missing heartbeat => UNKNOWN/STALE, not silently STOPPED or TRADED.
- Future virtual portfolio instances must have separate portfolio_definition_id and run_id; shared source wallets may feed many independent virtual accounts without duplicating wallet identities.
- Do not add auto-execution, broker account creation, subscription writes or live trading controls.

## 6. Phased implementation (dependency-aware)

| Phase | Concrete work | Acceptance predicate |
| --- | --- | --- |
| **WR-01: Freeze source contracts** | Read-only inventory all three research rosters, exclusion sources, 50-wallet audit, live config and subscriber schema; record input paths/hashes and the frozen 36-wallet contract; detect source conflicts | Baseline 158 research, 215 desired, 150 subscribed, 19/9 overlaps reproduced at one dated capture; unsupported live admission marked UNKNOWN |
| **WR-02: Deep inventory module** | Implement SQLite schema/migrations, typed Python service, private transactional store and dry-run; deterministic normalizer and append-only evidence references | Idempotent 2x imports; bad addresses/aliases/foreign keys/SHAs fail without partial commit; no private data in Git or logs |
| **WR-03: Evidence and monitoring adapters** | Read-only import three cohorts + exclusions + new50/older coverage; read-only config and live subscription adapter; bounded runtime admission adapter if available | Exactly matched source counts; no writes to tracker.db or observation ledger; no vendor event-time converted to first-known; stale/admission unknown explicit |
| **WR-04: Portfolios and status** | Versioned portfolio registry for selected experiments; status CLI, doctor, as-of queries, machine JSON and a privacy-safe generated status document | Distinguishes RESEARCH/CONFIGURED/SUBSCRIBED/ADMITTED/PAPER/DEMO/QUALIFIED/AUTHORIZED; no stale proposal shown as running |
| **WR-05: Documentation migration** | Add docs/WALLET-STATUS.md, update INDEX/AGENTS/ARCHITECTURE/DATA-ACQUISITION links; mark historical pages as dated and archive after reference audit | Agent starting at AGENTS/INDEX reaches current guide first; no broken links or accidental deletion of signed historical evidence |
| **WR-06: Fault and integration verification** | Build fixture matrix, crash/restart tests, permissions/audit checks, real read-only production snapshot, full copytrade-pm CI matrix; reversible roll-forward test | Tests prove every invariant below; original PM-01 frozen inputs and live source services unchanged |
| **WR-07: Controlled activation** | Install isolated owner-private database and optional lightweight **read-only** inventory refresh timer; no daemon/network trading path | Preview vs applied snapshots identical after recheck; timer tested, lag/failed reads visible, backup/rollback works; no tracker/ensemble restart required |

WR-01 precedes WR-02 and WR-03; WR-02 precedes WR-03/WR-04; WR-03 and WR-04 precede docs and acceptance. No production deployment before WR-06 verification. Implement iteratively, not as seven independent inconsistent registries.

Prefer an on-demand explicit sync first. A systemd timer is optional after operational evidence justifies it; cadence can be ~15 minutes for owner-private monitoring snapshots and on-change for cohort manifests. The timer must **never** write or commit tracked repository documentation. Do not deploy a new always-on server. Dry-run and alert on unexplained count/drift changes; never automatically expand the watchlist.

## 7. Verification matrix and cutover gates

### Correctness

- Fixture containing the dated 108/20/30 research sets returns exactly **158 distinct**; current desired 215 and subscriber 150 remain separate. The research+desired union is **354** at the dated baseline, not automatically a valid/qualified count.
- The 50-wallet acquisition references SHA-verified 113,273 fills / 1,196 instrument pairs without copying raw fills into the database.
- Case-folded address duplicate, alias collision, newly excluded wallet, mismatched source hash and missing private file each produce a detectable rejection or UNKNOWN. Nothing becomes eligible by omission.
- No false claim that source wallet independence, full-account capital, valid price mapping for #numeric IDs, prospective receipt, follower alpha, authorized account or paper run has been proven.
- A query as-of before selection cannot see later selected cohorts, later qualification verdicts or later amendments (PIT, as-known vs restated).
- Portfolio version and run identity distinct; one wallet may appear in multiple proposals and independent virtual accounts; absence of a run manifest cannot become RUNNING.

### Durability and security

- Test interruption between staged import and commit; previous successful snapshot remains readable, no partial generation published. Re-run from same source produces identical logical database tables and deterministic public summaries.
- Test stale/busy tracker DB, WAL journal replay, process restart, snapshot race, missing ledger schema, ledger_id change, outbox retention/cursor expiration, rejected rate-limit/error and exhausted disk. No service is modified; status is STALE/BLOCKED until recovery.
- One writer, concurrent readers, bounded queries, foreign_key_check / quick_check and online SQLite backup/restore on the **inventory DB only**. Do not checkpoint, vacuum, attach or write to tracker/ensemble/IntentJournal databases.
- Verify 0700 private directories, 0600 DB/backups/reports, no address/chat ID/credential leakage to docs, stdout, PR or CI logs. Never copy source secrets into Git; no new network/broker order interface.
- Use fixed synthetic fixtures for 158/215/150 expectations. Production count assertions are based on refreshed source manifests and allowed change policy, not hard-coded forever.

### Repository and service regression

- Run copytrade-pm core test suite and native-market test suite, Ruff, formatting/build, plus focused inventory tests and an independent check of PM-01 36-wallet parity (original artifact SHA unchanged).
- Capture baseline and post-run service active states, source file SHAs and modification times; compare production tracker subscription/observation DB logical invariants before and after with awareness of unrelated concurrent provider writes.
- Verify actual systemd timer behavior, failure alerts, restart and catch-up. Preserve untouched production release paths and follow the separate service release procedure if future changes are requested.
- Reconcile CLI JSON counts to generated Markdown and input digests on each successful refresh. A report older than its freshness SLA must show STALE and its captured date; never quietly label it CURRENT.

## 8. Rollback and maintenance

- Before first applied registry sync, take a private SQLite backup and retain immutable source-manifest hashes; test restore to a temporary path.
- Failed schema migration or importer: rollback transaction; leave previous good generation and previous documentation untouched, display stale/failed generation rather than fabricating zeros.
- Failed timer/read-only source adapter: disable **only the new registry timer**; use prior verified inventory generation with explicit as-of, not a tracker service restart.
- Restore prior doc link only after validating it points to dated evidence, not as an excuse to reinterpret frozen states.
- Deleting obsolete status summaries is a **later**, reference-reviewed cleanup. Never delete raw source evidence, signed journals, immutable score reports, OptMem memory, or private source generations.

## 9. Completion definition

The migration is DONE only when a new agent can read one current INDEX/STATUS, use a stable CLI to query wallet/cohort/portfolio/monitoring state, explain why 158 research is different from 215 configured and 150 subscribed, detect stale/unknown admission and paper-account run state, trace every claim to a dated verified source SHA, and reproduce the published snapshot after restart — **without altering existing observational or execution state**.

**This is an inventory/operations correctness program. It does not automatically qualify wallets or authorize a follower trade.**

Independent architecture judge: JUDGE_UNAVAILABLE in this session; recommendation is grounded in inspected source contracts and remains subject to implementation tests.
