# First-local HyperX receipts → PM-02 prospective evidence

**Contract:** `pm01_prospective_receipt_ledger_v1` (additive to immutable `pm01_fill_only_replay_v2`). This capability is **research-only** and records no broker action.

## Trust boundary

HyperX WS and REST workers create owner-private immutable source receipts with `schema=pm01_hyperx_first_local_receipt_v1`, source event clock, original producer `locally_received_at`, alias, SHA-256 wallet identity, exact source market, trade ID, and coverage/snapshot status. The ledger consumes their *already persisted files*. It never calls HyperX, changes the original receipts, or fabricates positions.

| Time | Meaning | Decision authority |
|---|---|---|
| `source_event_at` | Exchange/vendor event timestamp | **No** — not first-known |
| `locally_received_at` | Producer-recorded first local observation | Potentially; not independently attested |
| `first_known_at` | **Max(producer-local receipt clock, ledger-local first import clock)** | Conservative lower bound after independent clock audit only |
| `decision_at` | Frozen hypothetical follower decision, after receipt | Must precede outcome |
| `outcome_known_at` | Sealed outcome record availability, **not** source event time | Scoring only after maturity |
| `audited_at` | Independently signed evidence review | No retroactive change to the original clocks |

Every receipt is appended once with immutable SHA-chain predecessor, local `recorded_at`, original raw file SHA and account-cohort/market/TID identity. `events.jsonl` is 0600 in a 0700 owner-private directory; the ledger verifies all hashes and Ed25519 signatures whenever read. A flock serializes appenders. Replayed receipt timestamps or conflicting fill identities fail closed. Missing/truncated/tampered journal states do not silently auto-repair. The owner-private manifest pins exact 36 wallet address *digests*, source-cohort manifest SHA, and the **independent auditor's public key digest**. Private address mappings, HyperX raw pages, API credentials, or reviewer signing keys never enter Git or this journal.

### Evidence states

1. **RECEIPT:** WS or REST saved local observation. `verified_first_known=False` and no PM-02 episode; even a legitimate recent vendor fill does not establish follower execution or account economics. REST always `source_snapshot=True` and cannot be audited into a prospective WS signal. Recovered/stale WS snapshots similarly excluded.
2. **AUDIT:** An independent reviewer with a separate Ed25519 private key signs `pm01_independent_receipt_audit_v1`, binds immutable receipt record SHA, raw receipt SHA, first-known timestamp, independent clock-anchor SHA, named reviewer, reviewed feed continuity and `audited_at`. The ledger cryptographically verifies against the pinned public key and excludes stale/snapshot/future event claims. **An audit alone still creates no economic score.**
3. **OUTCOME:** Separately signed `pm02_independent_matched_outcome_v1`, binding receipt audit SHA + source event identity + recorded decision and outcome maturity, 5/15/60m horizon, independent source/market/follower execution evidence SHAs, matched control, signed exposure, net follower/control PnL in R, turnover and tail loss. Requires non-conflicting, finite, complete fields and outcome availability *after* decision plus horizon. All outcome numbers must be supplied by an independently verified follower-economics process; **this module never computes or guesses them.**
4. **PM-02 consumer:** `pm02_rows_asof()` produces the exact legacy fields expected by `pm_manager._prospective_evidence` **only** after chain, independent signature, maturity and as-of validation. The prospective `known_at` is the conservative ledger first-known bound; the `outcome_known_at` is the sealed local outcome record time. The PM-02 decision includes `audit_chain.prospective_ledger_head_sha256` from the **as-of prefix**, not events arriving afterward. No PM-01 historical replay schema/default SHA changed.

An externally signed declaration is **not itself proof** that the stated source coverage, actual follower fills, costs, matched control or independent clock anchor were empirically audited. The operator must use an independent reviewer and retain corroborating raw evidence off Git. The research ledger rejects unsigned/mismatched declarations but cannot force honest external measurements. Synthetic test signatures never qualify a live wallet. Current actual 36-wallet PM-02 evidence remains 0 qualified / 5 EMPTY / 0 actionable R.

## Offline CLI workflow

Python ≥3.14, package dependency `cryptography`. Use an **owner-private** research root with the exact original 6 + Wave1 10 + Wave2 20 cohort. The auditor public key must be an Ed25519 **raw 32-byte public key**; keep the private signing key outside this repository, CLI, broker, and VPS research user.

```sh
uv sync --frozen --group dev

# Initialize immutable cohort and auditor trust root (no vendor calls)
copytrade-pm-receipts init \
  --research-root /secure/research-root \
  --ledger /secure/prospective-ledger \
  --auditor-public-key /secure/independent-auditor.pub

# Import only producer's owner-private stored WS/REST receipts
copytrade-pm-receipts ingest \
  --research-root /secure/research-root \
  --ledger /secure/prospective-ledger \
  --auditor-public-key /secure/independent-auditor.pub \
  --receipts /secure/receipt-generation/first_local_receipts

# The separate reviewer first writes a private file:
# {"attestation": {...}, "signature_hex": "<detached Ed25519 signature>"}
copytrade-pm-receipts audit \
  --research-root /secure/research-root \
  --ledger /secure/prospective-ledger \
  --auditor-public-key /secure/independent-auditor.pub \
  --attestation-file /secure/signed-receipt-audit.json

# After separately verifiable, maturity-aligned follower/control economics:
copytrade-pm-receipts outcome \
  --research-root /secure/research-root \
  --ledger /secure/prospective-ledger \
  --auditor-public-key /secure/independent-auditor.pub \
  --attestation-file /secure/signed-matched-outcome.json

# Inspect counts and head without revealing wallet addresses or scores
copytrade-pm-receipts inspect \
  --research-root /secure/research-root \
  --ledger /secure/prospective-ledger \
  --auditor-public-key /secure/independent-auditor.pub \
  --asof 2026-11-01T00:00:00+00:00

# Read-only PM-02 ranking: SHA-pinned PM01 v2 input and sealed evidence
copytrade-pm-rank \
  --pm01 /secure/pm01-<SHA-prefix>.json \
  --asof 2026-11-01T00:00:00+00:00 \
  --out /secure/pm02-reports \
  --prospective-ledger /secure/prospective-ledger \
  --research-root /secure/research-root \
  --auditor-public-key /secure/independent-auditor.pub
```

`copytrade-pm-rank` without new flags remains **byte-compatible** with the original PM-02 historical-only default. For sealed mode, all three new CLI arguments are mandatory; the caller cannot input raw arbitrary prospective rows. Existing manifest and full journal must pass hash/signature validation, PM-01 aliases must exactly match ledger aliases, and as-of excludes future outcomes. A preexisting ledger is required; rank does not create evidence.

## Qualification boundaries

- Engineering: tests for WS/REST ingestion, independent signatures, invalid keys, stale/snapshot/quarantined source events, duplicated/conflicting receipts, malicious revisions, as-of, future signal, double-counting, missing costs/market, loss of journal data, thread contention, CLI, PM-02 consumer contract, and frozen PM01 v2 behavior.
- Scientific: real signed audit must be backed by actual independent clock witness and follower/matched-market evidence; validate true executable market-ID/venue, liquidity, fees, funding, source/account completeness, 5/15/60m decision-to-execution delays, PIT OOS and dependence statistics before rating managers. **These remain unverified.**
- Authorization: no orders or credentials, no fund account, no actionable R, no automatic promotion. Propr account-specific contract approval remains a separate prerequisite.
