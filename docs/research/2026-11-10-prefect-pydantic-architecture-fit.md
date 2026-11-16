# Research assessment — Prefect 3 and Pydantic-native Copytrade-PM

**Date:** 2026-11-10  
**Status at research review:** **RESEARCH ONLY**; no new approval of Q15, Q16 was still OPEN; no code, dependencies, registry or services changed.
**Subsequent owner decision (2026-11-10):** Q16 approved in the [final design-closure ADR](../decisions/2026-11-10-source-wallet-health-k-recalibration-design-closure.md). Prefect remains a **conditional research-only tool**, not installed or authorized by the design approval.  
**Repository inspected:** isolated `copytrade-pm` worktree at `origin/main=6c07cc6d36099135881be27a072c426a52a24f24`. No Prefect dependency or Prefect service found in inspected source/units. Live implementation performance has **not** been tested.  
**Related approved ADR:** [Q10–Q15](../decisions/2026-11-09-source-wallet-health-k-recalibration-round3.md). The earlier approved Q15 is **conditional** Prefect adoption for research orchestration, not a mandate to install it.

## Verdict

**ADOPT CONDITIONALLY** for *scheduled research orchestration* over an auditable, immutable, point-in-time **evidence-assessment** contract. **DO NOT ADOPT** as a replacement for the official position-first collector, real first-known T+300 timers, SQLite source/PM03/04 journals, release approval, or Guardian. Keep deterministic wallet diagnosis and k optimization independent of Pydantic AI. No model is needed for routine flow attribution or policy checks.

The higher-level abstraction is **immutable evidence snapshot -> deterministic assessment -> nonauthoritative proposal -> independently governed release**. Prefect runs the graph; it never supplies the economic truth or execution permit. **Durability of a computation != durability of received evidence != uniqueness of a financial effect.**

## Verified distinctions from official documentation

| Feature | What is native | Implication |
| --- | --- | --- |
| `@flow` parameter validation | Prefect validates flow parameters using Pydantic by default (`validate_parameters=True`) | Own strict/frozen/versioned `BaseModel` remains the canonical domain contract; wrapper validation alone is not evidence authenticity. |
| Prefect 3 `@flow`/`@task` | Scheduling, retries, cache and workflow status; can execute deterministic Python | No `pydantic_ai` package needed for Polars monitoring, capital attribution or k proposals. |
| `pydantic_ai.durable_exec.prefect.PrefectDurability` | Official, co-maintained Pydantic AI integration; *inside `@flow` only*, model requests, tool calls, MCP calls become Prefect tasks | Applies **only to a real AI agent**, not to ordinary Pydantic Validation models. `PrefectAgent` wrapper is deprecated. |
| Cache replay | A completed result recorded under the matching key can replay on retry | A crash after an external side-effect but before task-result persistence can repeat the side effect; no exactly-once broker/registry/financial guarantees. |
| Source input identity | Pydantic AI cache keys omit some run IDs and timestamps; the standard flow-run scoped policy prevents cross-flow automatic reuse unless explicitly changed | Carry PIT as-of, input evidence SHA, scope, model/algorithm/policy version, and explicitly governed key in all economically significant batch tasks. |
| Rate and concurrency | Prefect supports global concurrency and rate limits | Guard external provider budgets in tasks; note that some concurrency contexts warn-and-continue when the limit is missing unless `strict=True`. |
| Self-host | Prefect server default DB is a separate SQLite file; multi-worker server mode requires PostgreSQL and Redis | Do not reuse PaperJournal. Start only when there is a workload case; expose API/UI privately, pin versions and have backup/rollback. |
| Python support | Prefect 3.9.2 released Nov 6, 2026 requires Python `>=3.11,<3.16` and lists Python 3.14 | Compatible at metadata level with Copytrade-PM `requires-python>=3.14`; dependency solving and actual functional tests remain **UNKNOWN**. |

Primary references, checked 2026-11-10:

- Pydantic AI durable execution: https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/
- Pydantic AI Prefect integration (capability, caching, retries and limitations): https://pydantic.dev/docs/ai/capabilities/durable_execution/prefect/
- Pydantic AI Temporal integration: https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/
- Prefect flow parameter validation: https://docs.prefect.io/v3/how-to-guides/workflows/write-and-run
- Prefect single-server/multi-worker self-hosting: https://github.com/PrefectHQ/prefect/blob/main/docs/v3/how-to-guides/self-hosted/server-cli.mdx
- Prefect global rate/concurrency guard (default fail-open warning for missing limit): https://github.com/PrefectHQ/prefect/blob/main/docs/v3/how-to-guides/workflows/global-concurrency-limits.mdx
- Prefect Python metadata 3.9.2: https://pypi.org/project/prefect/

