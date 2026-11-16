# Source reliability, wallet health and k recalibration — design grill

**Date:** 2026-11-09  
**Status:** Q1–Q16 **OWNER APPROVED** across four design rounds. **DESIGN GRILL CLOSED**; no ready unresolved architecture decisions. Q17 optional AI-agent path is **NOT TRIGGERED**. No implementation, commit, merge, deployment, service restart, broker action, registry change, or financial release authorized.  
**Binding:** [Q1–Q3 ADR](decisions/2026-11-09-source-wallet-health-k-recalibration-round1.md); [Q4–Q9 ADR](decisions/2026-11-09-source-wallet-health-k-recalibration-round2.md); [Q10–Q15 ADR](decisions/2026-11-09-source-wallet-health-k-recalibration-round3.md); [Pydantic-native design and owners](decisions/2026-11-09-pydantic-native-domain-interfaces.md); [fixed-k policy](RISK-BUDGETED-K-SIZING-20261106.md).

## Evidence snapshot, not running authority

- Isolated design baseline: `origin/main=6c07cc6`, November 9, 2026. The original main checkout contained unrelated uncommitted work and is untouched.
- Installed `copytrade-v4-sixteen-source-0911.service`: active when inspected, PID 688048, cumulative 24 restarts, latest logged crash via `PAPER_JOURNAL_BUSY_OR_UNAVAILABLE`. The exception wrapper combines nonblocking `flock` conflict with `sqlite3.OperationalError`; **root cause and lock owner UNKNOWN**.
- Installed `copytrade-pydnative-v4-sixteen-paper-0911.service`: active when inspected, PID 624197, no systemd restarts at that snapshot. This is a virtual-paper consumer, not the source writer. Existing consumer BUSY retry does not repair upstream producer.
- Campaign: 16 virtual portfolios, 14 distinct selected parent accounts. Real ACT10 after-start opportunity canceled after GAP before T+300. Other isolated P1 trial had one authentic PARTIAL modeled attempt, no verified post-entry exit at its published audit.
- Existing Evals: 32 **synthetic** cases, no trusted real-wallet edge-decay corpus. Existing paper k is pinned by scenario/profile; no general revised-k deployment seam established.

## Settled dependency roots

- **Q1 APPROVED:** retain SQLite/source journal; diagnose and repair the current source-writer transaction seam, not introduce a new broker/DB. Causality and genuine continuity GAPs remain mandatory.
- **Q2 APPROVED:** distinct eligibility, financial attribution and strategy quality; declining equity is not automatically trading loss. Keep leader NAV optional for default fixed-k.
- **Q3 APPROVED:** k is versioned and portfolio/pod-specific; calibrate against causally cost-adjusted follower economics and existing risk; preserve every prior run and signed portfolio config.
- **Owner clarification APPROVED:** all three use **the existing domain-owned strict, frozen, versioned Pydantic v2 contract architecture** with pure reducers and existing persistence/financial owners. Not Pydantic-only at ingress and not a new monolithic global model.

## Round 2 — settled design decisions (OWNER APPROVED)

The owner approved Q4–Q9 **exactly as recommended**. These entries preserve the questions and alternatives for historical reasoning; the binding resolutions are recorded in the [Round 2 ADR](decisions/2026-11-09-source-wallet-health-k-recalibration-round2.md). Each depends only on Q1–Q3 and existing binding ADRs.

### Q4 — Writer contention classification and recovery (APPROVED)

**Question:** When a source commit is delayed, should a temporary lock abort the full 14-account observation session, or allow bounded durable progression while maintaining the original first-known clock?

**Recommendation:** Instrument lease-vs-SQLite failure cause in private diagnostics. Retain one owned serialized write path; allow bounded, classified retries for demonstrably transient BUSY/LOCKED only while original received frames remain in a bounded ordered queue, and commit them durably before any downstream source decision. An in-memory queue is **not** durable across process death. Hard divergence, corruption, inability to prove no missing frames, queue overflow or expiration fences the affected scope and emits a genuine GAP. Do not make an uncommitted in-memory frame a financial source. Avoid blindly changing the timeout.

