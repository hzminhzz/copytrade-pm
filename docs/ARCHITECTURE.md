# Architecture: evidence, manager governance, shadow account

## Public market-wide trade stream and UTC planning (2026-11-05)

[The forward public-trade contract](FORWARD-PAPER-PUBLIC-TRADES-20261105.md) adds a read-only market-wide buyer/seller filter to `pm_forward_public_trades` using the SQLite-sealed portfolio registry. A separate additive journal tape stores first-known wallet fills, durable commit clocks, disconnect gaps, five-minute UTC net-delta observations, and as-of public quotes. All are provisional; `PM03/PM04` remain the only financial accounting/target authorities. The existing rolling `ForwardBatch` contract is unchanged by default, with opt-in UTC close or UTC close-plus-five-minute policies. The new source code does not create `PAPER_RUNNING` or execute a financial event.

## Protected standby operational boundary (2026-11-05)

[The guarded standby/watchdog candidate](FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md)
adds self-PID SHA heartbeats, a separate watchdog with a persistent HALT latch,
and system-level unit definitions pinned to a source SHA. It contains **no
financial execution interface** and must not be confused with the existing
PM-03/04 journal, public observer or protected paper admission. Installation
requires root-managed identities and a root-owned release; these are currently
unavailable, and the component explicitly reports standby rather than running.

## Public observer service boundary (2026-11-05)

The [public P1/P14 observer deployment contract](FORWARD-PAPER-PUBLIC-OBSERVER-SERVICE-20261105.md)
adds a verified pinned **user** service configuration for existing first-local
public source and CCXT market tapes. The unit has no broker transport and
cannot create PM-03 financial events, join protected P1/P14 identities or
attest complete source equity. Public observer health may be
`DEGRADED_OBSERVER_ONLY` while protected paper remains `NOT_RUNNING`.
A quant-owned service is deliberately not a protected financial account.

## Agent-native discovery seam (2026-11-04)

[Agent-native operations](AGENT-NATIVE-OPERATIONS.md) introduces a machine-readable
capability directory and read-only orchestration facade. The new interface
delegates to existing domain authorities: wallet registry for indexed identities,
PM-03 for finance, prospective journal/heartbeat for paper, Polars job for
research, and installed Git/release tooling for respective observations.
No new database or financial authority is introduced. Unavailable runtime
sources are explicitly `UNKNOWN`; a research selection is never worker state.
The 5 November extension implements a private address-redacted wallet listing
in the existing registry catalog, SHA-verifies canonical immutable Polars
job reports within an explicitly scoped cache root, and delegates installed
release/observer validation to their owners. Systemd unit inspection is
OS evidence only, never protected worker admission.

The [P2 agent trace evaluation seam](AGENT-TRACE-EVAL-20261105.md) is an
isolated read-only scorer for externally captured host tool events. It is
not a replacement agent, a production event interceptor or a writer. An
independently pinned Ed25519-signed host capture is required for an empirical
pass; tests and assistant-authored transcripts cannot satisfy that boundary.


## Offline milestone #2 complete engineering vs independent science (2026-11-04)

[Owner-approved engineering acceptance](OFFLINE-MILESTONE2-ENGINEERING-ACCEPTANCE-20261104.md)
adds a single `pm_offline_job` manifest-to-report seam. It dispatches only
(a) a sealed synthetic PM-03 Decimal scenario with exact opening whole-book
and source-equity-as-of admission or (b) SHA-pinned real historical-oracle
source/market alignment, which is SCREEN_ONLY.

The `pm_offline_intents` compiler selects the latest *eligible entire
source book* across instruments, not lexicographic instrument order;
admits separately priced nonflat opening positions; enforces an equity
observation known at the **execution** instant; and right-censors unseen
fills. `pm_offline_receipts` checks local synthetic prospective bundle
source identity/time equality but does **not** independently attest a
real producer. PM-03 remains the **only** sequential cash, NAV, position,
fee, funding, drawdown and HALT authority.

One failing portfolio scenario returns `PARTIAL` with typed BLOCKED reason
and does not poison unrelated completed scenarios. Report and input SHA
are stable across worker counts and separate process restarts.
Optional `pm_offline_hot_market` derives a seven-day read-only, OS memory-mapped Int64 UTC/Float64 OHLCV numeric panel from precisely seven SHA-verified native daily source partitions. The default real 90-day native context cache remains optimized and unchanged. Hot-week arrays are screening-only and cannot authorize a PM-03 contractual PASS/BREACH or execution depth assumption.
A complete 90-day read-only real-data run produced report SHA
`3141e4acb2df842025f880403d9dd4be2702c6811917bcb7949546dbdc6cbd1a`
with `financial_status=BLOCKED_MISSING_ATOMIC_BOOK_ASOF_NAV_AND_REAL_FIRST_KNOWN`.
This is a successful engineering SCREEN_ONLY outcome, **not** historical
follower economics or science. Offline per-fill delay remains separate
from Forward-Paper first-event non-resetting T+300s.


**Scope:** the mainline research architecture, updated during the 2026-11-01 PR17 recovery; see [the dated disposition](RECOVERY-DISPOSITION-2026-11-01.md) for exact commits and verification. This repository was history-filtered from `hyperliquid-expert-ensemble` (see [PROVENANCE](PROVENANCE.md)). It is **not** the production wallet tracker or Telegram consensus engine. Its research code must never import a live broker/order gateway. Read [INDEX](INDEX.md) first.

## SQLite wallet registry authority correction (2026-11-05)