The official Pydantic AI overview now lists more durable engines than the earlier four-engine page snapshot; this does not itself justify broadening Copytrade-PM's architecture.

## Repository fit

### Existing owners that must not move

- `src/copytrade_pm/pm_v4_selected_positions.py`: official deduplicated 14 selected-source subscriptions, original source receipt clocks and existing `PersistentAccount`/`PaperJournal` owner; receiver -> bounded serialized writer. Keep under existing systemd and recovery.
- `src/copytrade_pm/pm_forward_source_stream.py`, `pm_forward_journal.py`: account-local continuity/evidence, exclusive writer lease, SQLite SHA-linked commit; Prefect retries cannot repair these writer lock semantics.
- `src/copytrade_pm/pm_source_contracts.py`: already defines strict frozen versioned `SourceEvidenceRef`, `SelectedPerpScope`, `CanonicalPositionBook` and explicit Decimal conversion, with raw SHA independent of `model_dump`. Reuse, do not create another `WalletState`.
- `src/copytrade_pm/pm_research_contracts.py`: strict retrospective uncertainty and research classification, explicitly not trading authority.
- `src/copytrade_pm/wallet_registry_portfolios.py`: registry-owned versioned portfolio identity and seals.
- `src/copytrade_pm/pm_v4_sixteen_scenarios.py`: existing immutable/research-only k values and selection, not a mutable runtime k database.
- `experiments/pydantic_wallet_health/README.md`: the isolated Pydantic Evals pilot has synthetic labeled cases and no independently validated real-wallet edge-decay classifier. It does not imply a production agent is ready.
- PM03/PM04 paper accounting and independent `prop-production` Guardian own their financial states.

### Proposed future workflow graph (concept only)

```text
Existing SQLite registry + immutable source/market/flow evidence (read-only)
      |
      v
Pydantic: validate MonitorBatch(as_of, roster_sha, evidence_refs)
      |
      v
Prefect: schedule and bounded fan-out of wallet evidence refresh tasks
      |                  (read-only; provider rate/concurrency guards)
      v
Pydantic: validated evidence/provenance/UNKNOWN / attribution facts
      |
      +--> Polars/DuckDB PIT 7d / 30d / 90d follower-quality assessment
      |       |
      |       +--> immutable wallet health report -> existing Grafana projection
      |
      +--> deterministic PM03/PM04 k scenarios for selected portfolios
              |
              v
       strict Pydantic KRecalibrationProposal (hold/decrease/increase)
              |
              v
       EXISTING independent versioned portfolio release governance
              |
              +--> future-only SHADOW release ONLY with separate authorization
              +--> Guardian / live authorization NEVER inherited
```

**Prospective signed first-known source collection and T+300 are not Prefect tasks.** Their correctness and continuity are owned by original first receipt, durable source journal and PM03/04 policies.

### Two candidate `@flow` families (not implemented)

- `daily_wallet_health(as_of, roster_inventory_sha, evidence_policy_version)`: enumerate registered identities as-of; dedupe; bounded fetch; verify raw provenance / source coverage / all transfer categories; attribute capital flows; 7/30/90-day descriptive/edge evaluations; produce one immutable audit report. For insufficient provider coverage, output `UNKNOWN`, not a fabricated wallet loss.
- `periodic_portfolio_k_review(as_of, exact_portfolio_version, follower_journal_heads, market_evidence_sha, rulebook_version)`: read-only PIT follower net cost/drawdown evidence, reuse Polars/DuckDB + PM03/04 estimates; evaluate robust k candidates; persist deterministic immutable proposal ID only; no automatic active k update.

For batches of many wallets, use capped fan-out and explicit provider-per-minute policy; let each wallet fail independently in output, not collapse whole-day jobs without provenance. Retain exact original known-at and evidence hashes; manual reruns are safe under deterministic idempotency keys.

## Critical risks and boundaries