**Alternatives:** fail fast on any BUSY (current restart problem); unbounded wait (staleness); new database/broker (scope expansion).

### Q5 — Shared socket vs account-specific fault isolation (APPROVED)

**Question:** Keep the 14-account single Hyperliquid subscription socket, or split into multiple connection groups to reduce correlated continuity gaps?

**Recommendation:** Preserve the single bounded official source session initially, but separate account-specific schema/scope quarantine from genuine shared transport failure. Track socket events and account-local epochs independently; partition sockets only after measurements prove an external shared failure and show the incremental connection/WS budget is feasible. A shared physical disconnect remains a genuine gap for every affected account.

**Alternatives:** one connection per wallet immediately (resource/provider budget); ignore shared transport gaps (invalid T0).

### Q6 — Health-monitoring universe, evidence source and cadence (APPROVED)

**Question:** Should monitoring cover only 14 live-source accounts, or registered research wallets too? How frequently should different observations be taken without widening the fragile official socket?

**Recommendation:** Monitor the current private SQLite registered wallet universe by **read-only, deduplicated and rate-budgeted** scheduled evidence checks (initial daily portfolio-wide status), plus higher-frequency status for existing selected paper wallets when their official source receipts are available. Do not subscribe every registered wallet to the 14-account source socket. Distinguish request success, evidence age, provider completeness and account identity. The 14 selected source accounts remain the only initially admitted official position-first live source scope.

**Alternatives:** 14-only monitoring misses deteriorating research candidates; new WS for every registry wallet risks provider/socket pressure.

### Q7 — Capital/flow attribution and the $1,000 rule (APPROVED)

**Question:** Which economic account value can legitimately determine a $1,000 eligibility floor, and what should happen when deposits, withdrawals or funding coverage are incomplete?

**Recommendation:** Bind the floor to a declared selected-account-equity measure with original source/DEX scope, provenance and first-known time. Do **not** substitute sum of unrelated DEX margin summaries, partial equity feeds, spot/vault NAV or stale values. Classify missing coverage as `EQUITY_UNVERIFIED`, not `BELOW_FLOOR` or `LIQUIDATED`. Retain explicit flow-attribution categories with unallocated residual and no trading-loss inference. Decide future entry-suspension effects after this evidence policy is approved.

**Alternatives:** use whole-wallet NAV as universal fixed-k blocker (contradicts existing policy); infer losses from simple equity delta (false decay).

### Q8 — What constitutes economically meaningful edge decay? (APPROVED)

**Question:** How should new evidence separate a short volatile week from a lasting deterioration in the *follower's* attainable net economics?

**Recommendation:** Use a predeclared multi-horizon assessment: 90-day historical context when available, rolling 30-day confirmation and recent 7-day **warning** for fast deterioration. Base primary evidence on T+300 follower net outcomes with costs and risk-aware denominators; retain historical fill-derived episodes only as labeled retrospective screens. Require minimum independently observed episodes/active days, PIT train-vs-forward separation, and effective sample size before positive `EDGE_DECAY_CONFIRMED` or k-increase claims. If data are thin, report `INSUFFICIENT_EVIDENCE`; do not auto-increase k from a favorable week. Exact thresholds and test statistics remain a later node.

**Alternatives:** 7-day source PnL alone (noisy); equity change alone (flow confusion); forcing every wallet to have impossible 90-day prospective receipts immediately (blocks useful diagnostics).

### Q9 — Who may activate a new k version? (APPROVED)

**Question:** After the engine proposes hold/decrease/increase, should it immediately resize active portfolios, or create a new immutable release pending policy-specific authorization?

**Recommendation:** Pydantic validates a versioned **research proposal** and its evidence. Only a separately authorized, registry/policy-pinned **portfolio k release** can change a running SHADOW configuration; no automatic rewrite of active journal records, historical results or preexisting k. Enable deterministic automated proposals and risk-off recommendations; do not auto-increase deployed k, repin Guardian, or infer live/demo approval. The exact future activation permissions for automated shadow-only decreases vs increases remain a following decision.