Private SQLite is the single source of truth for current *metadata* wallet
inventory, cohorts, aliases, exclusions and portfolio registrations. Legacy
CSV, JSON and Markdown are import/provenance evidence; they cannot silently
replace direct SQLite membership or drive the read-only release gate. The
`doctor` checks SQLite `integrity_check`, `foreign_key_check`, supported schema,
cohort provenance and a deterministic inventory SHA. Old import age/hash
remains a separately reportable diagnostic. The six `ml4t-top6` members
registered only in SQLite remain included but carry `UNVERIFIED_IMPORT_LABEL`
provenance until independently documented. PM-03 finance, first-known source
NAV, source/market receipts, protected paper workers and trading authorization
remain separately attested authorities, not columns in the registry.

## Private registry boundary (2026-11-04, partial implementation)

Wallet/portfolio discovery and status consumers **must** use the [mandatory registry-first read contract](WALLET-REGISTRY-AGENT-WORKFLOW.md). Git supplies immutable SHA-sealed decisions; private SQLite supplies the versioned materialized index; the tracker, worker, financial journal and qualification record retain independent authority. OptMem and narrative docs are not a current source of truth. A merged source hotfix must not be mistaken for an activated pinned release.


The optional `copytrade_pm.wallet_registry` module builds an owner-private SQLite **inventory** from research roster CSVs, deployed tracker desired list and read-only subscription database. It does not own subscription writes, tracker admission, source equities, financial positions, execution, scientific qualification or risk authorization. See [the operational checkpoint](WALLET-REGISTRY-STATUS-20261104.md) for what has actually been verified; a preliminary imported database is not a completed WR-01–WR-12 activation.

## Wallet research-catalog query interface — 2026-11-04

`wallet_registry_catalog` extends the owner-private SQLite metadata inventory with the **approved Gemini V2 research selection** and qualified, immutable portfolio IDs (`gemini.phase4/E6`, `gemini.phase4/E2`, `gemini.phase5/B`, legacy `q3/B`). The CLI `copytrade-wallet-registry portfolio --current` is the canonical read interface for **new research priority**, distinct from an actual paper-account run. Source V2 JSON has a pinned SHA/first-known Git merge, private Phase 4 alias references have separate SHA and a conservative first-local import clock, and missing or colliding identities are explicit blockers. `portfolio_versions` and their source seals are immutable; new selection priorities are separate append-only `research_selections` rows. The tracker, financial PaperJournal and source data lake remain independent owners and are never written by this catalog. Old PR #57 was closed as superseded by mainline #79 (`5d7b4d7`); frozen membership source-only PIT hotfix #91 was merged as `e5d9933`, but installed release and independent WR/FP/science gates must still be checked separately. See [the registry implementation guide](WALLET-REGISTRY-STATUS-20261104.md) and [V2 decision](decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.md).

**Sealed membership hardening and future updates:** [Registry review hardening](WALLET-REGISTRY-REVIEW-HARDENING-20261104.md) adds a second independent validation of every sealed membership from pinned source definitions, write-time immutability triggers, exact full-address identity SHA, pinned version selection, rollback compatibility preflight, and schema-v8 append-only signed research selections. An independently supplied signer key fingerprint is required; signature acceptance does not confer trading authorization or scientific qualification.

## Responsibility boundaries

