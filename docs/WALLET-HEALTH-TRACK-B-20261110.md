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

## Official field capture and read-only rollout (2026-11-10)

The additional `copytrade_pm.wallet_health_official` reader queries the **current private SQLite as-of registry**, deduplicates the 283 eligible HL account identities observed in the first field canary, and uses only the already approved official Hyperliquid public `/info` HTTPS API. The current eligible count is not hardcoded; rerun the registry doctor. The collector does not subscribe new accounts to the official position WebSocket or connect a broker.

Each original response is stored byte-for-byte under a new `g...` owner-private, create-once generation alongside a timestamped, request-SHA- and response-SHA-bound receipt. A bounded rolling weighted rate reserve (default 240/min, maximum 600/min against the venue's documented shared-IP 1,200/min limit), one local process lock, three read-only retries and explicit provider-error abstention prevent unlimited acquisition. It cannot coordinate with unrelated processes using the same public IP; keep the reserve conservative. The default full-roster pass requests the selected *main perp DEX* state and independent account abstraction mode for every identity. Optional `--deep-wallets N` adds bounded 90-day original nonfunding ledger, funding and fills evidence to the first N accounts. The deep retrospective pages are **not** prospective first-known sources, nor are saturated historical pages complete.

```bash
uv run --frozen --group dev python -m copytrade_pm.wallet_health_official \
  --generation /home/quant/.local/share/copytrade/health-research/g20261110example000001 \
  --max-wallets 512 --deep-wallets 12 --weight-per-minute 240 \
  --publish-dir /home/quant/.local/share/copytrade-grafana-health
```

The generation path must be new and cannot be reused. The CLI reports sampled-account and provider coverage, original raw receipt counts, and missingness; it never prints private addresses or source balances. The `wallet_health` engine still abstains on absent or late follower episodes. This collector deliberately sets `source_continuity_verified=false`, `complete_pnl=false` and `complete_flows=false`: one REST state plus an historical ledger does not prove continuous observation, complete account-wide money flow or follower PnL. `default`/`disabled` source modes can verify a **main-perp account value only**; unified/portfolio-margin/dex-abstraction cannot promote per-DEX account value to a whole-wallet denominator. A main-perp capital observation is not authority for other HIP-3 DEX balances or unrelated subaccounts. No health report auto-excludes a wallet.

The redacted-only host directory is a separate publication boundary from the private raw generation. `wallet_health_projection` validates the immutable private report SHA and publishes only redacted statuses to this directory. Grafana's read-only publisher container mounts it as input and atomically copies a validated snapshot to the existing evidence volume; projection and Grafana have no registry/private wallet mounts, no source sockets, and no write interface. The producer bridges only one SHA-valid file and retains stale assessment clocks. A missing or corrupted source makes the viewer return 503 or preserves the last stale evidence, never a green signal. The operator can disable the read-only daily timer without deleting private captures, modifying other Grafana dashboards or touching Guardian.

The initial bounded live canary queried 4 real registered accounts and persisted 11 official public provider receipts without errors. Exactly one main-perp capital observation and one recent activity window were supported; **0 full economic attributions, 0 authenticated follower PnL observations, 0 real false-positive-rate qualifications**. This validates transport and conservative abstention on a small real sample, not yet all-wallet scientific performance. The full-roster result and actual installed-service SHA must be reverified against service/evidence records, not inferred from unit tests or this dated note.

## Boundaries and gaps

- No autonomous provider acquisition, retry or external quota coordination is implemented. Any provider response must first be captured into independently authenticated, timestamped evidence.
- No real-wallet diagnostic accuracy or false-positive rate is established by the synthetic test cases.
- No automatic exclusion, liquidation, trading activation, k adjustment or Guardian effect is allowed.
- No Prefect service, scheduled timer, Grafana installation or protected service deployment is included.
- Positive copyability and statistical edge-decay claims require an independently reviewed prospective follower evaluation, cost sensitivities, historical selection-trial accounting and out-of-sample controls.

**Track C interface:** `wallet_health_assessment_v1` contains per-wallet as-of eligibility, uncertainty, diagnostic windows and immutable evidence hashes. Track C may consume those *read-only* research fields, but must not interpret the report as a signed k release or trading authorization.