**Alternatives:** edit the current k in place (destroys attribution); unconditional automatic sizing increases (unqualified evidence); forbid all research proposals (defeats automation).

## Round 3 — settled design decisions (OWNER APPROVED)

The owner approved Q10–Q15 **as recommended**. These entries preserve the rationale, alternatives and boundaries; the binding decisions are in the [Round 3 ADR](decisions/2026-11-09-source-wallet-health-k-recalibration-round3.md). The Prefect technology direction is approved **conditionally on demonstrated workload value**, but no installation or workflow execution was authorized.

### Q10 — What proves the source-writer repair is reliable? (APPROVED)

**Prerequisites:** Q4, Q5.

**Question:** Require days of uninterrupted uptime before acceptance, or define a bounded engineering gate plus independent live SHADOW evidence?

**Recommendation:** Use one adversarial source-writer acceptance suite (lease collision, SQLite BUSY during WAL/setup/commit, cancellation, queue overflow, stop/restart, source/consumer replay), proving no duplicate T0, no accepted uncommitted frame, exact preserved first-known clocks and intact stream SHA chain. Follow with a **bounded live SHADOW canary** of the unchanged 14-account scope and real source-to-paper journal integrity. Track service restarts, queue high-water, age of committed receipts and genuine GAP recovery separately. A real post-start T+300 entry/exit is required to claim complete *forward economic lifecycle* acceptance but **not** to prove that the repaired writer survives contention; do not gate the engineering fix on waiting arbitrarily for a wallet to trade. Set numerical latency/backlog/error budgets after measuring real baseline rather than inventing them.

**Alternatives:** pass purely because a systemd process is active; require an arbitrary multi-day soak as a release veto; skip real canary entirely.

### Q11 — What should wallet-health findings automatically do? (APPROVED)

**Prerequisites:** Q6, Q7, Q8.

**Question:** Should a confirmed equity-floor breach, liquidation, inactivity or edge deterioration automatically exclude wallets or halt all open positions?

**Recommendation:** Adopt a **graded capability response**: confirmed severe capital/identity eligibility failure prevents *new wallet selection* and may suspend new-risk admission **only under an explicitly versioned active-shadow participation policy**; do not silently write a registry exclusion or clear unresolved positions. Unknown/stale capital evidence causes an alert and missing-evidence status rather than an inferred loss or automatic global ban. A 7-day edge warning triggers review or a **risk-off k proposal**, not a forced liquidation. Real source continuity GAPs still independently fence new T+300 entries through the existing source policy. Recovery requires documented fresh evidence and a bounded probation decision; manual governance still owns durable exclusions. Decide precise time thresholds and the action for each evidence class before code.

**Alternatives:** one global wallet `ACTIVE/DEAD` flag; automatic removals for any balance decline; silently close held exposure on a monitoring alert.

### Q12 — How should the k estimator balance speed and statistical validity? (APPROVED)

**Prerequisites:** Q8, Q9.

**Question:** Size k from a fixed recent drawdown ratio, an extreme-loss model, or a robust constrained simulation over executable follower outcomes?

**Recommendation:** Use **deterministic constrained scenario evaluation**, not a learned end-to-end black box. For each (portfolio,pod), re-evaluate candidates across the native PM03/PM04 cost/risk model with T+300 PIT timing, volume/capacity uncertainty, exact lot sizes, adverse-price stress, funding and cross-pod correlation. The `$200` per-pod example is a *nominal trigger*, not a guaranteed bound. Require OOS/forward sample sufficiency before proposing increases. For sparse evidence, `HOLD` / `DECREASE_REVIEW` rather than `INCREASE`. Reuse Polars/DuckDB vectorized screening and exact Decimal application at the financial boundary; do not create per-row Pydantic bars or another simulator. Choose sample minima, maximum per-release k delta, loss quantile/stress set and performance objective in the approved specification.

