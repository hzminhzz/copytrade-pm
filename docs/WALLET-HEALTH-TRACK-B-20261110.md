# Track B wallet health — research-only operator contract

Issue: #256. This is an isolated daily research report, **not** a trading, release, or registry mutation system.

## Owners and execution

The private SQLite wallet registry remains authoritative for as-of membership, aliases and historical exclusions. `wallet_health.registry_universe` uses a read-only SQLite transaction and a deduplicated registered-wallet query; it does not expand the selected 14-account official source stream. `wallet_health.assess` is independently executable and deterministic given fixed as-of, evidence and policy revision. It never queries provider endpoints or silently backfills information. Input acquisition remains independently budgeted and supplied by an authorized capture process. `provider_budget` caps the number of registry identities examined for external evidence; no network requests occur in this job.

Run from the repository (with UTC as-of and a **private** output directory):

```bash
uv run --frozen --group dev python -m copytrade_pm.wallet_health \
  --as-of 2026-11-09T18:00:00+00:00 \
  --out /home/quant/.local/share/copytrade/health-research
```

An optional private JSON input file may be supplied with `--evidence /private/capture.json`. Its schema is:

```json
{
  "schema": "wallet_health_input_v1",
  "synthetic": false,
  "financial": [],
  "episodes": []
}
```

Each financial or episode record includes the SQLite numeric `wallet_id`, the selected `account_scope`, as-of safe `observed_at` / `known_at` timestamps, a 64-hex source evidence hash, and the strict fields in the Pydantic `FinancialEvidence` or `FollowerEpisode` model. `synthetic: false` is an assertion by the supplying capture owner; it does not independently authenticate venue records. Capture provenance and provider transport readiness are separate acceptance gates.

A full registry report with zero observed financial evidence is a **coverage and abstention report**, not a demonstration of wallet health. Do not treat a retrospective episode as an authentic forward wallet position event. Costs must be included in genuine follower-net episode PnL, with explicit completeness flags. The report cannot independently measure slippage, source availability or portfolio marginal value. It makes no positive scientific qualification.

## Financial accounting

For the same selected account and UTC knowledge window:

`equity delta = deposits - withdrawals + realized PnL + unrealized PnL change - fees + funding + residual`.

An unknown funding term, partial flow coverage, missing account equity, unverified account-scoped capital, ambiguous account scope or stale receipt does **not** imply zero residual, zero capital, liquidation, source loss, or k invalidity. The separately declared `capital_verified` flag is required for eligibility and financial attribution; `source_continuity_verified` is a separate statement and does not follow from capital evidence. A current verified selected-account equity below $1,000 generates a research-only eligibility finding. It is **not** a whole-wallet NAV requirement for `FIXED_K_NATIVE_QUANTITY`.

7/30/90-day follower windows are *diagnostics*. Five distinct flat-to-flat, cost-complete, coverage-complete episodes across five distinct observed days are a minimum for a numeric diagnostic, **not statistical edge significance**. Available Polars is used for one-pass bulk aggregation; the minimal core also offers a numerically equivalent conservative Decimal fallback. Negative diagnostic PnL generates a **review recommendation only**. Portfolio marginal contribution remains UNKNOWN until matched risk-aware net follower tapes and controls exist. Recommendations do not modify registry, k, HALT, Guardian or inventory.

## Immutable report and Grafana

The report is a private create-once SHA-256-named JSON document with a strict frozen Pydantic v1 contract. Different as-of or evidence inputs produce different hashes. Reports are research artifacts, not signatures.

With explicit `--publish-dir /path/to/publisher-writable-evidence`, a separate redacted `wallet-health.json` snapshot is published through the existing atomic evidence publisher. The account-risk gateway's new fixed GET `/v1/wallet-health` route accepts the same bearer/host/body/query restrictions and opens only this fixed hash-checked projection from its read-only evidence mount. It never reads private financial journals or SQLite. The public projection contains only salted wallet pseudonyms, category status, count summaries, evidence count and age; it does not contain private wallet addresses, capital values, or financial journals. No running Grafana server or access rules are changed by this PR.

Published hashes prove integrity of local publication, not source authenticity. Stale assessments are explicitly downgraded. Do not display these rows as protected-account finance.

## Boundaries and gaps

- No autonomous provider acquisition, retry or external quota coordination is implemented. Any provider response must first be captured into independently authenticated, timestamped evidence.
- No real-wallet diagnostic accuracy or false-positive rate is established by the synthetic test cases.
- No automatic exclusion, liquidation, trading activation, k adjustment or Guardian effect is allowed.
- No Prefect service, scheduled timer, Grafana installation or protected service deployment is included.
- Positive copyability and statistical edge-decay claims require an independently reviewed prospective follower evaluation, cost sensitivities, historical selection-trial accounting and out-of-sample controls.

**Track C interface:** `wallet_health_assessment_v1` contains per-wallet as-of eligibility, uncertainty, diagnostic windows and immutable evidence hashes. Track C may consume those *read-only* research fields, but must not interpret the report as a signed k release or trading authorization.
