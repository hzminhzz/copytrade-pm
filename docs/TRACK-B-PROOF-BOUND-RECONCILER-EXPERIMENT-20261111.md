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

## Scale and reversibility

Existing `v4_source_export.export_signed_events` and `strategy_source_verify.verify_packet` still call **full** original-chain verification. Their use on active source journals is unsafe at current VPS disk/CPU pressure. The reconciler refuses source SQLite DB+WAL sizes exceeding **64 MiB** before invoking that existing full verifier. This cap is intentionally conservative and **not** a solution for large journals. No live 0811/0911 source or paper worker should be configured to invoke this module.

A later production-capable read model needs independently verified bounded incremental attestation anchored to an immutable fully audited checkpoint. `verify_stream_heads_fast` alone must not become the complete historical proof. Require checkpoint trust, cursor continuity, causal clocks, original hashes, WAL/reader resource and write-latency benchmarks, and recovery from archive/read-through before removing the 64 MiB guard.

The experiment has no systemd or Prefect integration, no Grafana release, no private/public Ed25519 publication signer, no external alerting and no automatic cleanup. Rollback is to **not invoke** it. Retain immutable experimental private receipts for audit; deletion requires an explicit retention decision.

## Next vertical slices (not implemented by this experiment)

1. Independently anchored incremental source and PM03 evidence verification on a bounded snapshot/cursor read model. Verify storage, WAL and CPU budgets first; address issue #292 separately.
2. Authentic independently selected registry, original market, fee/funding and PM03/04 evidence completeness, with explicit missing reason codes rather than optimistic finance labels.
3. Prefect adapter accepting only the reconciler's immutable manifest SHA and out-of-band source trust pin; preserve existing batch jobs and isolated research inputs.
4. Owner-controlled signed private-to-public publication and read-only Grafana rollout, independent ingress/v1 rollback tests and measured freshness.
5. Observed production metrics and scientific validation remain different acceptance tracks. No automatic k/Guardian/broker action.

## Engineering acceptance

The test file `tests/test_strategy_evidence_reconciler.py` uses original generated V4 signed-source journal fixtures to prove: deterministic first-known T+300, no financial promotion, exact idempotent replay, modified packet SHA rejection, forged-but-rehashed source proof rejection, manifest pin and selected-scope rejection, independent signer pin rejection, crash-after-publish recovery, tampered output refusal and large-original guard.

**Not verified:** actual 0911 live chain admission, real signed/source registry binding, independently comparable follower economics, Prefect orchestration of new manifests, live Grafana 200, real resource-budget improvements or scientific qualification. None may be inferred from unit tests.