**Alternatives:** k = budget / most recent wallet drawdown; directly maximize 7-day source gross PnL; force all wallets to use one global k.

### Q13 — How does a k version become effective with pending or open exposure? (APPROVED)

**Prerequisites:** Q9.

**Question:** Should a new k immediately resize existing exposure, become active only when flat, or apply only to future eligible entry opportunities?

**Recommendation:** Keep **policy version provenance at each committed modeled effect**. Default to **future-opportunity activation at an explicit effective time**, with a frozen k for an already-open T+300 opportunity until it resolves or is canceled; never recalculate original T0 or create a second attempt. Existing follower inventory remains accounted for at original historical effects and is not assumed flat because k changed. An explicitly authorized risk-reducing action may reduce open exposure under the existing PM03/04 guards; no automatic new-risk catch-up or retroactive financial journal rewrite. A newly admitted portfolio version must have an immutable release/effective-time record and a deterministic post-restart read rule. Decide whether a new run or a versioned policy change inside one run is required after auditing the actual journal configuration contract.

**Alternatives:** edit `k_by_pod` in-place and replay all prior entries; immediate uncontrolled resize; require every active strategy to flatten before publishing any recommendation.

### Q14 — Where do monitoring status and approvals live? (APPROVED)

**Prerequisites:** Q6, Q9.

**Question:** Extend Grafana and the existing SQLite/capability read models, or introduce a new live wallet-state service/UI?

**Recommendation:** Publish **read-only Pydantic-validated, as-of/evidence-bound projections** from the current registry, source/journal and immutable research outputs. Grafana shows separate `source continuity`, `capital attribution`, `eligibility`, `edge warning`, `k proposal`, `release effective`, and `Guardian authorization` dimensions; never blend them into a green health score. Alerts and operator acknowledgements have independent delivery/ACK evidence and cannot issue trading commands. Preserve private wallet-address redaction and avoid writing new financial authority into dashboard tables.

**Alternatives:** create a second current-wallet registry; let UI status directly change k or reset financial HALT.

### Q15 — Prefect vs Temporal vs systemd for durable research jobs (APPROVED)

**Prerequisites:** Q6, Q9 (also compatible with Q4/Q5 source separation).

**Question:** Should the new health/attribution/recalibration schedule remain `systemd` timers, adopt **Prefect 3**, or move all source and finance state machines into Temporal?

