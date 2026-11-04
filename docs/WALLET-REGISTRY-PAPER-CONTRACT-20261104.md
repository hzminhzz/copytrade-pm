# Wallet registry to paper-runtime boundary — engineering contract

**2026-11-04 status: implemented as an optional PRIVATE read-only observer and tested against synthetic fixtures only. No registered live P1/P14 paper worker was found at inspection.** This is not production activation, not a live/demo broker integration and not scientific qualification. FP-10 issue #67 remains a separate cross-program integration gate.

## WR-06 — versioned research portfolio selections

A registry source migration imports seven **SHA-sealed** decision declarations from reviewed Git document versions:

| Portfolio | Contract | Status |
| --- | --- | --- |
| P1 | S035-ENA / S051-BTC / S053-HYPE, virtual $10,000, combined nominal budget $600 | PAPER_RESEARCH_PRIMARY, **not running** |
| P14 | P1 trio + S064-xyz:BRENTOIL + Whale_0x5f94, virtual $10,000, **same** nominal $600 budget | PAPER_RESEARCH_CHALLENGER, **not running** |
| P16 | P1 trio + Whale_0x5f94, illustrative $600 total | OPTIONAL_CONTROL |
| A/B/C | Frozen historical three-wallet research configurations | HISTORICAL_RESEARCH_ONLY |
| Combo2 | W028, CA-008, W015, hypothetical $5,000 paper account | PAPER_RESEARCH_EXPERIMENT |

Selection source: the reviewed document's exact bytes SHA-256, immutable Git revision and a conservative observed Git commit date. Current changes to a selected source document fail closed until a new, approved version is pinned. The selection contract JSON is hashed canonically as `wallet_portfolio_definition_v1`. Source alias-to-address resolution is **different from** independently verified account-book and trader-identity proof; P1/P14 have unresolved source identities here and no trade authorization. A legacy unsealed v1 entry never provides a SHA for a paper run.

Query e.g.:

```bash
uv run --group dev copytrade-wallet-registry portfolio P1
uv run --group dev copytrade-wallet-registry portfolio P14 --asof 2026-11-02T00:00:00+00:00
```

Do **not** infer active workers from these selection records. Keep paper source wallets, current source equity, subaccount book and PM03 risk in their separate authorities.

## WR-07 — provisional consumer for FP-10

**Important live coordination note (2026-11-04): draft FP PR #73 already defines
`paper_run_manifest_v1` and `paper_run_status_v1` with DIFFERENT field
envelopes from this provisional registry projection. This is a KNOWN CONTRACT
MISMATCH, NOT A VALID SHARED v1:**

| Field / source | FP-01/FP-02 in draft PR #73 | Registry provisional reader in PR #57 |
| --- | --- | --- |
| Portfolio digest | `portfolio_sha` | `portfolio_definition_sha256` + `portfolio_version` |
| Policy/release | `policy_sha`, `release_sha`, `market_manifest_sha`, `selected_at`, `started_at` | Not yet shared as primary run attestation |
| Financial journal | Private WAL/FULL `paper-events.sqlite3` and `PaperJournal` | Presence-check of private `events.jsonl`; never opened for replay |
| Worker status | `worker_status=NOT_RUNNING`, `admission=BLOCKED`, no durable worker heartbeat yet | Requires worker PID/start ticks, worker/feed/quote heartbeat |
| Financial authority | PM03 Account + own `PaperJournal` | Registry **never** owns financial state |

**Decision:** do not invent live worker status, rename FP fields under PR #73,
write into the paper journal, or treat a matching schema label as validated
cross-program integration. A dedicated synthetic regression confirms that
FP-01/FP-02's NOT_RUNNING/BLOCKED prototype returns UNKNOWN/INVALID_SCHEMA
in the provisional registry adapter. FP-10 #67 must reconcile one exact
authoritative schema at the publisher/registry boundary when the independently
built forward-paper runtime reaches its integration gate; both projects remain
isolated until that review. The rest of this section specifies the current
**registry-only experimental projection**, not the agreed final FP-10 protocol.


A distinct paper worker must publish owner-private **0600**, bounded JSON files in a **0700** directory, with no symlinks:

- `manifest.json`, schema `paper_run_manifest_v1`: unique `run_id`, `portfolio_id`, `portfolio_version`, exact `portfolio_definition_sha256`, separate `account_id`, `journal_name="events.jsonl"`, `environment="PAPER"`, `order_route="NONE"`.
- `status.json`, schema `paper_run_status_v1`: exact matching run/portfolio SHA/account ID, `worker_state` (RUNNING/HALTED/DEGRADED/STOPPED), `worker_pid`, `worker_start_ticks` (Linux /proc process start token), UTC `heartbeat_at`, `transport_heartbeat_at`, `quote_heartbeat_at`, monotonic `journal_seq`, 64-digit `journal_head_sha256` (publisher-reported).
- `events.jsonl`: present as the publisher's owner-private **0600** journal path. This registry never opens, replays, truncates, mutates or claims to verify its economic events.

The adapter is **one-way and observational**. It compares the run manifest to the registry's sealed selection, enforces per-run/account identity, a stable worker process and fresh heartbeats (90s worker, 120s transport/quotes). A long-lived wallet holding period is not a lost transport heartbeat. An absent file, changed selection, no journal, PID reuse, malformed source, stale heartbeat or missing transport results in `UNKNOWN`, `STALE` or `DEGRADED` — never a silent `PAPER_RUNNING_OBSERVED`.

```bash
# No writer:
uv run --group dev copytrade-wallet-registry paper
uv run --group dev copytrade-wallet-registry paper --run-dir /owner-private/paper/run-id
# Explicitly index one already independently launched valid run.
# Writes ONLY to the private registry, never to the paper worker/journal.
uv run --group dev copytrade-wallet-registry paper --run-dir /owner-private/paper/run-id --apply
```

The `paper` list command re-checks files and PID state on **each read**, not just stored timestamps; results are bounded to 500 registered runs. Reports omit raw private paths and account/journal IDs, exposing only their SHA-256 fingerprints. Even a matching file and PID do **not** certify economic P&L, source-account completeness, legitimate data capture, scientific qualification, demo execution or trading authorization. An optional paper worker must be delivered and its schema contract tested separately by FP-09/FP-10 before this can be called production-integrated.

**No registered run** means `global_running_count=UNKNOWN`, not proof that all portfolios have stopped.

## Boundaries still open

- FP-10 (#67) must verify the actual independently built forward-paper publisher writes this exact schema, hashes the same definition and remains operational if the inventory is unavailable. There is no paper runtime or demo provider deployment from this change.
- WR-08 (#51) requires independently verified scientific attestation; no prospective matched outcome is imported, and `SCIENTIFICALLY_QUALIFIED` remains NOT_ESTABLISHED. SQLite v5 triggers now restrict research verdict writes to `UNQUALIFIED`, `BLOCKED` or `NOT_ESTABLISHED`, preventing any unreviewed positive/authorized promotion through this inventory. A verified signoff producer is still unavailable.
- WR-10/11 require full independent fault matrix, backup/restore and controlled activation signoff. A successful fixture/mock status is **engineering** evidence only.
- Any production order route is out of scope and rejected by this paper-only contract.