1. **Temporal/Prefect durability marketing is not financial transaction atomicity.** Prefect result caching cannot make a received Hyperliquid WS frame durably first-known, nor guarantee an external effect occurred only once. The existing journal remains the authority.
2. **PIT cache poisoning:** if a cache key only uses wallet ID, tomorrow's job can replay yesterday's assessment. Version and content-address every economic input. Be careful with Pydantic AI’s excluded run-time identifiers and un-serializable dependency objects.
3. **Retry multiplication:** SDK transport retries * Prefect task retries * higher-level flow retries can exceed vendor rate budgets. Choose one retry owner for each remote operation and bound API capacity; avoid four retries at each layer.
4. **Provider concurrency can be fail-open by default:** when using Prefect global concurrency, use strict lease enforcement for important provider budgets, plus local fail-closed caps; verify it with a real missing-limit/lease-failure test.
5. **Infrastructure crash is not automatic completion:** Prefect distinguishes ordinary FAILED/retry states from infrastructure CRASHED, which can be terminal. A worker loss or API outage may leave a run CRASHED or stranded. Configure and test explicit rescheduling/recovery and persisted results; don't promise that a destroyed worker will always resume the same run unaided. See https://github.com/PrefectHQ/prefect/blob/main/docs/v3/concepts/states.mdx and https://docs-customer-managed.prefect.io/reference/failure-behaviors/.
6. **Self-host complexity and security:** Prefect UI, API, persisted task inputs/outputs and Logfire can expose raw wallet evidence and provider credentials if used without redaction/permissions. Pass opaque wallet handles and SHA refs, not raw addresses or secrets in parameters and task logs. Keep API private; no public exposure without independent auth.
7. **Second SQLite operational burden:** Prefect server defaults to a separate SQLite DB, not the trading journal. Multi-server/multi-worker requires PostgreSQL and Redis. Avoid creating a second source of wallet metadata truth and avoid mixing service versions.
8. **Code and task-key evolution:** when `PrefectDurability` tool task names/definitions or code change, task-cache identity may change; a replay could repeat a tool. Keep external tools read-only and release governance independent of cached results.
9. **Agent hallucination / unsupported inference:** AI can help investigate ambiguous flows, but it is not needed for deterministic source financial attribution. Existing synthetic Evals cannot claim genuine accuracy or financial superiority.

## Deployment topology and experimental gates (NOT AUTHORIZED)

**Read-only pilot recommended before productionization:**

- A pinned, *separate* Prefect 3 environment on the VPS, compatible with Python 3.14. Core Copytrade-PM lockfile and running releases unchanged. Do not install now.
- Start with an isolated local flow, then an isolated one-server deployment only if daily/weekly automated schedules and retry dashboards justify it. The single server's local SQLite (if chosen for pilot) must be isolated and backed up, never sharing a path or mutex with source journal. Do not enable multi-worker server mode on SQLite.
- Prefer one process worker pool initially, bounded CPU/memory/time, no shared-private-source writes, no network access to broker/Guardian endpoints. Run only read-only source/registry acquisition and append-only proposal generation.
- Verification matrix: PIT backtest (future receipt must not appear), isolated wallet failure, worker/process termination and Prefect CRASHED recovery (including explicitly re-queued failed/crashed flows), crash before/after result persistence, idempotent proposal re-run, repeated as-of with changed evidence SHA, missing provider rate lease, huge registry fan-out, memory/cost benchmark, synthetic and independent real-wallet attribution outcomes, flow upgrade/in-flight retry.
- Measure how many daily/weekly flows, average time, task queue saturation and recoverable failures exist. Compare against a simple `systemd.timer` run before accepting Prefect's additional service lifecycle.

**Claim ceiling:** passing a Prefect smoke test means scheduled orchestration verified, not healed Hyperliquid source writer, causal financial qualification, or permission to trade.

## Explicit recommendation for Q16

Preserve Q15 **without expanding it**: Prefect 3 is a conditional `ADOPT` for research workflows only. Do not make Q16/source writer recovery contingent on installing it. Include a separate Prefect pilot/rollback acceptance alongside the wallet-health workstream. No agent runtime is required for initial launch; if actual Pydantic AI diagnostic agents are adopted later, evaluate `PrefectDurability` and its cache/side-effect limitations separately.

No design decision has been reopened or newly approved by this research report. Q16 remains the only current ready frontier.