**Recommendation:** **ADOPT Prefect 3 for bounded, periodic, research-only workflows** once the actual workload justifies independent scheduling, retries, status and human review: daily deduplicated wallet checks; PIT flow attribution; 7/30/90-day follower-health scoring; weekly or event-driven k proposal jobs. Start as a small, isolated, version-pinned deployment on the existing VPS, separate from main `copytrade-pm` source/finance dependencies. Self-hosted Prefect orchestration metadata must be **separate from PaperJournal/registry financial authority**; Prefect's flow/task caches cannot validate original receipts, guarantee external side-effects exactly once or authorize revised k. Bind cache/retry identity to wallet ID, as-of, source/evidence SHA and algorithm version; operations must be idempotent at existing authorities. If just one or two simple deterministic jobs exist, retain systemd timers until Prefect actually removes operational burden.
  
  **Do not adopt Temporal for the present three enhancements.** Temporal offers event-history replay and strong durable long-running multi-step workflow coordination, but it adds a separate server/service/worker/task-queue and workflow-determinism burden. Revisit only for genuinely long-running, cross-service/human-approval workflows whose progress must survive prolonged outages and whose needs cannot be met safely by Prefect + existing journals. **Never replace the official position-first T+300 loop or PM03/04 with either engine.**
  
  **Pydantic clarification:** `Pydantic Validation` (existing strict domain models) is not `Pydantic AI`. Prefect `@flow/@task` works with ordinary deterministic Python; `PrefectDurability` from `pydantic_ai.durable_exec.prefect` applies **only if a real Pydantic AI agent is later introduced inside a Prefect flow**. It makes model/tool/MCP calls resumable but grants no financial authority. Keep AI/Prefect optional to the observer, rather than importing orchestration dependencies into high-frequency source ingress.
  
  **Official product references checked 2026-11-09:** [Pydantic AI durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/), [Pydantic Prefect integration](https://pydantic.dev/docs/ai/capabilities/durable_execution/prefect/), [Pydantic Temporal integration](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/), [Prefect self-hosting](https://docs.prefect.io/v3/), [Temporal workflows](https://docs.temporal.io/workflows).

**Alternatives:** Temporal-first rewrite for research/official source; mandatory Pydantic AI for deterministic scoring; Prefect task cache treated as proof of source-financial exactly-once; installing Prefect before it yields measurable scheduling/recovery benefit.

## Round 4 — final decision (OWNER APPROVED — CLOSED)

### Q16 — What is the end-to-end acceptance, sequencing and rollback contract? (APPROVED)

**Prerequisites:** Q10–Q15 approved. This is the only ready question; no autonomous Pydantic AI diagnostic runtime was approved, so Q17 remains **conditional/not triggered**. See the [independent Prefect × Pydantic technical research](research/2026-11-10-prefect-pydantic-architecture-fit.md) before approving Prefect-related release steps; Pydantic AI durability does not establish financial exactly-once or automatic recovery from every Prefect CRASHED state. See also [QuantumFlow's large-scale negative whale-copying study and its Copytrade-PM implications](research/2026-11-10-quantumflow-hyperliquid-whale-tracking.md); it is external author-reported evidence, **not** a reproduced empirical verdict for the current T+300 cohort.

**Question:** Should the three capabilities ship as one all-or-nothing cutover, or as separately reversible, evidence-gated releases whose operational status and scientific claims remain independent?

**Recommendation:** Approve a **three-track, reversible delivery** with common Pydantic-native domain contracts and explicit evidence/authority boundaries, not one new monolithic service.

1. **Source reliability (first operational priority):** diagnose the actual lease/SQLite failure in the original source producer; add only bounded classified writer recovery and account-correct GAP handling. Prove with deterministic fault tests, real source/consumer chain checks, first-known T0 preservation, restart and adverse concurrency. Deploy only through its own separately authorized, pinned SHADOW producer canary, backed up and with a verified rollback to previous evidence heads. Do **not** treat an active process as continuity proof, or require waiting for an arbitrary live wallet exit to declare the writer bug fixed.
2. **Wallet monitoring (can develop in parallel):** read-only Pydantic evidence models and an independent Polars/SQLite-as-of evaluation of the **entire registered universe**, starting daily, with more frequent assessment only for already selected accounts and with explicit source-rate budgets. Demonstrate withdrawal/top-up vs loss/liquidation distinction and missing-data abstentions on independently labeled real retrospective data and future forward receipts where available. Expose independent eligibility/attribution/edge findings via Grafana. Activate alerts/read-only views first; **do not** silently exclude, liquidate, change subscribed accounts or mutate paper risk.
3. **Versioned k research and guarded release (after evidence available):** generate deterministic portfolio/pod-specific `HOLD/DECREASE/INCREASE` Pydantic proposals using PIT, T+300 modeled net returns with costs, stressed PM03/PM04 risk, OOS sufficiency and immutable provenance. Verify restart/cursor/idempotent generation and multi-portfolio wallet independence. Ship a proposal-only mode first. A subsequent immutable **SHADOW-only** release is an independent authorized decision, effective only for future eligible opportunities; preserve old held inventory and pending-intent k. Automatic increases and any Guardian/demo/live release remain separate and unauthorized.
4. **Optional Prefect deployment:** prove the scheduling/retry and operator-evidence benefit over simple systemd timers with actual job count/cost/latency before installing Prefect 3. If beneficial, run it from a pinned isolated VPS environment, secured with independent metadata/credentials, backup and rollback. Prefect cannot own original source T0/continuity or any finance state. Temporal remains deferred, Pydantic AI optional and not required for deterministic monitoring.
5. **Acceptance and truthful release report:** require separate badges/facts for **IMPLEMENTED**, **ENGINEERING VERIFIED**, **SHADOW DEPLOYED**, **PROSPECTIVE LIFECYCLE OBSERVED**, **SCIENTIFICALLY QUALIFIED** and **TRADING AUTHORIZED**. Record source/market/selection/algorithm/contract hashes, tested commits, private receipt provenance, old/new active service pins, test/perf evidence, failed/unknown gates and exact rollback conditions. Do not conflate correct simulation with independently executable follower PnL.
6. **Approved QuantumFlow-informed economic acceptance gate:** For wallet selection and **positive k** evidence, compare delayed **follower net** economic outcomes against cash/no-trade and relevant matched-wallet/coin controls with pre-registered as-of rosters, disclosed trial counts, separate unseen OOS/forward periods and a three-price delay/adverse-cost sensitivity. Do not mistake raw gross leader PnL, recent hit rate, whale size or frequent fills for copyability. Label historical reconstructed first-known as estimates. This gate **must not delay acceptance of the independent source-writer correctness fix**.

**Why:** The source reliability repair can unblock continuous T+300 research without waiting for an unvalidated wallet-scoring system or k promotion policy. Read-only diagnostics can be useful before positive alpha evidence exists. Prefect can scale the noncritical research workflows without being introduced into the financial critical path.

**Rejected alternatives:** all-or-nothing rewrite; replacing the source service with Prefect/Temporal; converting research k proposals into active sizing automatically; rewriting frozen journals to apply new k; declaring scientific alpha from passing tests or retrospective source PnL.

**Status:** Q16 **OWNER APPROVED** with the additional economic gate described above. The binding final [design-closure ADR](decisions/2026-11-10-source-wallet-health-k-recalibration-design-closure.md) captures acceptance boundaries, alternatives and remaining evidentiary unknowns. The in-scope design frontier is **EMPTY**. Implementation specification, tickets, code, commits, merges, installation, deployments or financial promotion require separate explicit tasks.

### Q17 — Conditional agent diagnostic fork (NOT TRIGGERED)

Only reopen if the owner later explicitly chooses a real Pydantic AI diagnostic agent. Its tool access, private PIT evidence, model-error behavior, independent labeled corpus and Pydantic AI durable Prefect integration would require a distinct decision round. Deterministic monitoring and source reliability do not depend on it.

## Edge-case probes to settle before an implementation specification

1. Source socket receives frames at T0 and T+180; SQLite is BUSY at T+181, queue grows, writer recovers at T+245. May T+300 be attempted only if every required frame was actually preserved and committed with original receipt clocks?
2. An uncommitted frame is lost after process death and the socket reconnects. Baseline must not be promoted to a post-baseline opportunity regardless of favorable market movement.
3. One account reports unknown critical DEX shape, the other 13 are valid; do not globally wipe independent healthy accounts unless the physical transport or identity mapping is ambiguous.
4. Equity falls 60% after withdrawal, source positions remain unchanged, and follower modeled PnL is positive; classify capital and quality independently.
5. A whale receives a large top-up and a profitable last seven days but only two follower episodes; no automatic k increase.
6. The same source wallet is shared by P1 and P14 but has different k and loss budgets; a recommendation for P1 must not alter P14.
7. A k revision is published while an entry opportunity is pending at T+180 or follower exposure remains open; old event time/k provenance must survive and no unreviewed immediate new risk may be created.

## Record state

**Design closure:** Q1–Q16 are owner-approved and documented in four linked ADRs with updated domain terminology. No unresolved ready design questions remain. Conditional Q17 would require a distinct new owner request for a genuine Pydantic AI diagnostic agent; it was not activated by Prefect research scheduling. Prefect remains only a conditional research-orchestration direction, neither installed nor authorized for deployment. No implementation, specification, commit, merge or deployment was initiated by this closure.
