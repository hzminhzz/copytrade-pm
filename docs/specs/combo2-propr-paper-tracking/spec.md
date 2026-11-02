# Spec: Combo 2 Core prospective Propr paper tracking

> ALIGN artifact | Confirmed by owner: 2026-11-02 | Status: APPROVED FOR DECOMPOSITION, NOT IMPLEMENTED
>
> This is an engineering paper/shadow contract, not a scientifically qualified strategy, a real Propr fill record, or authorization to place orders. This document defines observable outcomes and acceptance tests; implementation work is separate.

## Objective

A continuously recoverable, strictly non-order-mutating paper tracker follows the *current equity-normalized positions* of Combo 2 Core (W028, CA-008, W015), observes eligible source-wallet events as first known locally, batches each rebalance by five minutes, and produces one coherent, risk-clamped, auditable virtual follower portfolio against a nominal USD 5,000 Propr trial (#JhW9), with source-fidelity and modeled-execution differences visible.

## Why

The earlier signal-per-fill interpretation did not preserve each wallet's own sizing. Paper tracking is needed to observe what the independent managers would have held after five-minute latency, how much portfolio exposure a USD 5,000 trial can actually accommodate, and whether the *modeled* consolidated paper account survives conservative local constraints. This is useful before any separate decisions about actual challenge execution. Paper results must not be confused with source-wallet historical P&L, actual Propr account P&L, or scientifically verified follower alpha.

## Frozen decisions and terminology

- **Manager roster:** exactly W028, CA-008 and W015; independent virtual attribution per manager. Exact source addresses, subaccount identity and credential material remain in private configuration, not in Git. Changing the roster is a new versioned experiment, not an edit to the frozen 36-wallet PM-01 cohort.
- **Account binding:** Propr trial display alias #JhW9, with the full canonical account ID supplied privately and verified read-only. Nominal paper starting equity USD 5,000.00; this is not an assertion about the real account's observed balance.
- **Sleeves:** fixed USD 1,000.00 target-scaling capital per manager (USD 3,000.00 total). Remaining nominal USD 2,000.00 is unallocated capital, **not** a guaranteed stop-loss reserve or proof that leveraged positions are safe. Sleeves are sizing references, not three separately funded brokerage balances.
- **Timing:** schedule at 300 seconds after the first **locally observed** eligible leader event in a batch; further observations for the same manager/instrument before the deadline join the existing batch and do not extend it. Rebalance from the coherent latest first-known position/equity state at decision time, not from summing fills.
- **Sizing denominator:** current live source-manager account equity and the associated coherent full position state obtained using read-only Hyperliquid clearinghouseState (including applicable DEX/subaccount identity), not fixed opening equity, margin used, historical best-known equity, or an unrelated parent account.
- **25% cap:** **aggregate manager gross absolute notional per exact instrument** capped at USD 1,250.00 (25% of the frozen USD 5,000 paper reference) *before netting*. This is a conservative owner-defined local paper cap; its equivalence to an account-specific Propr rule remains **unverified**.
- **Risk accounting:** virtual paper P&L/risk and read-only actual Propr account monitoring are **separate ledgers**. Neither ledger's equity, inventory, breach, or transaction count may be silently substituted for the other. Real-account monitoring never produces paper orders.
- **Safety mode:** strictly paper only. No order creation, amendment, cancellation, close/flatten, or leverage mutation on any remote venue under any configuration, test, restart or error path. Read-only account/market queries are permitted; an informational Hyperliquid POST /info is not an order submission.

## Acceptance criteria

### A. Source, clocks and initial observation

1. All three managers are addressed by exact configured source-account identities; their equity and entire reported position set are associated with the same manager/account/DEX scope. A missing subaccount, incomplete DEX census, zero/nonfinite equity, source discrepancy, or inconsistent snapshot causes the affected rebalance to be **BLOCKED_SOURCE**, with no new paper intent or fill for that logical operation.
2. The journal records distinct UTC source-event time, first-local-receipt time, original observation/source hash or ID, scheduled deadline, source snapshot observation/receipt time, decision time and hypothetical fill time. A historical event timestamp cannot become the first-known clock or create a backdated prospective paper trade.
3. A first eligible observed event at T schedules one decision no earlier than T+300 seconds; N subsequent same-manager/instrument fills within the interval produce at most one net external paper order per exact instrument for the completed batch. Duplicated, replayed or out-of-order messages never multiply an order or reset the first deadline. Other instruments and managers may participate in the same due decision without losing their separate attribution.
4. At the deadline, sizing uses the newest *coherent* source equity and all positions available by decision time, including intervening partial close, add, reversal and fully flat outcomes. It never adds reported fill notionals as if they were separate target positions. No first-known source event means no claimed new signal.
5. Startup first reconciles and records an observed baseline **without auto-entering historical positions**; ordinary paper catch-up starts with new eligible first-known events. Any explicitly requested initial-catch-up paper experiment is separately named and audited, not disguised as a newly observed fill. Reconnect and restart must not synthesize knowledge from missed history; a gap is recorded and new opening waits for a valid fresh source state.
6. Regular read-only full-state checks and stream health checks detect missed events and manager/source drift. A detected discrepancy is identified with first-known time and audited as a correction; it is not retroactively treated as an event seen earlier.

### B. Fidelity, portfolio math and clamping

7. For each manager w and exact instrument i, preserve the signed leader exposure:
   N_desired(w,i) = (signed_leader_quantity(w,i) * as-of_source_mark(w,i) / source_equity(w)) * USD 1,000.
   Corresponding desired signed quantity = N_desired(w,i) / the follower's as-of paper execution reference price. The leader's leverage is reflected by the source notional/equity ratio. The source and follower price conventions and timestamps are logged separately.
8. The independent desired manager books remain visible before risk clamping. With USD 100,000 source equity and USD 300,000 BTC long notional, desired follower BTC long notional is exactly USD 3,000 before caps, not one arbitrary fixed trade or USD 1,000.
9. Per instrument, calculate G_i = sum across all three managers of abs(N_desired(w,i)). If G_i > USD 1,250, scale that instrument's manager targets by the same factor 1,250 / G_i, retaining the original signed proportions. Thus two opposing USD 1,000 manager targets do **not** pass the cap by netting to zero. Preserve desired, capped, rejected and executed exposure for every manager.
10. Calculate the proposed consolidated paper position only after manager-level clamping. Internally offsetting manager allocations do not create simulated external fills or double-count execution costs; the account's net external quantity equals the sum of its virtual manager quantities. Internal crosses must preserve attributed P&L and cash conservation.
11. Apply an additional *local paper* portfolio-wide gross-notional ceiling of USD 5,000.00 (1x nominal trial starting capital), as a provisional conservative initial overlay, **not** an assertion of Propr's contractual leverage limit. Gross is the sum of absolute manager notionals, including opposing virtual exposures; exceeding the ceiling scales the allowable book proportionally and records lost target fidelity. The risk policy is frozen and versioned per paper run.
12. Before new/increased paper exposure, evaluate modeled aggregate stress loss, concentration, gross exposure, margin/lot eligibility and contractual-paper headroom against a versioned scenario set. The conservative predeclared stress-loss budget must not exceed current headroom to the USD 120 / USD 240 soft limits. Unknown required stress inputs, missing hedge-break stress for offsetting managers, or an unsupported margin assumption block **new risk** without preventing legitimately executable risk reductions. Stress results are estimates, not guaranteed stops.
13. Every source instrument uses exact venue/DEX/market namespace and a reversible, verified source-to-Propr symbol mapping. Unsupported, unlisted or unmapped assets generate **SKIPPED_UNLISTED** evidence and no order for that asset; surviving instruments may be tracked only with an explicit PARTIAL_BOOK flag, source-equity denominator unchanged, and no claim of whole-book fidelity. If the omitted leg invalidates required hedge/stress assumptions, new additions depending on that hedge fail closed.
14. Use finite Decimal quantities, positive valid marks, verified tick/lot/minimum and explicit rounding toward zero on openings. Do not invent minimum quantities or silently round exposure upward through a risk cap. Exact BTC/ETH and HIP-3 namespaces are not interchangeable.

### C. Catch-up, trade gates and simulated fills

15. The net hypothetical external delta is q_allowed_target(i) minus q_paper_actual(i), where q_paper_actual is owned only by the synthetic follower ledger. A Propr read-only position, an unfilled local intent or a source-wallet position never counts as an already-executed paper fill.
16. For ordinary risk additions, stage an eligible intent only if absolute delta notional is at least USD 10.00 **and** quantity meets the exact instrument lot/minimum after safe rounding. Below-threshold deltas are deferred and considered in the next valid reconciliation; they are not labeled filled.
17. Pure reductions and full closes bypass the USD 10 notional threshold and seek 100% of executable position reduction. They still obey exact market state, lot/minimum, freshness and liquidity. Non-executable dust remains an explicit residual/exception; never assert flat while residual inventory exists.
18. A reversal is represented as a risk-reducing close of the previous side followed by a separately gated new opening of the opposite side. A negative delta against a long is not automatically a new short; position side, exact position identity and reduce-only intent are recorded correctly. Circuit breakers may allow the close and deny the opening.
19. Paper execution has independent hypothetical order/partial-fill/rejection/expiry outcomes, deterministic slippage/spread/fee/funding assumptions, capacity/participation bounds and independent marking. An approved or locally staged intent is not a fill; an acknowledgment is not proof of flat. Unfilled residuals remain pending and affect subsequent catch-up. Never equate synthetic execution with actual Propr matching or price improvement.
20. Fee, funding, price/latency drag and mark-to-market affect the paper equity and per-manager attribution. Account cash/balance, unrealized P&L, marked equity, consolidated positions, and sum of manager P&L reconcile exactly within an explicit Decimal tolerance. Source-wallet P&L, paper P&L and actual Propr account P&L appear separately, without derived challenge pass probability.

### D. Market sessions and risk latches

21. An unavailable/closed Propr market, including synthetic equity perps on weekends, rejects new paper opening/add orders. A declared bounded last-valid-mark carry may be used for valuation with a visible CARRIED_STALE flag and last-mark age; it is not an executable quote. Carry bound and market calendar are versioned inputs. After the bound expires, equity valuation is UNKNOWN and new risk is frozen. Reopen price gaps are charged to the synthetic book; closures/reductions execute only when the market is actually executable in the simulation.
22. Daily paper loss is measured from the *realized paper balance at the start of that UTC day* (00:00 UTC reset reference) to the current conservatively intrabar-marked paper equity, including unrealized loss, costs and funding. The soft freeze latches at 80% of the local 3% daily allowance: USD 120 when the daily-start balance is USD 5,000; if the daily-start balance differs, use 0.8 * 0.03 * that balance. Equality triggers.
23. Total-paper soft freeze latches when initial USD 5,000 paper reference less current marked paper equity is at least USD 240 (80% of the nominal USD 300 / 6% static maximum). Contractual hard thresholds are modeled separately and cause a permanent simulated-stage breach. The 3% daily / 6% static rules are **provisional Classic 1-Step paper assumptions** until the actual account's product/stage/rule evidence is confirmed. Do not import Turbo or Two-Step terms silently.
24. A soft freeze stops *all* new openings/additions across managers and instruments, while allowing only executable reductions and closes that cannot increase account-wide risk. It persists across process restart. A daily soft latch cannot be reset during the same UTC day; a next-day reset requires a new day-start balance, complete source/paper reconciliation, and a logged explicit operator reset. Total-DD or contractual breach never self-resets.
25. Mark-to-market/risk checks include observed intrabar adverse extremes where available; minute OHLCV is documented as a conservative proxy for simultaneous intrabar exposures, not a proven tick path. Missing critical pricing, an unpriced open position, or unknown state is not treated as zero loss. Paper risk never silently reads actual Propr balance as paper equity.
26. Separately report read-only real-account equity, daily reference, challenge type, account halt indicators and read-only inventory when known. Their status has separate ACCOUNT_MONITOR_UNKNOWN / ACCOUNT_MONITOR_BREACH values and never changes synthetic past P&L. Missing real-account credentials/health may degrade account monitoring but must not enable remote trading or falsely claim the real account is safe.

### E. Persistence, observability, fault recovery and no-mutation guarantees

27. For every eligible/blocked/skipped decision, persist source identity (redacted), source timestamps/hash, normalized position/equity, desired pre-cap targets, each clamp and risk reason, net delta, minimum-lot decision, hypothetical fill outcome, resulting simulated exposure/equity and reconciliation status. Local SQLite IntentJournal use must distinguish **shadow intent** from **paper simulated fill** and from **real broker reconciliation**. All data directories holding private account or source information remain owner-private and outside Git.
28. The execution mode has no mutation-capable Propr, Hyperliquid or broker order transport; remote order-create/cancel/close/amend/leverage endpoints are unreachable even through misconfiguration or an injected live client. Read-only official clearinghouseState queries and Propr account GET/WS inspection are allowed, and do not count as order mutations. Tests intercept/spy remote mutation attempts and assert exactly zero across normal, reject, timeout, reconnect, restart and kill-switch scenarios.
29. Decisions, intent staging and paper fill/ledger updates are idempotent and crash-consistent. Failure during an invalid/missing source snapshot, incomplete batch, risk check, journal write or simulated fill leaves the same logical operation without a partially committed target/intent/fill; retry starts from the last verified durable point. Broken receipt ordering, duplicate event, truncated journal, pending/ambiguous paper outcome and stale writer all fail closed rather than assuming an executed or flattened order.
30. Replaying the same complete first-known input stream, frozen policy, funding/fee model and market data yields byte-stable decision keys and equivalent portfolio equity and attribution. Restarts preserve pending batch due times, open simulated positions, latches, stale-price state and journal continuity; no duplicate or retroactive trades.
31. Operator output identifies ACTIVE_PAPER / DEGRADED / BLOCKED_SOURCE / FROZEN / PAPER_BREACHED, source freshness and lag, pending batches, hypothetical and filled exposure by wallet, desired-vs-allowed-vs-executed tracking error, missed/unsupported instruments, account-versus-paper monitoring, daily/total P&L and circuit-breaker reason. All reported returns carry an explicit HYPOTHETICAL / NOT SCIENTIFICALLY QUALIFIED label.
32. A dedicated fixture-driven test matrix passes at least: three-manager equity scaling; the USD 100k/300k BTC example; gross-not-net cap with opposing manager positions; proportional multi-manager clamping; account-wide gross ceiling; fixed 300s deadline and duplicate fills; add/close/reversal; USD 9.99 vs USD 10.00 trade thresholds and lot rounding; partial fills/dust; unlisted/HIP-3/market-closed/stale marks; 00:00 UTC daily reference; USD 120/240 equality touch; latching/restart; malformed/late snapshots; atomic failure and no-remote-order invariants. Verify both standalone paper math and compatibility with the repository's existing shadow/account tests.

## In scope

- A strictly paper-only, prospective Combo 2 tracking workflow; three manager/source seats and per-manager source-book fidelity diagnostics.
- First-local-observation event scheduling, coherent read-only leader equity/position observation and five-minute batch collapse.
- Equity-normalized USD 1,000 fixed-sleeve targets, exact-instrument account-gross risk clamping, consolidated netting and hypothetical follower ledger.
- Conservative local paper-risk controls, funding/fees/latency, synthetic fills and persistent freeze/recovery.
- Existing Propr example path as a **thin read-only launcher/status view**, with portfolio policy/accounting owned by copytrade-pm. Private read-only source/account acquisition can be provided through a narrow, explicit and auditable input interface.
- Reproducible synthetic test fixtures, operator-visible evidence and zero-mutation verification.

## Out of scope

- Actual remote orders, challenge execution, leverage changes, automatic flatten/cancel, credentialed live broker integration or any live trading authorization.
- Selection/ranking changes, wallet replacements, PM-02 qualification, modifications to frozen PM-01 source manifests, retrospective rewriting of first-known clocks, or claims of measured alpha.
- Changing the production hyperliquid-expert-ensemble service, adding exchange order routing, or assuming that public Propr display symbols are authorized account market IDs.
- Computing genuine challenge-pass probability, treating simulated fills as real broker executions, or bypassing broker permission/fee/risk attestation for a future separate live phase.

## Constraints

- Strictly no network mutation of broker or order state; read-only APIs only, and any paper launcher has no path to submit/close/cancel orders.
- Exact source account and Propr account identity are separately bound; never infer a first account or commit full private IDs, source wallet maps, raw account snapshots, private credentials or proprietary market bytes.
- Respect source-event vs first-known vs decision vs hypothetical fill time, local receipt hashes, immutable previous research, and no hindsight-derived prospective positions.
- Use exact native DEX/market/contract mapping and Decimal financial arithmetic, with conservative precision and stale data handling.
- Fixed nominal paper $5,000 / 3 x $1,000 allocation / $1,250 per-instrument manager-gross cap / $10 opening gate / $120 initial-day and $240 static soft freezes; any subsequent change requires a new versioned run.
- The additional USD 5,000 portfolio gross ceiling and modeled stress conditions are **owner-local research policy**, not represented as verified Propr rules. The USD 2,000 unallocated amount does not protect from gaps, leverage, or losses.
- The paper contract may run explicitly marked **PROVISIONAL_RULES** for engineering research, with immutable local rules and no claim of Propr compliance. Account-specific Propr rule attestation is required before any non-paper execution work.
- Preserve existing broker-independent, multi-provider connector contracts; do not embed wallet strategy/business logic into the provider SDK or convert copytrade-pm into a live broker client.

## Environment / prior art

- Owner project: hzminhzz/copytrade-pm, local VPS /home/quant/dev/copytrade-pm; work-unit specification lives here. At inspection 2026-11-02, local main HEAD b560db3 with existing unrelated dirty and untracked files; they must remain untouched.
- Existing account/risk/shadow concepts: src/copytrade_pm/pm03_account.py, pm03_execution.py, pm03_attribution.py, pm03_risk.py, pm03_rules.py, pm03_memory.py and pm03_run.py; their paper ledger and no-network precedent should be preserved.
- Existing equity-based intent concept: src/copytrade_pm/pm_wallet_intent.py. Its hourly historical and margin/weight alternatives are *not* this new prospective five-minute contract; the mode here is strictly equity.
- Provider integration boundary: hzminhzz/trading-connector at /home/quant/dev/trading-connector; the existing untracked connectors/propr/examples/paper_track_combo2.py currently inspects the read-only account and can stage manual ShadowGateway decisions, but does not yet observe leader events, batch, size, mark or enforce the requested automatic portfolio risk. Existing IntentJournal and ShadowGateway are provider-boundary prior art, not a source of proven paper fills.
- Canonical internal guides: docs/INDEX.md, docs/ARCHITECTURE.md, docs/RUNBOOK.md, docs/QUALIFICATION.md, docs/PM-03-shadow-account.md and the trading-connector README.md, docs/architecture.md, connectors/propr/PLAN.md, connectors/propr/OPERATOR_RUNBOOK.md.
- Dated Propr public rules in pm03_rules.py: Classic 1-Step evaluation 3% daily loss and 6% static drawdown, reset 00:00 UTC. They are published general terms, **not confirmed for the particular trial**. No account-specific proof for a 25% gross single-coin limit has been established.
- Existing data retrieval boundaries: prospective HyperX observations are not complete source-account snapshots; official read-only clearinghouseState provides the current source account/position state with its own timestamp and completeness checks. Private source evidence stays outside Git.

## Existing surface (must not break)

- copytrade-pm's frozen 36-wallet PM-01 history, consumer schema pm01_fill_only_replay_v2, PM-02 provenance/qualification gates and PM-03 synthetic offline CLI behavior.
- The existing PM-03 synthetic attribution, account risk state, fail-closed unknown outcomes, audited event store and its deterministic tests.
- trading-connector's multi-provider SDK interfaces, Propr read-only endpoints, native instrument precision and existing IntentJournal users, including Bybit and Propr flows; do not change them to enable remote mutations.
- User and other sessions' dirty/untracked source, artifacts, production services, branches and credentials.

## Open questions and pre-implementation decision rules

1. **Account-specific Propr terms / 25% meaning** — Owner: Propr/operator. The implementation uses the agreed USD 1,250 manager-gross local paper cap and PROVISIONAL_RULES label regardless; it must not declare this contractually required or remotely tradable without a dated authenticated account rule and official market-ID evidence. This does **not** block labeled engineering-only shadow research.
2. **Exact wallet/subaccount and supported Propr instrument registry** — Owner: read-only acquisition/operator. The current private alias bindings and authoritative provider instrument metadata must be reconciled before any affected source-driven paper rebalance. Missing symbols are skipped with full fidelity-loss disclosure; no guessed symbol or lot value is permitted.
3. **Market session calendars, carry duration, price and cost model, participation capacity, stress shocks** — Owner: implementation research. Before a paper run accepts new-risk targets, freeze finite source-backed/configured parameters and SHA identities in a run manifest. Unknown required parameters fail closed on the affected opening. No claim that 1m OHLCV reveals actual bid/ask or fill capacity.
4. **Propr program/stage and observed real account baseline** — Owner: operator/read-only connector. Continue with explicitly provisional Classic 1-Step *paper assumptions* while reporting actual-account status as UNKNOWN until observed; never borrow the paper starting NAV for real-account loss headroom.
5. **Future real execution** — Owner: separate explicit authorization and separate specification. No runtime flag or success here is sufficient. Current disposition remains NOT AUTHORIZED.

## Completion and evidence

- The work is **IMPLEMENTED** only when the actual prospective workflow, simulated accounting, journal and operator output meet this contract, including restart/reconnect behavior.
- It is **ENGINEERING VERIFIED** only after recorded fixture-driven tests and a read-only end-to-end paper smoke demonstrate zero mutation-capable network requests and correct accounting/clock/risk behavior.
- It is **PAPER OBSERVED** only with time-stamped first-known receipts, stable operation and separately tagged hypothetical economics.
- It is **SCIENTIFICALLY QUALIFIED** only after a separate properly controlled prospective economic qualification; this specification and passing tests do not confer that state.
- It is **AUTHORIZED FOR LIVE TRADING: NO**. No code, documentation, CI or operator shortcut may promote this work to live execution.
