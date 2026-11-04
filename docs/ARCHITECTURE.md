# Architecture: evidence, manager governance, shadow account

**Scope:** the mainline research architecture, updated during the 2026-11-01 PR17 recovery; see [the dated disposition](RECOVERY-DISPOSITION-2026-11-01.md) for exact commits and verification. This repository was history-filtered from `hyperliquid-expert-ensemble` (see [PROVENANCE](PROVENANCE.md)). It is **not** the production wallet tracker or Telegram consensus engine. Its research code must never import a live broker/order gateway. Read [INDEX](INDEX.md) first.

## Responsibility boundaries

| Boundary | Owner | Inputs → outputs | Authority |
| --- | --- | --- | --- |
| Wallet candidate discovery and initial vendor roster | **Upstream/private** wallet research, outside this package | Wallet addresses, alias mapping and vendor-listed instrument roster → frozen cohort source manifests | Discovery only; not scientifically qualified |
| Frozen historical source | `pm_sources`, `pm_source_audit`, `pm_hyperx_overlay_audit` | Owner-private HyperX pages and SHA manifests, optional fresh independent generations → 36 immutable source identities and diagnostic coverage | Historical vendor knowledge, **not** first-known trading signals |
| Exact minute market evidence | `pm_shadow.VerifiedHyperliquidMinuteSource`, `pm_market_audit`, `pm_propr_scope` | Native Hyperliquid 1m Parquet under *ml4t-data* plus public display scope → market-day integrity/availability | Data coverage; not L2 capacity or Propr order-ID authorization |
| Historical whole-wallet PM-01 | `pm_fill_replay`, `pm_fill_cards`, `pm_fill_tape` | Exact source fill books + minute marks → 36 wallets × 5/15/60m hypothetical follower rows; observed signed book tape | `pm01_fill_only_replay_v2` is **hindsight** |
| Prospective collection | `pm_hyperx_forward`, `pm_hyperx_rest_forward` | Bounded read-only vendor WS/REST → immutable first-local receipt files | Receipt only; REST snapshots never qualify |
| Independent receipt and economic audit | `pm_prospective_ledger`, `pm_prospective_cli` | Frozen cohort + receipt → external signed audit → external signed mature follower/control outcome | Exact PM-02 row adapter, as-of validated; cannot independently verify external economic truth |
| Trader Intelligence scientific readiness (draft PR #36) | `trader_intelligence_qualification`, `trader_intelligence_qualification_cli` | Existing sealed prospective ledger → independent signature/hash/as-of checks → evidence counts, complete horizon groups, descriptive paired net R | Read-only; **never** signs, creates evidence, confers A/B or marks SCIENTIFICALLY QUALIFIED |
| Trader Intelligence bounded native source snapshot (draft PR #36) | `trader_intelligence_source_capture` | Existing private candidate aliases and official Hyperliquid per-DEX/spot REST responses → immutable local SHA evidence and current source positions | No atomic book, complete NAV, trading permission or historical first-known reconstruction |
| Manager allocator | `pm_manager`, `pm02_audit`, `pm02_risk`, `pm02_campaign`, `pm02_outcomes` | Frozen PM-01 + optional independently attested prospective rows → cards, history, dependence checks and up to five proposed R seats | Research proposals, not orders |
| Protected-decision review check | `pm_governance` | Frozen JSON evidence + policy/commit binding + separately signed review + operator-pinned public key → deterministic read-only verdict | Reviewer signature only; **not** independent science, owner approval, registry mutation or trading authority. See [governance boundaries](GOVERNANCE-GATES.md). |
| Handoff | `pm_handoff`, `pm03_bridge` | SHA-pinned PM-01/PM-02/tape → dependency verdict; positions require separate sealed contract | Cannot turn risk R into position targets |
| Challenge/account simulator | `pm03_rules/account/risk/execution/attribution/memory/run/stress/cli` | Versioned **synthetic** market/PM targets/account evidence → simulated equity, event ledger, HALT and policy comparisons | One **shadow-only** account-risk supervisor |

The **source account's** realized PnL, a **historical modeled follower's** PnL, a **prospective matched follower's** net R, and a **consolidated prop shadow account's** PnL are different objects. Never add or relabel one as another.

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

## Trader Intelligence research seam (draft PR #36; 2026-11-02)

Issue #27 defines the independent read-only intelligence consumer. The WIP implementation lives on a separate feature branch, and is **not** part of released `main` until reviewed and merged. It adds only `trader_intelligence.py` (pure C/X-first assessment and stable SHA), `trader_intelligence_intake.py` (read-only historical/prospective events), `trader_intelligence_book.py` (verified full-book enrichment) and `trader_intelligence_research.py` (hypothetical 300s minute follower, conservative stop/capacity, source-independent matched-control scaffold). **No new account risk, PM-02 frozen 36 interface, broker connector, source journal, or network order transport exists.**

Original HyperX/public fills remain historical proxies and cannot become prospective first-known data. The full-book enrichment requires coherent locally observed equity and positions and explicit account-mode/spot/subaccount attestation; no source gap can be filled by inference. Unknown independence stays unknown. The reproducible benchmark has no attested unbiased PIT/holdout, independently observed matched follower economics or calibrated positive selection policy, so all comparative scientific conclusions remain **NOT_QUALIFIED** and all model-produced A/B grades remain disabled. Passing deterministic tests cannot authorize live risk.

The actual `hyperliquid-expert-ensemble` descriptive publisher modules `copy_board.py` and `copy_digest.py` are present on its active `feat/expert-wallet-execution-correctness-prospective-research` branch (VPS inspected November 2) but **not** the ensemble `main` SHA `ef8d7c1`. Its separate draft adapter must therefore be reviewed against that feature branch and not silently merged into or deployed through the production service. Default Telegram output stays the original descriptive digest. See [the evidence checkpoint](TRADER-INTELLIGENCE-CHECKPOINT-20261102.md).

## Things deliberately NOT implied by this architecture

- A public Propr instrument list is not an authenticated tradable market-ID allowlist.
- Source page pagination is not proof of a complete exchange account book, collateral, or funding.
- A day-level SHA is not exact-minute liquidity/depth.
- Positive historical source cashflow or a few modeled executable episodes is not OOS follower alpha.
- Separate wallet accounts' summed closed PnL is not a pooled challenge equity curve.
- The five-seat allocator is not the production consensus-signal engine in `hyperliquid-expert-ensemble`.
- Draft [PM-36 PR #7](https://github.com/hzminhzz/copytrade-pm/pull/7) is separate research, **not** part of this `main` description.
