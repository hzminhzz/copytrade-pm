# Proof-bound Evidence Reconciler — isolated Track B experiment

**Decision:** EXPERIMENT. This is not installed, deployed, scheduled or authorized for trading. It does not repair issue #292, nor does it claim authentic follower-net economics or scientific qualification.

## Why this interface exists

Track B's existing Prefect adapter consumes **already sealed** assessments. Its original input generation, PM03 reconciliation, report production and Grafana publication remain separate responsibilities. This experiment tests a *single deep assembly seam* that accepts original source references, validates them through existing domain owners, and publishes a private immutable assessment. No second registry, financial ledger or workflow-state database is introduced.

### Existing authority

- `strategy_census.assess_verified_packet` and `strategy_source_verify.verify_packet`: original Ed25519 V4 source, first-known T0, source journal verification, missing intervals and frozen k.
- `strategy_selection.verify_selected_registry`: independently selected SQLite portfolio/seal when the operator supplies a registry.
- `strategy_finance.inspect_pm03_original`, `reconcile_source_attempts` and `summarize_pm03_economics`: read-only original PM03 reducer, simulated finance and source joins.
- `strategy_windows.with_windows` and `strategy_advisory.with_recovery`: existing 7/30/90-day windows and provisional recovery.
- `strategy_health.publish`: existing canonical SHA no-clobber private 0600 report.
- `strategy_health_prefect`: unchanged optional research-only dispatcher.
- `strategy_release_candidate`: unchanged independently signed offline private-to-redacted binding; **not invoked** by this experimental reconciler.
- `dashboard.evidence_plane` and Grafana: unchanged, no network publication by this experiment.

## Offline-only interface

```python
from copytrade_pm.strategy_evidence_reconciler import reconcile_manifest

receipt = reconcile_manifest(
    manifest_path,
    exact_manifest_file_sha256,
    trusted_source_public_key_sha256=independently_pinned_source_key_sha256,
)
```

Equivalent CLI:

```sh
uv run --frozen python -m copytrade_pm.strategy_evidence_reconciler \
  --manifest /operator-private/original/reconcile-request.json \
  --manifest-sha256 <exact-file-sha256> \
  --trusted-source-public-key-sha256 <independent-key-sha256>
```

Manifest contract: `track_b_evidence_reconcile_request_v1`, a strictly typed immutable 0600 file in an owner-owned 0700 directory. It pins `packet_path` and its exact original-byte SHA, a source public-key file and SHA, existing original V4 SQLite journal, one selected-account binding, original source cursor, `StrategyScope`, frozen `Campaign`, UTC as-of/created-at and existing private output directory named `track-b-prefect-staging`. Optional private registry and original PM03 root + original PM03 head SHA must be supplied together with their real authorities. The independent source public-key SHA is **also required as an out-of-manifest caller argument**; the manifest cannot establish its own trust anchor.

Output: `track_b_evidence_reconcile_receipt_v1` plus exactly one content-addressed no-clobber 0600 canonical private assessment. Replay returns `EXISTING_VERIFIED`; tampering fails closed. The receipt separates source availability, operational execution, follower economics, scientific qualification, private publication and trading authorization. No raw wallet identifiers, k or financial amounts appear in the receipt.

If registry seal is not independently supplied, source availability remains `INCOMPLETE_SCOPE`, regardless of successful original journal verification. If PM03 evidence is absent, economic comparability remains `UNKNOWN`. If PM03 is present, original modeled finance is derived using the PM03 reducer, but market/fees/funding independent completeness and scientific comparability remain `UNKNOWN`.

All rejected signed-source, journal, hash, cursor, scope, symlink and permissions evidence fails closed. An unverified selected account is never called fully verified. Missing material is not silently filled from historical Vike fills.

## Incremental source-proof engineering (added 2026-11-11)

The optional independently anchored path is now implemented, **not deployed or promoted**:

