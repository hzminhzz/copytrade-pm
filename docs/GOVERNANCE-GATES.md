# Decision governance — review at state boundaries

**Decision:** 2026-11-04. Research-only; no trading, qualification or production authority.
Canonical agent invocation rule: [AGENTS.md](../AGENTS.md). Scientific acceptance
remains [QUALIFICATION.md](QUALIFICATION.md). Recovery follows
[BLOCKER-RECOVERY.md](BLOCKER-RECOVERY.md).

## Decision classes

| Class | Examples | Enforcement |
| --- | --- | --- |
| ROUTINE | Q&A, file/CSV searches, wallet discovery and preliminary screens, status checks, simulations, diagnostics, tests, lint, documentation, already-approved reversible work | Proceed without `judge` / `judge_batch`. No per-turn review, no artificial latency. |
| PROTECTED_WRITE | A real qualification registry mutation, permanent frozen-roster promotion/deletion, a material policy/risk contract change | Deterministic invariants and exact input lineage must pass. Owner authority remains separate. Invoke independent review at signoff or PR boundary where required. |
| HIGH_IMPACT_JUDGMENT | New scientific evaluation method, materially different selection thresholds or live-risk authority | Independent evidence-based review at an explicit decision boundary, not on exploratory discussion. A review cannot bypass science, controls or owner authority. |

An exploratory candidate list is **not** a frozen-roster promotion. A research
allocation proposal is **not** an authorized PM or an executable order.
Existing PM-02 campaign/report and Trader Intelligence readiness checks remain
deterministic. Do **not** substitute an arbitrary global `p_value`, `n_eff`
or drawdown threshold for their predeclared study-specific policies.

## Explicit signoff check (implemented)

`copytrade-pm-review-gate` / `python -m copytrade_pm.pm_governance`
checks a **separately supplied** Ed25519 reviewer attestation. It makes no
model, judge, web or broker calls and never changes a registry. The caller
must provide an immutable JSON evidence snapshot, a 64-hex policy SHA-256 and
the exact 40-hex source commit. These bind the review to the material being
evaluated. Review reuse is valid **only** if all bound inputs are identical.

The review JSON contains exactly:

```json
{
  "schema": "pm_governance_independent_review_v1",
  "operation": "MATERIAL_POLICY_CHANGE",
  "evidence_sha256": "<SHA256 of raw JSON evidence bytes>",
  "policy_sha256": "<64 lowercase hex>",
  "source_commit_sha": "<40 lowercase hex>",
  "verdict": "APPROVE",
  "reviewer": "<independent reviewer identity>",
  "reviewed_at": "<timezone-aware ISO-8601>",
  "rationale_sha256": "<64 lowercase hex>",
  "signature": "<128 lowercase hex Ed25519 signature>"
}
```

The reviewer signs canonical UTF-8 JSON of all fields **except** `signature`
(`sort_keys=True, separators=(',', ':'), allow_nan=False`). This is the
existing repository canonical-JSON convention. Store the original review,
rationale and evidence under owner-private versioned storage, not in Git.
The trusted Ed25519 public key **must** be anchored in independent operator
configuration. Passing a user-selected key to the CLI does not by itself
prove independent reviewer identity.

After an external PR review/signature has been recorded, run:

```bash
uv run --frozen --group dev copytrade-pm-review-gate \
  --operation MATERIAL_POLICY_CHANGE \
  --evidence /secure/frozen-policy-diff.json \
  --policy-sha256 <actual-64-character-policy-hash> \
  --source-commit-sha <actual-40-character-commit-sha> \
  --review /secure/review.json \
  --trusted-reviewer-public-key /secure/preconfigured-reviewer.pub
```

Possible protected actions: `MATERIAL_POLICY_CHANGE`,
`FROZEN_ROSTER_PROMOTION`, `PERMANENT_ROSTER_DELETION` and
`SCIENTIFIC_QUALIFICATION`.

- A successful **non-scientific** review check outputs
  `REVIEW_SIGNATURE_VERIFIED_NOT_AUTHORIZED`. It establishes only that the
  configured key signed the matching verdict. Owner authorization,
  scientific validation and any actual mutation are **not** performed.
- `SCIENTIFIC_QUALIFICATION` is **fail-closed** until an independently
  verified statistical/economic signoff producer and a protected
  qualification writer exist. The existing
  `trader_intelligence_qualification_cli` is read-only and reports
  `NOT_SCIENTIFICALLY_QUALIFIED`; even a signed optimistic review or an
  edited status cannot change that. `pm_manager` remains research-only.
- Missing review/trust root, stale evidence/policy/commit, negative verdict,
  bad signature, invalid clocks and unknown operations fail closed.
- An unavailable reviewer yields `JUDGE_UNAVAILABLE` **only for the
  affected protected decision**. Continue routine research and authorized
  reversible engineering. Do not fabricate, skip or silently replace review.
- Neither the CLI nor its reviewed input constitutes Propr approval, live
  order permission, qualification, an immutable registry writer or a
  production release.

## Current boundary and future automation

The repository does **not** have a `registry.db` writer or automatic
scientific-promotion command. Therefore no existing research command is
rewired to invoke an LLM, and no fake `pm-qualify` path is introduced.
Existing deterministic PIT/OOS, signed outcome and shadow-risk gates remain
unchanged. The new CLI supplies a reusable **review-verification seam** for
genuine protected workflows without changing their existing contracts.

An asynchronous reviewer may later be connected to a high-impact PR workflow
or signoff job. Before treating it as an enforced gate, provision an
independent key/trust root, protected PR branch rules and an owner-authorization
path; test stale review after commit changes, unavailable reviewer and
attempted bypass. None is provisioned by this research-only change.
Never invoke review from the market event loop, 300-second batching,
broker reconciliation or HALT controls.

## Verification

```bash
uv run --frozen --group dev python -m pytest -q tests/test_pm_governance.py
uv run --frozen --group dev copytrade-pm-review-gate --help
uv run --frozen --group dev python -m pytest -q tests
uv run --frozen --group dev ruff check src tests
```

Independent-review signatures in unit tests use synthetic private keys and
do not establish that an actual external reviewer or qualification producer
is deployed.
