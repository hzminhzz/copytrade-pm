# WR-08 signed negative evidence import — research-only

**Scope (2026-11-04):** optional, operator-directed import of independently
*claimed* negative scientific review records. This is NOT an independent
qualification process, live trading authorization, or economic scoring model.
Positive verdicts are never supported by this interface.

## Authority boundaries

- The original PM-01 prospective receipt ledger, PM-02 whole-account
  `pm02_independent_matched_outcome_v2` evidence producer, risk policy and
  independent reviewer remain separate, higher-level authorities.
- A valid Ed25519 signature proves possession of a signing key, **not** that
  the reviewer is independent or has audited actual source equity, executed
  follower fills, capacity, costs and matched controls. `reviewer_role`
  is the reviewer's declaration, not a credential or attestation of
  independence. The registry always returns `scientifically_qualified=false`
  and `trading_authorized=false`.
- The operator supplies a private 0600 signed review envelope, 0600 source
  evidence file and a **separately provided** 32-byte Ed25519 raw public key
  from a trusted external reviewer. The registry never generates a signing
  key, loads a private key, signs an assessment, or trusts a key declared in
  the same signed review envelope.
- All three private inputs must be explicitly supplied. Nothing is scraped
  or silently generated from historical HyperX fills, vendor profit factor,
  synthetic test results, market quotes, Gemini portfolio proposals, or
  unrelated research reports.
- The whole envelope is accepted only when it has exactly
  `attestation` and `signature_hex`. Attestations must follow the strict
  `wallet_registry_independent_negative_v1` schema and contain:
  `decision_id`, canonical wallet address, policy version and SHA,
  source evidence SHA, verdict (one of `BLOCKED`, `UNQUALIFIED`,
  `NOT_ESTABLISHED`), `decision_at`, `reviewed_at`, reviewer identifier
  and claimed role, `scope=RESEARCH_ONLY`, both authorization booleans
  false. Duplicate JSON keys, nonprivate, linked, malformed, oversized,
  unsigned, mismatched, future-dated, unknown-wallet or unexpected fields
  are rejected.
- Import knowledge time is the **actual local import time**, never the
  source event time or an attestation's historical `decision_at`. This
  prevents backdating claims. Replays of identical source/proof are idempotent;
  conflicting revisions use new decision identities, not an overwrite.
- SQLite v6 adds `qualification_proofs` with SHA-pinned canonical payload,
  policy digest, reviewer-key fingerprint and Ed25519 signature. Evidence
  verification occurs again under the private registry writer lock before
  a single transaction. A trigger forbids editing or deleting the linked
  immutable negative decision/proof.
- The existing SQLite v5 positive-verdict rejection remains intact.
  Direct ad-hoc negative rows without a corresponding proof do not become
  independently signed. A valid cryptographic negative row **never**
  becomes a positive qualification or paper-run admission.

## Commands

Only after receiving a genuine independent review and its corroborating
off-Git sources from an actual reviewer:

```bash
# Check the local registry and available signature imports (no writes).
uv run --group dev copytrade-wallet-registry qualification

# Redacted preview. The reviewer has supplied real evidence/key files:
uv run --group dev copytrade-wallet-registry qualification \
  --attestation-file /private/reviewer/negative-attestation.json \
  --evidence-file /private/reviewer/source-evidence.bin \
  --auditor-public-key-file /private/reviewer/auditor-ed25519-raw.pub

# Optional owner-private negative indexing ONLY after review:
uv run --group dev copytrade-wallet-registry qualification \
  --attestation-file /private/reviewer/negative-attestation.json \
  --evidence-file /private/reviewer/source-evidence.bin \
  --auditor-public-key-file /private/reviewer/auditor-ed25519-raw.pub \
  --apply
```

All CLI output is redacted; it contains no wallet address, reviewer ID,
private file path or signature. Successful verification is
`SIGNATURE_CHECKED_NEGATIVE_ONLY`, not external auditor independence.

**Current owner-private source (2026-11-04):** no genuine signed
whole-account matched outcome and no independently verified positive
authorization are available to import. Synthetic Ed25519 fixtures exercise
the validation path only. Actual scientific qualification remains
NOT ESTABLISHED; trading authorization remains false. Do not fabricate
signed evidence to make the registry report populated.
