# ADR — Prefect orchestrates Track B; immutable evidence owns recovery

**Date:** 2026-11-10
**Decision:** ADOPT Prefect 3.9.2 as an **optional research-only orchestration adapter**.
**Runtime promotion:** NOT APPROVED; no persistent Prefect server, schedule, worker, remote API, Grafana release or source/paper restart.

## Problem and higher-level model

Track B's original Pydantic contracts already own causal source validation, PM03/04 research attribution, 7/30/90-day windows, weekly provisional advisory, warning recovery, private immutable reports and redacted presentation. A global "workflow ready" boolean wrongly couples four independent lifecycles: (1) source/economic evidence, (2) deterministic assessment, (3) workflow execution, and (4) operational authority.

Model **an assessment run as a content-addressed transformation of externally pinned, already sealed evidence**. Prefect manages bounded concurrent attempts and transient retries; the original input/output SHA identities remain the durable truth. Failure or restart never rewrites a source T0, market quote, PM03/04 journal, SQL portfolio, k release, Guardian permit, or prior report.

## Chosen interface

A private, operator-owned 0600 JSON job manifest pins 1–16 original strategy-health report(s), optional original-backed causal window evidence, optional predeclared weekly look and expected input byte SHA256. A separate 0700 output directory receives at most one 0600 no-clobber report per **final report byte SHA256**. All paths are absolute. Prefect tasks accept only a manifest path, pinned manifest SHA and index, and return only a small sanitized receipt; raw wallet IDs, k, evidence, financial amount and private report bytes never become task result storage.

- **Pure domain modules:** `strategy_health`, `strategy_windows`, `strategy_advisory`, `strategy_incidents`, original source/PM03 readers. Pydantic 2.14.3 remains authoritative for schema.
- **Deep core module:** `strategy_health_jobs` owns pinned private input verification, deterministic evaluation, existing immutable report publishing and verified replay.
- **Optional adapter:** `strategy_health_prefect` maps independent jobs to bounded Prefect tasks, retries only transient I/O and returns sanitized receipts. Use `--extra prefect`; zero Prefect imports from source, PM03/04, Guardian, hot loops or Grafana.
- **Operational seam:** Private staging output is NOT the signed private-public publication binding and NOT the Grafana release. Owner publication, authentic finance, k activation and broker authorization remain separate gates.

A completed job can be rerun after process death: if identical output already exists, verify its *exact canonical bytes* and return `EXISTING_VERIFIED`; any tamper, wrong input SHA or output collision fails closed. This is resumability via original immutable artifacts, not a claim that local ephemeral Prefect automatically restarts a dead Python process. A future persistent deployment needs its own approved worker, bounded storage, private credentials, retention/GC, rollback and telemetry controls.

### Alternatives and leverage

| Shape | Change locality | Operational cost | Verdict |
| --- | --- | --- | --- |
| Existing Python jobs + systemd timers only | Retry/state policy repeated across each job | Low | Baseline/rollback |
| **Prefect 3 optional orchestration + original SHA receipts** | One adapter; domain modules unchanged; retries in Prefect, idempotency in one core interface | Moderate, opt-in | **ADOPT** |
| PydanticAI `PrefectDurability` | Agents would become another evaluation owner; Track B currently has no LLM agent loop | Unnecessary | NOT APPLICABLE |
| Temporal engine for these local research jobs | Requires worker/service and additional replay/command semantics | High | DEFER |

Prefect native tasks are used, not PydanticAI's agent capability. Prefect's durable caching alone does **not** guarantee exactly-once external effects or automatic restart. No source API acquisition, PM03/04 mutation, alert delivery, k release, trade execution or second financial ledger is a Prefect task.

## Failure/acceptance rules

- A missing, corrupt, stale, unsealed or non-0600 private report fails closed. No fabricated finance or shortcut to scientific qualification.
- The manifest and each input are byte-hash pinned. Missing optional market/finance evidence means zero authentic matches, not zero risk or a clean finance result.
- Already-known source opportunities, selected fixed k, signed lineage, weekly predeclarations, and `as_of` do not change when a task retries.
- Retry only `EAGAIN`, `EBUSY`, `ETIMEDOUT`, `EINTR` local transient I/O; structural errors never become success.
- All output has `read_only=true`, `trading_authorized=false`, `source_finance_authenticated=false`, `scientifically_qualified=false`. Prefect never claims real strategy alpha.
- Disable configured remote Prefect APIs, including API key/profile URLs, and disable Prefect server analytics during local runs. No sending owner-private data to Prefect Cloud.
- Default no persistent daemon/service, no schedule, no broker/Guardian/Grafana mutation.

## Promotion sequence

1. Verify optional dependency isolation, exact pinned results, 2-run idempotence, tamper rejection, post-publication crash replay, transient retry and 1–16 independent job isolation on synthetic fixtures.
2. Run an isolated private nonproduction manifest referencing independently verified original Track B evidence and compare outputs to the non-Prefect parity path (same SHA) without mutating originals.
3. Only after independently authorized operations design an isolated persistent worker/scheduler, private retention/metrics, WAL/storage budgets and rollback. Do not add one implicitly.
4. Independently evaluate authenticity, scientific alert calibration, Grafana rollout and Track C releases. A successful Prefect flow never upgrades any of these gates.

**Prior decisions preserved:** [2026-11-09 Pydantic ecosystem sequencing](2026-11-09-pydantic-native-sequencing-ecosystem.md) and [2026-11-10 merge vs promotion](2026-11-10-merge-vs-runtime-promotion.md).