| Boundary | Owner | Inputs → outputs | Authority |
| --- | --- | --- | --- |
| Wallet candidate discovery and initial vendor roster | **Upstream/private** wallet research, outside this package | Wallet addresses, alias mapping and vendor-listed instrument roster → frozen cohort source manifests | Discovery only; not scientifically qualified |
| Frozen historical source | `pm_sources`, `pm_source_audit`, `pm_hyperx_overlay_audit` | Owner-private HyperX pages and SHA manifests, optional fresh independent generations → 36 immutable source identities and diagnostic coverage | Historical vendor knowledge, **not** first-known trading signals |
| Exact minute market evidence | `pm_shadow.VerifiedHyperliquidMinuteSource`, `pm_market_audit`, `pm_propr_scope` | Native Hyperliquid 1m Parquet under *ml4t-data* plus public display scope → market-day integrity/availability | Data coverage; not L2 capacity or Propr order-ID authorization |
| Historical whole-wallet PM-01 | `pm_fill_replay`, `pm_fill_cards`, `pm_fill_tape` | Exact source fill books + minute marks → 36 wallets × 5/15/60m hypothetical follower rows; observed signed book tape | `pm01_fill_only_replay_v2` is **hindsight** |
| Prospective collection | `pm_hyperx_forward`, `pm_hyperx_rest_forward` | Bounded read-only vendor WS/REST → immutable first-local receipt files | Receipt only; REST snapshots never qualify |
| Independent receipt and economic audit | `pm_prospective_ledger`, `pm_prospective_cli` | Frozen cohort + receipt → external signed audit → external signed mature follower/control outcome | Exact PM-02 row adapter, as-of validated; cannot independently verify external economic truth |
| Trader Intelligence scientific readiness (merged PR #36; read-only) | `trader_intelligence_qualification`, `trader_intelligence_qualification_cli` | Existing sealed prospective ledger → independent signature/hash/as-of checks → evidence counts, complete horizon groups, descriptive paired net R | Read-only; **never** signs, creates evidence, confers A/B or marks SCIENTIFICALLY QUALIFIED |
| Trader Intelligence bounded native source snapshot (merged PR #36; read-only) | `trader_intelligence_source_capture` | Existing private candidate aliases and official Hyperliquid per-DEX/spot REST responses → immutable local SHA evidence and current source positions | No atomic book, complete NAV, trading permission or historical first-known reconstruction |
| TI native replay and evidence diagnostics (merged PRs #40/#75) | `trader_intelligence_research`, `trader_intelligence_native`, `trader_intelligence_stress`, `trader_intelligence_source_preflight`, `trader_intelligence_walkforward` | Existing read-only source journal, native verified 1m and versioned conditional candidate cuts -> hypothetical 300s/600s stresses, five-policy matched diagnostic, privacy-safe SHA-pinned source readiness | **Unqualified research only:** never produces independent signed economic truth or positive A/B; no source or risk authority |\n| Manager allocator | `pm_manager`, `pm02_audit`, `pm02_risk`, `pm02_campaign`, `pm02_outcomes` | Frozen PM-01 + optional independently attested prospective rows → cards, history, dependence checks and up to five proposed R seats | Research proposals, not orders |
| Protected-decision review check | `pm_governance` | Frozen JSON evidence + policy/commit binding + separately signed review + operator-pinned public key → deterministic read-only verdict | Reviewer signature only; **not** independent science, owner approval, registry mutation or trading authority. See [governance boundaries](GOVERNANCE-GATES.md). |
| Handoff | `pm_handoff`, `pm03_bridge` | SHA-pinned PM-01/PM-02/tape → dependency verdict; positions require separate sealed contract | Cannot turn risk R into position targets |
| Challenge/account simulator | `pm03_rules/account/risk/execution/attribution/memory/run/stress/cli` | Versioned **synthetic** market/PM targets/account evidence → simulated equity, event ledger, HALT and policy comparisons | One **shadow-only** account-risk supervisor |

The **source account's** realized PnL, a **historical modeled follower's** PnL, a **prospective matched follower's** net R, and a **consolidated prop shadow account's** PnL are different objects. Never add or relabel one as another.

## Forward-paper campaign boundary (FP-01, Issue #58)

`pm_forward_paper.PaperCampaign` is the initial **in-memory, non-running** admission facade. It seals `paper_run_manifest_v1` using canonical SHA-256 and creates separate PM-03 `Account.start` projections with exactly $10,000 each. `paper_run_status_v1` explicitly reports `NOT_RUNNING`, `BLOCKED`, `order_route=NONE` and `FORWARD_PAPER_SIMULATED_v1`. `PaperCampaign` exposes no broker order/cancel transport; its journal-backed event methods now apply isolated **synthetic** PM-03/PM-04 fills, without a running scheduler or genuine live-source admission. FP-02 adds opt-in `PaperJournal` SQLite WAL/FULL private account HALT/mark event persistence and replay checks behind `PaperCampaign.record_event`. It does not touch the PM-03 JSONL research ledger or registry database. The broader FP-02 crash, full-disk, backup and load acceptance matrix remains separate from these initial engineering fixtures. FP-03 permits only explicitly attested synthetic fixture `SIMULATED_DECISION` events with `order_route=NONE` and `FORWARD_PAPER_SIMULATED_v1`; it invokes existing PM-03 `classify`, `execute_targets` and `Account` methods, persisting result-dependent replay hashes. Broker-like routes, unconfirmed rulebooks and unknown markets fail closed. FP-04 adds `pm_forward_admission.admit_source_book` for synthetic atomic whole-book, DEX/subaccount, margin/equity and causal-clock attestation; incomplete or sequential REST books commit `BLOCKED_SOURCE`, not a fabricated fill. Any real source remains blocked pending independent producer authentication. FP-05 adds a pure `ForwardBatch` planning seam that locks the first receipt's T+300s due clock and previews due-time whole-book quantities scaled by follower allocation/source equity. That pure planner does not itself execute targets; an additional `pm_forward_pm04` adapter now routes SHA-sealed **synthetic** whole-book receipts into existing PM-04 `PM04_CONFIG/PM04_SIGNAL/PM04_TICK` event processing, journaled by the same `PaperJournal`. Native PM-04 owns non-resetting T+300s batches, independent pod risk/netting and PM-03 modeled fills; signed native targets must satisfy the existing `pm_exposure_sizing` contract: `(source quantity × verified source mark / source equity) × frozen pod allocation / causally known follower mark`. Missing source marks or follower quotes block sizing; direct quantity scaling is valid only if the two prices happen to match. The tests cover two separate P1/P14 accounts, one shared source receipt, due-time execution, later update without timer reset and unfillable reductions. No live producer or autonomous worker is connected. FP-06 introduces a private, shared, read-only-ingestion `source_receipts` tape in the separate paper SQLite store. It rejects conflicting receipt identity, noncontiguous source sequences and impossible source/first-known/capture clocks, and verifies the source chain on reopen. The new `PaperCampaign.record_source_decision`/`PaperJournal.consume_source_effect` requires a SHA/clock-bound existing receipt, and atomically commits each account's consumed source cursor together with the PM-03 decision/event and account snapshot under the same SQLite transaction. Replay checks both the source hash chain and run-specific consumed source cursors; a missing sequence, forged receipt or failed commit cannot advance account holdings. **Still missing:** actual source collector integration, source transport health, PM-04 target dispatch and an independent prospective provider attestation. FP-07 adds explicit synthetic market attestation for native instrument ID, session and permitted-market state, point-in-time known contract, minimum quantity/step and SHA-pinned modeled cost configuration; unsupported markets and altered assumptions commit `BLOCKED_MARKET`. This is not an external quote producer or complete live lot/cost provider mapping. FP-08 adds separate synthetic funding interval events and exclusive interval claims, PM-03 funding/cash/mark reconciliation, and an optional versioned maintenance-margin projection. Missing funding is `UNKNOWN_FUNDING`, missing margin terms `UNKNOWN_LIQUIDATION`; it never fabricates liquidation/exit fills. It is not a live funding publisher or verified venue-margin model. FP-09 adds sealed in-memory P1/P14 frozen member definitions and a non-executing shared-observation fanout. Each P1/P14 PM-03 account remains independent at $10k, while missing S064/whale source books explicitly block P14 without changing P1. The nominal $600 risk definition is not an enforceable per-pod stop here; WR-06 identity integration and live source admission remain unimplemented in this FP branch; synthetic PM-04 shared-source replay and journal persistence are implemented, but no live deployment. FP-11 introduces an independent SQLite `mode=ro` operator status CLI (`copytrade-pm-paper-status`) that reports journal identity, disk free space, explicit NOT_RUNNING/STALE/DEGRADED/HALT, source/market ages, and does not call quiet-wallet inactivity a feed disconnect when heartbeat/snapshot evidence is fresh. It is **not** a running worker, independent watchdog, systemd deployment or attested PID monitor. A manually supplied PID and heartbeat cannot produce a healthy status without an independently verified worker identity. The `copytrade-pm-paper-report` CLI replays PM-03/PM-04 economics from immutable journal events through the same financial authority, verifies persisted state, and reports model PnL, costs, funding, exposure and observed-model drawdown with explicit UNKNOWN prospective coverage and NO alpha/pass-rate claim. The 2x/3x sensitivity columns are NOT_COMPUTED until independently specified runs are performed. No live first-known wallet admission, durable source signal scheduling, prospective paper observations or scientific qualification exists. Neither this class nor this status authorizes production activation, a paper fill, or scientific qualification. Historical PM-03 modes and the no-fill prospective safeguard remain unchanged.

## Draft forward-paper one-shot fixture worker, scale and protected release

`pm_forward_fixture_worker.FixturePaperWorker` is intentionally a **fixture-only library**, not a daemon. It reads complete already-captured SHA-sealed synthetic books from one shared private source tape; all frozen P1/P14 members must be present/fresh before any PM04 signal is sent. Separate PM03 accounts own their own cursor, cash, HALT and attribution; restart reconstructs source books and account effects from persisted SQLite, never from a volatile in-memory book. Native PM04 still controls the T+300s due window, risk and netting. Missing P14 S064/whale observations block only P14, not admitted P1. This does **not** establish a genuine Hyperliquid atomic full-account source or prospective market feed.

`copytrade-pm-paper-preflight` is read-only and fail-closed: the actual VPS `quant` coder identity owns the existing release paths, and generic reports is mode 775; protected paper state must use separately authorized OS identities and paths. No installation or service restart occurs. `scripts/bench_forward_paper.py` supplies short isolated **synthetic** ext4 accounting and 2x burst measurements only. See [forward-paper continuation](FORWARD-PAPER-CONTINUATION-20261104.md) and [load probe](FORWARD-PAPER-SYNTHETIC-BENCHMARK-20261104.md). The real 72-hour pilot, 24-hour 50-account soak, independent provider admission and scientifically qualified results are still unavailable.

## CCXT Pro Hyperliquid read-only quote producer — FP-07 #64

`pm_forward_ccxt_market.ReadOnlyCCXTProHyperliquid` is an optional, pinned (`ccxt==4.5.91`) **public market-data-only** adapter. It resolves each instrument using exchange native `info.name` and explicit HIP-3 DEX discovery; a CCXT numeric `market.id` never substitutes for a native coin. It records first-local-known, provider-event timestamp, observed two-sided L2 and model cost/lot contract with local SHA binding. It refuses future/stale/locked/crossed books, replayed/ambiguous native markets and mismatched source quote hashes. `pm_forward_market.market_contract_reasons` validates `VERIFIED_QUOTE` against the quote proof and rejects an understated observed spread or insufficient minimum notional. `PaperJournal.append_market_quote` stores independent, SHA-chained market receipts outside Git in a 0700 private SQLite directory; restore/backup/readonly chain audits tested. **Crucially, L2 resting book depth is not traded volume:** `volume_base=None`; the existing PM-03 executor still blocks modeled market fills until independently evidenced capacity is available. HIP-3 (such as `xyz:BRENTOIL`) has unverified trading sessions even when a live quote appears, so `supported=False`. This adapter does not supply wallet source equity, position books, venue funding, broker routes, service supervision, trading authorization or scientific qualification. `pm_forward_ccxt_trades.TradeWindow` and `pm_forward_market_stream.BoundedMarketCapture` additionally ingest CCXT Pro public websocket trade caches, **exclude the initial retrospective cached window**, deduplicate immutable native trade IDs, quarantine lost/overrun caches, and store per-instrument first-known receipt SHA chains in `PaperJournal.market_trade_batches`. Each local trade batch remains `trade_volume_complete=false`, `executable_volume_base=None`: a rolling websocket cache is not a verified, uninterrupted venue-volume census. The bounded collection command never starts a daemon or changes account state. See the [L2 canary](FORWARD-PAPER-CCXT-PRO-MARKET-20261104.md) and [bounded trade+quote capture](FORWARD-PAPER-CCXT-TRADES-20261104.md).

## Read-only public Hyperliquid account-scope capture — FP-04/06

`pm_forward_source_observation` is a deliberately **non-admitting** bridge over the existing E4 `allDexsClearinghouseState` parser. It preserves native per-DEX signed inventory, hashes account identifiers, checks official DEX catalog parity and local first-known time, and records per-account evidence in the separate `PaperJournal.source_receipts`. `pm_forward_source_stream` is a bounded public per-parent WS consumer that discovers subaccount names without assuming their balances are observed, excludes provider snapshot backfills and fails closed for missing/invalid native clocks. Even a complete individual all-DEX perp snapshot does **not** provide atomic parent/subaccount/spot/vault equity or a verified collateral denominator: `source_equity=None`, `account_scope_complete=False`, `synthetic_fixture=False`. No genuine paper signal is authorized; see [bounded source observations](FORWARD-PAPER-PUBLIC-SOURCE-SCOPE-20261104.md).

## Test-only worker identity and independent health — FP-10/11

`pm_forward_heartbeat` seals a locally emitted observer-only heartbeat to the native Linux process PID/start-ticks/boot epoch, run+release/manifest hash and financial journal cursor/head. A read-only watchdog CLI compares those to `/proc`, times transport/source/market freshness independently, and fails closed on stale, forged, missing, restarted or financially diverged state. `pm_forward_status` can display the independent verdict via `--heartbeat-root`. This observation is intentionally **never PAPER_RUNNING**: the coder-writable path is not protected, the record is not independently signed, and the source/market production feed remains unqualified. No systemd unit, long-lived protected worker or broker transport has been activated. See [observer health contract](FORWARD-PAPER-OBSERVER-HEALTH-20261104.md).

## Frozen P1/P14 identity-linkage audit — WR-06/FP-10

`pm_forward_registry_identity` opens the existing wallet registry using SQLite read-only/query-only and compares WR-06 frozen P1/P14 membership rows to locally stored owner-private historical address locators. **All five addresses match registered Hyperliquid wallet identities, but current P1/P14 version-2 membership `wallet_id` values remain NULL** (3/3 P1 and 5/5 P14 links missing). The audit never mutates the wallet registry or imports private historical fills. Even an address match does not verify independent prospective source equity, so a roster can only graduate through a new verified registry seal. See [live identity audit](FORWARD-PAPER-REGISTRY-IDENTITY-20261104.md).

## Unified P1/P14 live-readiness and synthetic cost diagnostics — FP-10/13

`pm_forward_readiness.audit_live_paper_readiness` opens the WR registry and both privately captured source/market SQLite tapes using `mode=ro` and `PRAGMA query_only`. It validates source and market SHA chains, compares per-parent account identity hashes to approved P1/P14 native wallet address hashes, enforces local first-known freshness, includes **all** native open position instruments (not headline coin only), and reports exact blockers as `BLOCKED_NO_TRADE`. The live 2026-11-04 audit found 9 required native markets for P1 and 23 for P14; bounded captured quote coverage was 8/9 and 22/23, with `para/ANSEM` rejected by the observed spread threshold. Time-bounded scans cannot count as continuous coverage and all five wallet NAV scopes remain unadmitted. `pm_forward_cost_sensitivity` adds opt-in 2x/3x synthetic PM-03/04 cost replay in `copytrade-pm-paper-report --cost-stress`, without mutating financial records or rerunning Gemini research. See [readiness and cost evidence](FORWARD-PAPER-READINESS-20261104.md).

## Protected service inventory and fail-closed cutover — FP-12

`pm_forward_release.read_only_user_service_inventory` inspects a fixed, validated user-systemd allowlist using property-only `systemctl --user show`; there is no start/stop/restart/deploy interface. The current VPS production tracker, source observer and ensemble are active; no P1, P14 or paper watchdog unit exists. The protected release preflight remains `BLOCKED` because both release and state are coder-writable, the generic reports root is mode 775 and separate OS/service authority has not been verified. The code does not modify permissions or silently start services. See [read-only service inventory](FORWARD-PAPER-PROTECTED-SERVICE-20261104.md).

## Bounded frozen P1/P14 source-observation campaign

`pm_forward_source_campaign.observe_frozen_portfolio_readonly` uses the owner-private P1/P14 alias-address map and read-only wallet-registry audit to issue sequential, bounded **public** all-DEX per-parent subscriptions for each frozen member. The receipts inherit the E4 native DEX and first-known validation, while each result is labeled `BLOCKED_OBSERVATION_ONLY_NO_TRADE`. A missing parent, incomplete subaccount, unsealed membership ID, stale snapshot or unknown NAV must never result in a PM04 order or financial-account activation. This command does not install a service or alter the historical-fills registry. See [source-campaign command and limits](FORWARD-PAPER-BOUNDED-SOURCE-CAMPAIGN-20261104.md).

## Shared P1/P14 read-only public observer (FP-04/06/07 continuation)

`pm_forward_source_campaign.observe_shared_frozen_sources_readonly` validates the versioned WR identity bridge for P1 and P14 before subscribing once to their five unique source addresses. It records independently time-stamped parent/subaccount, spot/vault (diagnostic-only) receipts into the existing SQLite WAL, then `pm_forward_observer.capture_shared_observer_cycle` extracts all witnessed signed native instruments and runs bounded, fault-isolated CCXT Pro L2/trade captures. The separate P1/P14 read-only readiness audits consume those same tapes without any parallel financial authority. It never infers source NAV, executed venue capacity, HIP-3 session approval or continuous feed from partial captures. Finite supervised cycles and fault gaps are available for engineering tests only. An opt-in observer-only indefinite loop persists a locally hashed PID/start-epoch plus verified source/quote/collateral-head heartbeat for a separate SQLite-read-only watchdog (`pm_forward_observer_health`), but never grants protected process authority or `PAPER_RUNNING`. Separately, each isolated account process can use `pm_forward_source_fanout.fanout_one_portfolio_receipts` to verify and copy immutable shared source receipt chains into **only its own** private P1 or P14 `PaperJournal` database, requiring no cross-account OS write privileges. The paired fanout is fixture-only. Its prefix checks make a crash/restart idempotent per account; a financial PM-04/PM-03 effect must still use each account's existing atomic `consume_source_effect`, and no cross-database financial transaction is asserted. No protected service activation or paper financial event writer exists on this path. See [shared observer runbook](FORWARD-PAPER-SHARED-OBSERVER-20261104.md).

## PM-01 historical path

`pm_sources.load_cohort(root)` is deliberately fixed to **6 original + 10 Wave1 + 20 Wave2** and references multiple authoritative private manifests. It reconciles alias/address collisions and vendor pagination; it does **not** accept an arbitrary fresh wallet address. `pm_source_audit.audit()` validates raw page hashes and selected market defects.

`pm_fill_replay.run(root, market_root, risk_budget, hyperx_generations)` loads the vendor-listed exact instrument roster and signed position-before/after fill chains. It withholds an initial book until each listed leg can be anchored; post-anchor discontinuities, missing marks, missing native markets and volume constraints yield `BLOCKED_*`, not manufactured trades or flat exposure. The 5/15/60-minute delays model hypothetical next-minute-open follower actions, not actual first-known receipt or observed Propr fills. `risk_budget=0.01` means **1% gross hypothetical notional**, NOT 0.01 R and NOT probability of passing a challenge.

A separate `pm_fill_tape` materializes a **historical-only** `pm01_observed_book_tape_v1`. Its account snapshots may be useful for source diagnostics but `pm03_actionable_targets_available=False`. A Rust observation path (`pm_portfolio` + `pm_research`) exists as a **separate/legacy** replay boundary; it is not a prerequisite for the fill-only 36-wallet research.

## Whole-wallet and broker boundaries

[E0/E4 integration](RECOVERY-INTEGRATION.md) adds complete-book validation, a single proportional scale per source wallet, native DEX identity and `pm_wallet_handoff` into the existing PM04 authority. Bounded public A/B/C collection remains raw evidence; discovery, freshness and storage integrity do not establish complete capital reconciliation.

[Registered PM02 evidence](PM-02-EVIDENCE-GATES.md) adds immutable fixed OOS looks and independent whole-account v2 attestations. Horizon trials stay separate, repeated looks cannot advance lifecycle, and worst-case exposure envelopes cannot be averaged away.

[The ML4T/Propr specification](ML4T-PROPR-INTEGRATION.md) and `pm_ml4t_contract` provide a pure offline identity/reconciliation oracle. They import no broker or credential provider and implement no execution path. The existing PM03/PM04 financial authority remains unchanged.

## PM-01 forward path

`pm_hyperx_forward` records WS event times and local receipt times; `pm_hyperx_rest_forward` stores recently seen REST fills explicitly tagged snapshot/partial. Both are bounded by provider limits and **do not** create account-complete positions or follower economic outcomes.

`pm_prospective_ledger.ProspectiveLedger` reads the same producer receipt schema `pm01_hyperx_first_local_receipt_v1`; first-known is conservatively the later of producer-local receipt and ledger ingestion clocks. Ledger events are SHA chained and owner-private; independent Ed25519 signatures gate both a receipt audit and a separately matured matched economic outcome. The PM-02 adapter exposes only the **as-of** verified rows. See [signed evidence contract](PM-01-prospective-ledger.md) for full fields and threat model.

**Important missing external seam:** there is no demonstrated, automatically deployed independent reviewer/real follower execution-cost/matched-control outcome producer. A field named `verified_first_known` cannot be populated from vendor timestamp alone.

## PM-02 manager governance

`pm_manager.rank` validates the frozen `pm01_fill_only_replay_v2` contract; historical wallet cards are descriptive. Prospective score requires mature observations with matched control, nonfuture clocks, source/market SHA and complete net economics. Policy includes 60 episodes, 40 effective samples, 30 calendar days, stale/drift tests, Bonferroni-style conservative lower bound and synchronized-dependence/correlated-tail risk screens. `pm02_risk.allocate` allows up to five **research** seats with EMPTY legitimate.

`pm02_audit` pins the PM-01 input raw SHA, each PM-02 output's canonical JSON SHA, previous decision and monotonically increasing decision time. The opt-in ledger CLI binds the as-of chain head. Passing this contract does **not** imply a manager's source PnL was independently reconciled.

## PM-03 account-risk boundary

`pm03_bridge.inspect_pm02` verifies PM-02 SHA and decision time. `require_external_targets` deliberately cannot infer positions from PM-02 R budgets. `pm03_rules` contains dated publicly observed Propr defaults; actual account terms, allowed market IDs, leverage, margin, fees, and compliance remain unconfirmed.

`pm03_account` manages Decimal balance/equity/virtual manager inventory; `pm03_execution` netting and partial simulated fills; `pm03_attribution` financial reconciliation; `pm03_risk` GREEN/YELLOW/ORANGE/RED/HALT; `pm03_memory` locked, durable replay-first event store; `pm03_stress` compares three identical-path **synthetic** allocation policies. `copytrade-pm-shadow` accepts local JSON; it does **not** connect an exchange or order API. See [PM-03 design](PM-03-shadow-account.md).

## PM-04 optional three-pod extension (Issue #12)

The same PM-03 `ShadowRun` owns the account's quantities, cash, risk state and immutable ledger. Optional `pm04_shadow` coordinates versioned independent pod targets, nonresetting 300-second increase windows, immediate reductions, per-pod **independently funded** loss budgets with a frozen PM-03 rulebook-linked reserve receipt, conservative gross/inflight/queued exposure and event-replayed states. `pm04_broker` independently ingests **read-only** external observations (never broker orders); unresolved order or account evidence blocks new risk. `pm04_compare` replays three execution policies on identical synthetic input. Legacy PM-03 snapshots remain unchanged without PM-04. Read [PM-04 contract](PM-04-shadow-hardening.md). PM-36 PR #7 is still separate, unmerged research and cannot authorize live sizing.

## Future ML4T execution ownership — approved boundary, not implemented in PR #13

**Decision (2026-10-31; Issue #12):** retain PM-03/PM-04 as the owner of multi-pod targets, signed netting, virtual attribution, contractual shadow floors, portfolio stress and deterministic replay. Reuse the locally inspected `ml4t-live==0.1.2` and `trading-connector` for provider-neutral execution infrastructure in a **separate migration issue**; do not rewrite the PM-03 shadow account around `SafeBroker` or create a second account financial ledger.

| Function | Current shadow owner | Future separately authorized execution boundary |
| --- | --- | --- |
| Independent pod targets, research clocks and SHA lineage | `copytrade-pm` | `copytrade-pm` unchanged |
| 300-second net batching, per-pod veto, shared net target | `pm04_shadow` + PM-03 `classify` | Same portfolio intelligence, before a broker boundary |
| Per-pod virtual books, central overlay, intended/executed research economics | `pm03_account`/`pm03_attribution` | Preserve as portfolio attribution; actual broker economics must come from reconciled observations |
| Challenge-specific daily-start **realized balance** floor, intraday marked equity and HWM cap | Versioned PM-03 `Rulebook` | Thin Propr-specific contract policy; never replace with ML4T's generic fixed `max_daily_loss` float |
| Broker execution, retries, idempotent order lifecycle and network transport | **None** | `trading-connector` provider adapter behind `ml4t-live.SafeBroker`; exact provider/account environment must be bound |
| Generic order size, total exposure, frequency and kill switch | PM-03 synthetic checks | `SafeBroker`, explicitly fail-closed on any mismatch |
| Actual broker cash, signed net positions, trades, balance, funding and fees | **UNKNOWN** (PM-03 is a shadow projection) | Independently reconciled provider observations are authoritative; PM-03 may only project/attribute, never claim to replace external truth |
| Final live-trading authorization | **None** | Separate signed owner approval and provider contractual terms, not implied by software passing tests |

**Observed local API evidence:** installed `ml4t-live==0.1.2` exposes `ml4t.live.safety.LiveRiskConfig.fail_on_reconciliation_mismatch` with default `False`; a future integration MUST explicitly use `True` and verify connection/restart behavior. Its `max_daily_loss` and `max_drawdown_pct` are generic limits and do not directly encode Propr's daily-start balance floor. The `trading-connector` checkout contains existing uncommitted work; its Propr ML4T bridges must be inspected/reconciled **read-only** before a separate scoped implementation. No adapter or connector work is in this PR.

**Lossless instrument mapping:** the portfolio instrument identity `(venue, market namespace/DEX, symbol)` remains lossless. A future Propr adapter must prove that native `BTC` versus `BTC/USDC` resolves to one authoritative broker position if and only if the exact provider market IDs are equivalent; conflicting aliases, hedge-side ambiguity and account-ID mismatch must HALT. No heuristic ticker stripping. Preserve raw provider IDs and evidence clocks.

**Risk composition:** `portfolio permission ∧ Propr contractual permission ∧ SafeBroker permission ∧ fresh reconciled actual broker state ∧ explicit authorization`. Any veto wins; neither an optimistic PM-03 mark nor a SafeBroker internal shadow `VirtualPortfolio` may fabricate actual balance or positions. Write-ahead durable intents must survive lost ACK/crash; a reconnect requires full provider reconciliation before new risk. The source-of-truth cutover and any genuinely redundant PM-03 function deprecation require **differential tests** against frozen PM-03 fixtures, versioned migration/rollback, and a dedicated review.

See the independent GitHub ML4T migration issue (created after PM-04 engineering verification). No live execution path was introduced here.

## Source and package topology

```text
src/copytrade_pm/
  pm_sources.py / pm_source_audit.py       frozen cohort and source SHAs
  pm_hyperx_*                              bounded vendor diagnostics/forward collection
  pm_market_audit.py / pm_propr_scope.py   venue/data and display-universe gates
  pm_chd_*                                 optional scoped native market-day writers (ml4t-data owner)
  pm_fill_*.py / pm_shadow.py              historical fill-only and market-source replay
  pm_portfolio.py / pm_research.py         separate Rust-observation historical research
  pm_prospective_ledger.py / _cli.py       signed first-known evidence seam
  pm_manager.py / pm02_*.py                conditional manager scoring and allocation
  pm_handoff.py / pm03_bridge.py           versioned SHA handoff and position authority gate
  pm03_*.py                                standalone consolidated shadow account
tests/                                     deterministic, synthetic, adversarial contracts
docs/                                      current handbook + preserved source-era historical reports
examples/pm03_synthetic.json              only synthetic no-network demonstration
```

## Trader Intelligence read-only research seam (merged PRs #36, #40 and #75; 2026-11-04)

Issue #27 defines the independent read-only intelligence consumer. The mainline TI modules include `trader_intelligence.py` (pure C/X-first assessment and stable SHA), `trader_intelligence_intake.py` (historical/prospective as-known journal), `trader_intelligence_book.py` (conditional coherent book enrichment), `trader_intelligence_research.py` (300-second hypothetical minute follower and strict v2 matched controls), `trader_intelligence_features.py` (as-of specialization), `trader_intelligence_native.py` (SHA-verified complete 1m windows), `trader_intelligence_stress.py` (model cost/latency/stop stresses), `trader_intelligence_walkforward.py` (unqualified five-policy fold diagnostic), and `trader_intelligence_source_preflight.py` (read-only owner-private live source/market readiness audit). **No new account risk, PM-02 frozen 36 interface, broker connector, source journal, or network order transport exists.** Actual verified PIT source continuity and independent matched economic evidence remain absent. See the [2026-11-04 engineering report](TRADER-INTELLIGENCE-CONTINUATION-20261104.md).

Original HyperX/public fills remain historical proxies and cannot become prospective first-known data. The full-book enrichment requires coherent locally observed equity and positions and explicit account-mode/spot/subaccount attestation; no source gap can be filled by inference. Unknown independence stays unknown. The reproducible benchmark has no attested unbiased PIT/holdout, independently observed matched follower economics or calibrated positive selection policy, so all comparative scientific conclusions remain **NOT_QUALIFIED** and all model-produced A/B grades remain disabled. Passing deterministic tests cannot authorize live risk.

The ensemble `copy_board.py`/`copy_digest.py` and opt-in C/X adapter are on `feat/expert-wallet-execution-correctness-prospective-research` (ensemble PR #9 merged there at `e033509c`), **not asserted as ensemble `main`**. A separate pinned, reversible **digest-only** C/X release is active and has verified descriptive-only Telegram delivery. Ensemble/tracker financial authorization and order routes remain untouched by TI, and a new research PR merge cannot silently change the production service. See [the dated acceptance](TRADER-INTELLIGENCE-ENGINEERING-ACCEPTANCE-20261103.md) and [Nov 4 continuation](TRADER-INTELLIGENCE-CONTINUATION-20261104.md).

## Things deliberately NOT implied by this architecture

- A public Propr instrument list is not an authenticated tradable market-ID allowlist.
- Source page pagination is not proof of a complete exchange account book, collateral, or funding.
- A day-level SHA is not exact-minute liquidity/depth.
- Positive historical source cashflow or a few modeled executable episodes is not OOS follower alpha.
- Separate wallet accounts' summed closed PnL is not a pooled challenge equity curve.
- The five-seat allocator is not the production consensus-signal engine in `hyperliquid-expert-ensemble`.
- Draft [PM-36 PR #7](https://github.com/hzminhzz/copytrade-pm/pull/7) is separate research, **not** part of this `main` description.

## Offline Polars 2.x PIT study foundations (2026-11-04; draft PR #92)

This is an **additive, offline-only** research surface on the independent
`feat/polars2-pit-offline-sweeps-20261104` branch. It is not the production
paper worker, wallet registry, legacy 36-wallet replay, trading gateway,
scientifically qualified signal or portfolio deployment.

- `pm_offline_manifest.Study`: fail-closed clock/namespace/rule/cost/risk/
  source-equity/market-day SHA manifest, explicit 0/1/2/5/10-minute policies
  and scenario stress snapshots. Unknown, stale or partial evidence is blocked.
- `pm_offline_source.reconstruct_whole_books`: independent account/DEX
  all-leg initial-book continuity, exact same-timestamp position chain,
  as-of positive source equity, no future-only snapshot/phantom flat hedge.
- `pm_offline_eligibility.compile_eligible`: Polars lazy optimizer stage
  using `eligible_at = first_known_at + delay`, followed by strictly later
  native minute open; same-minute collapse only **after each event is eligible**.
- `pm_offline_market`: native Hyperliquid 1m SHA and sidecar validated
  exact timestamp joins. **Prior completed** minute volume is a conservative
  proxy, not executable depth; current minute realized volume is ex-post only.
- `pm_offline_cache`: private, immutable SHA + software-version keyed
  cached outcomes; atomic fsync/sealed hardlinks, corruption checks and
  explicit per-object size/free-disk budgets.
- `pm_offline_account`: **synthetic fixture** adapter to the existing
  PM-03 Decimal `Account`, `execute_targets` and `pm03_risk.classify`.
  Portfolio net/gross/pod concentration and frozen stress exposures are
  conservative pretrade gates; PM-03 remains the cash, PnL, fees, funding,
  drawdown, margin and HALT authority.
- `pm_offline_certification`: fixture-only inclusive exact-floor and
  target checks; missing contractual/whole-book/equity/funding/mark inputs
  return UNKNOWN, ambiguous timing AMBIGUOUS, screening cannot PASS.
- `pm_offline_sweep`: **bounded synthetic fixture-only** deterministic
  scenario runner, 1/2 worker parity, frozen 3/5-wallet and cost stresses,
  crash/resume cache. Real vendor source-to-account execution is **not yet
  certified or supported** by this runner.

The offline **per-fill eligibility policy is distinct from Forward-Paper
PR #73's first-event, non-resetting 300-second batch**. Neither modifies
the other. Retrospective HyperX event timestamps are never relabeled as
prospective first-known receipts. The fixture size envelope is deliberately
small (up to 2,000 events, 32 markets, 1,440 minutes, 12,000
scenario-minutes and 2 workers). It does not meet representative
500k-fill / 13M-bar OOS performance or full economic qualification gates.

See [baseline](OFFLINE-PIT-BASELINE-20261104.md),
[partial engineering checkpoint](OFFLINE-PIT-PROCESSING-20261104.md),
[operator runbook](RUNBOOK.md) and [qualification gates](QUALIFICATION.md).

## Read-only real-data Polars historical-oracle adapter (2026-11-04, PR #92)

`pm_offline_repository` inspects owner-local ignored JSON files from three
research cohorts and the canonical adjacent ML4T Hyperliquid Parquet lake. It
reports aggregate source completeness, SHA-checked native-day coverage and
explicit unsupported/spot coins, but **never** converts a single current
wallet-equity scalar into historical NAV or receipt times.

`pm_offline_oracle` normalizes only verified namespace-qualified perpetual
fills into SHA-addressed source and per-fill delay tapes, 0/1/2/5/10 minutes;
its time clock is explicitly `HISTORICAL_ORACLE`. It provides grouping and
right-censor counts only, not PM-03 follower targets.

`pm_offline_oracle_market` joins those sealed candidates against SHA-verified
native 1m Hyperliquid opening prices and *prior completed-minute* base volume
in bounded per-instrument Polars queries. Missing/partial/invalid market days
are reported as unmatched, never substituted. The optimized market join
retains byte-identical tapes versus a simpler day-by-day reference on the
same 377,130-event full 90-day sample.

None of these imports a broker, changes paper or registry ownership, or
authorizes a real follower P&L. A complete source NAV/atomic opening book
and independently timestamped receipt producer are **still required** for
real PM-03 financial certification. See [dated audit and benchmarks](OFFLINE-PIT-REAL-ORACLE-20261104.md).
