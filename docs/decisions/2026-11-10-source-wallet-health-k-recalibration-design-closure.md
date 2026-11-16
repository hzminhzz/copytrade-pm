# ADR — Final delivery and economic-acceptance boundaries for the Pydantic-native wallet program

**Date:** 2026-11-10  
**Status:** **OWNER APPROVED — Q16; DESIGN GRILL CLOSED (Q1–Q16)**. Design approval only. Not permission to implement, install, commit, merge, deploy, activate paper k changes, modify Guardian, or place orders.  
**Supersession:** This closes the open Q16 frontier in [the design grill](../SOURCE-WALLET-HEALTH-K-GRILL-20261109.md). Approved prerequisite decisions are [Round 1 Q1–Q3](2026-11-09-source-wallet-health-k-recalibration-round1.md), [Round 2 Q4–Q9](2026-11-09-source-wallet-health-k-recalibration-round2.md), and [Round 3 Q10–Q15](2026-11-09-source-wallet-health-k-recalibration-round3.md).  
**Research considered:** [Prefect and Pydantic native-durability assessment](../research/2026-11-10-prefect-pydantic-architecture-fit.md) and [QuantumFlow's Hyperliquid whale-copying study / critical audit](../research/2026-11-10-quantumflow-hyperliquid-whale-tracking.md). The latter is external *author-reported* evidence, **not** an independently reproduced finding for these selected wallets.
**Inspected repository baseline:** isolated design worktree derived from `origin/main=6c07cc6d36099135881be27a072c426a52a24f24`. Recheck live revisions, owners and services before writing an implementation spec.

## Decision: three independently reversible delivery tracks, not an all-or-nothing migration

**Track A — Official source reliability (first operational priority; independent release acceptance)**

Keep the official selected-account native Hyperliquid position observer under systemd and existing `PersistentAccount`/`PaperJournal`/SQLite ownership. Diagnose the actual `flock` vs SQLite BUSY/LOCKED vs WAL/transaction vs storage cause before choosing bounded retry semantics. Preserve first-local-known T0 and raw evidence identity, selected-scope generations and chain integrity. Test crash-before-commit, replay, queue overload, account quarantine, socket disconnect and source/consumer idempotence. A true continuity GAP **must** fence new T+300 risk; it cannot be erased or fabricated as observation continuity.

Adversarial engineering acceptance and a separately authorized, reversible 14-account SHADOW producer canary can demonstrate writer reliability **without waiting for a real wallet to trade**. A later authentic first-known entry AND exit is required to report full prospective economic lifecycle evidence, which is a distinct gate. Do not claim writer reliability just because systemd is active. Backup and verify release and rollback of service pins/evidence heads independently. No Prefect dependency in this critical source/finance path.

**Track B — Wallet-health monitoring (read-only rollout; can develop in parallel)**

Use the **whole registered wallet universe** for periodic, rate-budgeted monitoring without widening the initial 14-account official position stream. Retain identity, source freshness, capital evidence/flow attribution, source continuity, follower net-economic quality and portfolio membership as **separate as-of facts**, with explicit `UNKNOWN` or `INSUFFICIENT_EVIDENCE` statuses. Distinguish withdrawals, top-ups, losses, funding, inactivity, liquidation and unsupported assumptions. The previously selected `$1,000` participation floor is evaluated only on genuinely verified capital scope; **leader whole-wallet NAV remains optional** under the fixed-k sizing contract.

Initially provide deterministic read-only health results, Grafana projections and alerts. Do not silently blacklist/exclude selected wallets, force liquidation, mutate PM03/04 inventory, or grant trading permissions. A future versioned participation restriction requires independent authorization; source GAP new-risk fences continue to apply regardless of wallet score.

**Track C — Portfolio/pod-specific k recalibration (proposal-first rollout; later governed release)**

Use the existing `FIXED_K_NATIVE_QUANTITY`, PM03/PM04 financial rules, independent follower pricing and portfolio/pod-specific risk budget. Recalculate k candidates only from causally available, cost-adjusted follower outcomes, capacity and market impact uncertainty, concentration/correlation, exact lot constraints, daily/trailing restrictions and nominal pod loss triggers (not hard loss guarantees). The estimator proposes `HOLD`, `DECREASE`, `INCREASE` or `INSUFFICIENT_EVIDENCE` through immutable, versioned Pydantic evidence-bound research records.

Deploy a **proposal-only** version first. An eventual new k is a separately reviewed, immutable SHADOW portfolio release effective prospectively for new eligible opportunities; an already pending T+300 intent retains its original k/T0, and held inventory remains accounted under original financial effects until properly reconciled or risk-reduced through existing permissions. No automatic deployed k increases, historical result rewrites, live/demo/Guardian authorization or broker orders follow from this program.

## Binding QuantumFlow-informed economic-acceptance addendum (OWNER APPROVED)

This additional **economic reproducibility gate** applies to wallet **quality/copyability claims and positive k proposals**, not to Track A's source-writer correctness. It does not turn exploratory negative results into a blanket prohibition on wallet research.

1. **Define follower copyability:** a wallet's selected-scope position strategy must be attainable with the actual **first-local-known T+300** policy and the follower's independently observed price, risk, fees, slippage, funding where available, turnover and capacity assumptions. Visible whale notional, leader gross PnL, high rank or next-month hit rate **do not alone establish net follower edge**.
2. **Record the search:** freeze candidate registry/cohort/portfolio versions and selection-as-of; retain *all* attempted ranking, portfolio and k variants and selection filters, including rejected candidates. Do not pick a favorable testing window after examining its results. The eventual statistical acceptance method must account for repeated trials/selection and temporal dependence.
3. **Use inexpensive fast screening first:** historical fill-reconstructed episodes and Polars/DuckDB can pre-screen hold durations, cost viability and economics. Historical fills without original first-known receipts remain labeled **retrospective estimated timing**; screening does not claim genuine prospective source observation. Do not reject maker-heavy wallets solely by fill count.
4. **Apply three execution-price sensitivity cases to surviving candidates:** (a) first eligible **1m** price after T+300, (b) one **additional minute** delayed, and (c) adverse execution-price/slippage stress. Use the existing PM03/PM04 financial and risk contracts, with no competing invented broker simulator; quantify slippage/impact/funding uncertainty rather than assume them away. For official prospective paper, use actually received source and market clocks, not retrospective synthetic T0.
5. **Independent economic controls:** compare cost-adjusted delayed follower economics against (a) cash/no new risk, (b) matched/random selection with comparable opportunity/cost exposure where meaningful, and (c) coin/market or matched-asset baseline when relevant. Require positive **marginal portfolio-level economic value** and a credible selection-conditioned net result before an `INCREASE` recommendation. A negative/uncertain benchmark means hold/review/no risk increase, not automatically no trade across all research.
6. **Preserve genuine unseen evidence:** split selection from out-of-sample / forward evaluation using PIT data, independent sample sizes and regime/temporal variation. The scientific significance/economic threshold, minimum episodes, trial-adjusted confidence, and stress magnitudes are implementation-spec parameters to derive from evidence, **not numbers invented by this ADR**.
7. **Keep evidence classes separate:** engineering source validity, eligibility/flow attribution, retrospective estimated PnL, OOS follower economics, real prospective modeled entry/exit lifecycle, scientific qualification and protected trading permission are separate claims. Valid Pydantic contracts do not imply profitable copying.

**Crucial sequencing rule:** do **not** block Track A reliability fixes or simple Track B descriptive/alerting work on full economic qualification. The stricter gate binds *positive copyability claims and increases in allocated k*, not ordinary fast research screening, conservative proposed decreases, or source preservation.

## Cross-cutting implementation and operational boundaries (design approved)

- Reuse the **existing strict, frozen, explicitly versioned Pydantic v2 source/research/paper domain models**, deterministic reducers and provenance policies; normalize Decimal/UTC only in designated adapters. Original raw receipts remain immutably hashed in their source owner, not reconstructed from `model_dump`.
- Use **Polars/DuckDB/Parquet** for scalable point-in-time features and historical screens; PM03/PM04 and existing SQLite registry/portfolios remain the financial and selection authorities. Do **not** introduce a second wallet registry, ledger or custom simulator.
- **Prefect 3 is conditionally adopted** for bounded *research-only* wallet monitoring, attribution and k-proposal workflows when measured scheduling/diagnostic value exceeds a few systemd timers. Test a pinned isolated VPS deployment, own metadata and access controls, provider lease enforcement, replay/idempotency, crash recovery, resource impact, operational backup and rollback **before separately authorizing installation**. Prefect does not own T+300 clocks, official source continuity or financial side effects. Temporal deferred; Pydantic AI agent not required.
- Grafana may project distinct read-only health/economic/copyability/portfolio states from the correct existing authority. It may not make or approve financial decisions.
- Keep tracks independently reversible: pinned versions and journal heads, preserved immutable records, observable status and rollback with no rewrite of original historical evidence.
- Report **IMPLEMENTED**, **ENGINEERING VERIFIED**, **SHADOW DEPLOYED**, **AUTHENTIC PROSPECTIVE LIFECYCLE OBSERVED**, **SCIENTIFICALLY QUALIFIED**, and **TRADING AUTHORIZED** as different conclusions supported by different evidence; never silently promote one into another.

## Alternatives rejected

- One monolithic Prefect/Temporal replacement for source, research, paper and financial authorities.
- Blocking an urgent source-writer fix on an unrelated full entry/exit lifecycle or a statistically qualified wallet.
- Using leader gross profit, whale size, very short recent returns or visually attractive curves as sufficient evidence to increase k.
- Treating a top wallet found after screening hundreds as OOS evidence; ignoring rejected trials, risk costs or missed five-minute entry prices.
- Modifying previous k versions, replaying pending T+300 intents as new opportunities, or replacing guardian independent authorization.
- Claiming this external article's large-population null definitively falsifies the specifically curated 5m delayed cohort.

## Acceptance, remaining factual unknowns and next action

**Decision tree:** All ready, in-scope Q1–Q16 are **approved/closed**. Q17 (optional Pydantic AI diagnostic agent) is **NOT TRIGGERED** by Prefect's deterministic research use; a separate user decision would be required to pursue it.

**Remaining factual unknowns to validate at implementation planning:** actual source-writer lock ownership and recoverability; current VPS/HEAD drift; authentic funding/provider flow coverage and their PIT completeness; independent wallet-health labels; measured real post-T+300 follower price/capacity; sufficient genuine out-of-sample/prospective follower episodes; cost and retry budget measurements; journal compatibility for activating k without retroactive mutation; Prefect operating overhead versus systemd. These are **evidence requirements**, not new unresolved architectural decisions.

**Next action when explicitly requested:** synthesize the approved design into a versioned implementation-ready specification, then dependency-aware tickets / execution plan. No spec, coding, test run, commit, merge, deploy, registry change, risk release or trading action is authorized by the architectural approval alone.