1. An independent auditor obtains a **consistent, isolated SQLite backup** of the original journal. With `offline_snapshot_confirmed=True`, `pm_forward_stream_anchor.full_audit_anchor` runs the existing full original stream/receipt audit on that small copy, validates the selected-account identity, source-receipt chain and causal clocks, and signs the exact stream and source-receipt cursor/hash heads with an externally provisioned **audit key independent of the producer signing key**. A WAL-bearing or larger-than-64-MiB initial audit file is refused. Never do this operation on an active 0811/0911 journal.
2. `publish_anchor` durably commits exact canonical Ed25519 bytes in the owner-private 0700 `source-audit-anchors` sidecar using SHA-addressing and atomic no-clobber publication; files are 0600. `load_anchor` requires the exact file SHA **and a separately pinned auditor public-key SHA**. A signed producer packet or local fast-tail preflight is not an independent audit anchor.
3. `verify_suffix` reads the actual original source journal in a single read-only SQLite snapshot, checks the exact sealed anchor row, verifies every contiguous stream event (including original v2 wire hash where applicable), linked original receipt, both hash-chain continuities, causal clocks, selected account, head, and absence of gaps in at most **256 stream events and 256 new source receipts**. It refuses backlog beyond either bound; no skipping and no full fallback. Both source and stream suffix must be independently verified.
4. `advance_anchor` requires the same independently provisioned auditor key, re-verifies the bounded suffix, and signs a new future anchor linked by the parent anchor's file SHA. The owner explicitly publishes and pins the successor. Nothing automatically rotates the trust key or promotes a candidate.
5. `v4_source_export.export_signed_events`, `strategy_source_verify.verify_packet`, and `strategy_census.assess_verified_packet` accept an **optional verified anchor**. The default full-chain legacy path is unchanged. The optional path uses the **same SQLite read transaction** to verify and export, then independently rechecks the verified head; a head that moves between reads fails closed. Its proof is `strategy_source_verification_v2_anchored`, not a substituted v1 historical audit hash. Existing V4 signed packet payloads and signatures are unchanged.
6. The strict reconcile manifest accepts four optional all-or-none private audit inputs (`original_audit_anchor_path`, `original_audit_anchor_sha256`, `audit_public_key_path`, `audit_public_key_sha256`) and requires a **separate out-of-manifest** `trusted_auditor_public_key_sha256`. Anchored runs bypass the 64-MiB full-scan guard, never run the full scanner, and durably emit both the canonical private report and `track_b_original_evidence_binding_v1` SHA-bound private reference (`*.proof.json`). The binding captures the signed source packet, independently signed audit, pinned request, report identities, and permanent NO TRADE status. It is **not** an independent signed public release.

Example read-only invocation with an already provisioned, signed and pinned anchor:

```sh
uv run --frozen python -m copytrade_pm.strategy_evidence_reconciler \\
  --manifest /owner-private/reconcile-request.json \\
  --manifest-sha256 EXACT_REQUEST_SHA \\
  --trusted-source-public-key-sha256 INDEPENDENT_SOURCE_KEY_SHA \\
  --trusted-auditor-public-key-sha256 INDEPENDENT_AUDITOR_KEY_SHA
```

The old full-history path still refuses journals larger than 64 MiB. This does **not** prove that original SQLite WAL and native v2 wire sidecar reads are efficient on the actual 0811/0911 deployments; the host remained heavily disk constrained. The code is **not enabled** on a live service, Prefect schedule, Grafana ingress, Guardian or broker.

## Next vertical slices (not implemented by this experiment)

1. Independently establish suitable 0811/0911 offline backups, owner-private audit signer/key policy and read-through retention before obtaining real anchors. Resolve issue #292 WAL/reader pressure and benchmark original snapshot verification and read latency without sacrificing write availability. No full audit against large active SQLite.
2. Bind independently selected registry, original market/fees/funding and PM03/04 completeness. Add explicit failure classifications and batch orchestration semantics; research-synthetic follower finance stays UNKNOWN for scientific comparability.
3. Optional local one-job Prefect adapter is implemented as `copytrade-pm-track-b-evidence-prefect`: exact immutable manifest and out-of-band auditor/source key pins; preflight rejects unanchored requests; idempotent original proof is reverified on task retry. The prior batch adapter stays unchanged; no persistent scheduling, remote API or live activation is approved.
4. Owner-controlled **independently signed** private-to-redacted release, with unchanged v1 wallet-health rollback and read-only Grafana canary/503 behavior; no publication without the real owner key and original proofs.
5. Independently observed acceptance for actual prospective economics, source freshness, rollback and capacity; science and trading authorization remain separate.

The experiment has no systemd activation, no scheduled Prefect, no Grafana release, no external alert delivery, no retention cleanup and no Guardian/trade route. Rollback means **do not invoke** the optional read-only functions; published experimental private receipts remain preserved until an explicitly approved retention operation.

## Engineering acceptance

The test file `tests/test_strategy_evidence_reconciler.py` uses original generated V4 signed-source journal fixtures to prove: deterministic first-known T+300, no financial promotion, exact idempotent replay, modified packet SHA rejection, forged-but-rehashed source proof rejection, manifest pin and selected-scope rejection, independent signer pin rejection, crash-after-publish recovery, tampered output refusal and large-original guard.

**Not verified:** actual 0911 live chain admission, real signed/source registry binding, independently comparable follower economics, Prefect orchestration of new manifests, live Grafana 200, real resource-budget improvements or scientific qualification. None may be inferred from unit tests.
