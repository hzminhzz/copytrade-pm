# Architecture: evidence, manager governance, shadow account

**Scope:** the code on `copytrade-pm/main` at `1434f55` (2026-10-31). This repository was history-filtered from `hyperliquid-expert-ensemble` (see [PROVENANCE](PROVENANCE.md)). It is **not** the production wallet tracker or Telegram consensus engine. Its research code must never import a live broker/order gateway. Read [INDEX](INDEX.md) first.

## Responsibility boundaries

| Boundary | Owner | Inputs → outputs | Authority |
| --- | --- | --- | --- |
| Wallet candidate discovery and initial vendor roster | **Upstream/private** wallet research, outside this package | Wallet addresses, alias mapping and vendor-listed instrument roster → frozen cohort source manifests | Discovery only; not scientifically qualified |
| Frozen historical source | `pm_sources`, `pm_source_audit`, `pm_hyperx_overlay_audit` | Owner-private HyperX pages and SHA manifests, optional fresh independent generations → 36 immutable source identities and diagnostic coverage | Historical vendor knowledge, **not** first-known trading signals |
| Exact minute market evidence | `pm_shadow.VerifiedHyperliquidMinuteSource`, `pm_market_audit`, `pm_propr_scope` | Native Hyperliquid 1m Parquet under *ml4t-data* plus public display scope → market-day integrity/availability | Data coverage; not L2 capacity or Propr order-ID authorization |
| Wave C cohort extension | `pm_wave_c`, `pm_portfolio.validate_38_wallet_cohort` | Two independently audited vendor generations + private identity map + replay-window decision → versioned 6+10+20+2 research cohort | Historical vendor knowledge only; frozen 36 untouched, no first-known clock |
| Historical whole-wallet PM-01 | `pm_fill_replay`, `pm_fill_cards`, `pm_fill_tape` | Exact source fill books + minute marks → 36 wallets × 5/15/60m hypothetical follower rows; observed signed book tape | `pm01_fill_only_replay_v2` is **hindsight** |
| Prospective collection | `pm_hyperx_forward`, `pm_hyperx_rest_forward` | Bounded read-only vendor WS/REST → immutable first-local receipt files | Receipt only; REST snapshots never qualify |
| Independent receipt and economic audit | `pm_prospective_ledger`, `pm_prospective_cli` | Frozen cohort + receipt → external signed audit → external signed mature follower/control outcome | Exact PM-02 row adapter, as-of validated; cannot independently verify external economic truth |
| Manager allocator | `pm_manager`, `pm02_audit`, `pm02_risk` | Frozen PM-01 + optional independently attested prospective rows → cards, history, dependence checks and up to five proposed R seats | Research proposals, not orders |
| Handoff | `pm_handoff`, `pm03_bridge` | SHA-pinned PM-01/PM-02/tape → dependency verdict; positions require separate sealed contract | Cannot turn risk R into position targets |
| Whole-wallet E0 source-intent seam | `pm_wallet_replica` | Independently audited complete account positions, equity, first-known clock → one-scalar intended source book and staged fidelity measures | Research target only; NEVER authenticates a self-declared source audit or authorizes orders |
| Challenge/account simulator | `pm03_rules/account/risk/execution/attribution/memory/run/stress/cli` | Versioned **synthetic** market/PM targets/account evidence → simulated equity, event ledger, HALT and policy comparisons | One **shadow-only** account-risk supervisor |

The **source account's** realized PnL, a **historical modeled follower's** PnL, a **prospective matched follower's** net R, and a **consolidated prop shadow account's** PnL are different objects. Never add or relabel one as another.

## Source-fidelity E0 baseline

For A/B/C future studies, the primary research object is one complete signed, point-in-time wallet book. Each fill is an update to that book, not a fresh independently sized episode. `pm_wallet_replica.replicate` applies one source-equity-to-pod-capital factor across all positions and explicitly refuses incomplete, retrospective/unverified or noncausal inputs. `pm_wallet_replica.fidelity` distinguishes intended vs risk-approved vs executed position tracking. The PM-03/PM-04 simulation retains sole account authority. The legacy partial-episode studies remain immutable historical diagnostics; see [E0 research migration](E0-WALLET-REPLICA.md).

## PM-01 historical path

`pm_sources.load_cohort(root)` is deliberately fixed to **6 original + 10 Wave1 + 20 Wave2** and references multiple authoritative private manifests. It reconciles alias/address collisions and vendor pagination; it does **not** accept an arbitrary fresh wallet address. `pm_wave_c.load_research_cohort(root)` is the only extension path: it keeps those 36 bytes intact, requires an independently audited two-wallet generation with a versioned roster, and returns exactly 38 identities. `pm_source_audit.audit()` validates raw page hashes and selected market defects.

`pm_fill_replay.run(root, market_root, risk_budget, hyperx_generations)` loads the vendor-listed exact instrument roster and signed position-before/after fill chains. It withholds an initial book until each listed leg can be anchored; post-anchor discontinuities, missing marks, missing native markets and volume constraints yield `BLOCKED_*`, not manufactured trades or flat exposure. The 5/15/60-minute delays model hypothetical next-minute-open follower actions, not actual first-known receipt or observed Propr fills. `risk_budget=0.01` means **1% gross hypothetical notional**, NOT 0.01 R and NOT probability of passing a challenge.

A separate `pm_fill_tape` materializes a **historical-only** `pm01_observed_book_tape_v1`. Its account snapshots may be useful for source diagnostics but `pm03_actionable_targets_available=False`. A Rust observation path (`pm_portfolio` + `pm_research`) exists as a **separate/legacy** replay boundary; it is not a prerequisite for the fill-only 36-wallet research.

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

## Source and package topology

```text
src/copytrade_pm/
  pm_sources.py / pm_source_audit.py       frozen cohort and source SHAs
  pm_wave_c.py                             versioned 2-wallet extension (6+10+20+2)
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

## Things deliberately NOT implied by this architecture

- A public Propr instrument list is not an authenticated tradable market-ID allowlist.
- Source page pagination is not proof of a complete exchange account book, collateral, or funding.
- A day-level SHA is not exact-minute liquidity/depth.
- Positive historical source cashflow or a few modeled executable episodes is not OOS follower alpha.
- Separate wallet accounts' summed closed PnL is not a pooled challenge equity curve.
- The five-seat allocator is not the production consensus-signal engine in `hyperliquid-expert-ensemble`.
- Draft [PM-36 PR #7](https://github.com/hzminhzz/copytrade-pm/pull/7) is separate research, **not** part of this `main` description.
