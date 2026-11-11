# Track B independent source-audit anchor — 2026-11-11

**Status:** EXPERIMENT ENGINEERING APPROVED; NOT RUNTIME AUTHORIZED

## Decision

Use a **verified historical audit anchor with bounded causal suffix verification** instead of repeatedly running the complete source journal verifier as part of every Track B source export and assessment.

The anchor is an immutable, independently Ed25519-signed statement of the selected-account identity, exact original observer stream cursor/chain head, exact linked original source-receipt cursor/chain head and causal terminal timestamps after an initial full audit of a **consistent isolated backup**.

All future admissible observations after the anchor must form one bounded continuous suffix under an explicit read-only SQLite snapshot. Missing rows, hash mismatch, ordering regression, changed account identity, unsupported backlog, or mismatching source/stream head makes the requested operation fail closed. Successful fast startup-tail checks are not equivalent to a signed historical audit.

## Authority and keys

1. The official source producer owns historical source bytes and V4 producer-signing key. It cannot issue or approve independent audit anchors merely by creating signed packets.
2. A separately trusted auditor owns the audit signature key. The operator must independently pin the exact raw auditor public-key SHA **outside** the request/anchor. Anchors may be created only from separately verified, consistent, isolated original copies.
3. The source-reconciler owns no audit key. It verifies signed audit artifacts and existing source proofs and writes only content-addressed private research assessments and proof bindings.
4. PM03/PM04 own simulated research finance; Guardian independently owns protected finance and permits. No audit result is source-equity replication, actual executed follower economics, scientific qualification or trading authorization.

## Compatibility and failures

The existing V4 signed export v1 wire/signature and Track B assessment v1 contracts remain unchanged. The legacy exporter retains complete original verification. The opt-in verified-anchor exporter reuses original source-row reconstruction and produces identical signed V4 wire on fixture parity tests. The independent proof result uses the **distinct** strategy_source_verification_v2_anchored identity; it cannot masquerade as v1 full-chain verification.

Only explicitly verified anchors may bypass the 64-MiB offline-only full-scan guard. The suffix verifier enforces at most 256 consecutive stream events plus 256 consecutive source receipts per request. Larger backlog fails rather than skips or resets. A successor anchor requires an independently authorized auditor signing key and re-verification; historical anchors and reports are retained. Consumer cursors never become audit trust anchors.

There is no Prefect/Grafana schedule or deployment change. The real 0811/0911 journals have not been independently sealed. GitHub issue #292 remains a separate disk/WAL/recovery concern: do not run heavy initial audits on active gigabyte journals, checkpoint their WAL, perform unsafe backups or force source restarts.

## Rejected approaches

- Trust producer-signed packets or fast head preflight as complete prior-chain proof: circular/incomplete.
- Rehash full original history with every Track B assessment: unbounded and dangerous under 95% disk use.
- Store a mutable best-known cursor or backfill source first-known observations from retrospective fills: false prospective continuity.
- Make Prefect or Grafana original source or financial authority: breaks existing ownership and rollback contracts.

## Acceptance and unknowns

Fixture tests verify full-audited isolated backup initialization, incremental original stream/receipt chain and clocks, signed parent link, independent key trust, original signed packet wire parity, no full scan, bounded backlog, tamper, replay and immutable report binding. Record the current full core and market suite on the actual PR.

**UNKNOWN pending separate runtime work:** independently recoverable initial audited real backups and disk headroom for 0811/0911; read/IO/CPU/WAL limits under concurrent consumers; actual first-known coverage; matched follower market/fee/funding data; owner-approved signing/public Grafana release; trading authorization.
