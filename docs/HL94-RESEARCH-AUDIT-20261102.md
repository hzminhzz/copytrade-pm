# Hyperliquid 94-wallet cohort: ingestion and audit checkpoint (2026-11-02)

## Evidence status

- **COMPLETED:** isolated read-only raw-fill ingestion audit, both vendor naming styles, trade-identity validation, SHA-addressed private per-wallet report.
- **NOT COMPLETED:** complete historical source position-book reconciliation, per-wallet authentic historical equity, Propr market-scope/native 1m coverage screen, 60/30 window selection, top-20 shortlist, PM03/PM04 three-pod portfolio experiments, validation, sensitivities or superiority claims.
- **RESEARCH DISPOSITION:** NO QUALIFIED PORTFOLIO. This is not a negative return finding. No candidate has been compared through the full follower engine in this cohort.
- **TRADING AUTHORIZATION:** NONE.

## Verified source audit

Raw cohort root: `/home/quant/dev/copytrade-pm/data`.

Versioned, immutable private report:
`/home/quant/.local/share/copytrade/reports/hl94-20261102/hl94-audit-84b1c1b344fa03c3df7f.json`

SHA-256: `84b1c1b344fa03c3df7f9bd7d9485f646f474601224c0361b63f6158a2fd752`.

- 19 original active roster JSON files, 20 Nansen JSON files, 55 broader inventory files.
- 94 files and **94 unique full wallet addresses** (no address-level overlap).
- **500,168 raw fill rows**; 37 invalid rows; **500,131 validated unique fill identities**.
- Invalid rows are quarantined, not used for source-account replay. Trade IDs at zero are not unique exchange evidence and are explicitly rejected, not silently deduplicated.
- Counts are for source-file contents, not first-known/real-time trades.
- Per-wallet report stores raw file SHA, label, instruments, observed chain breaks, gross reported turnover, aggregate reported closed PnL, and measured zero-to-zero holding times where a continuous book segment is observed.
- Closed PnL alone cannot proxy all-in wallet or follower profitability; source funding, collateral and unknown initial inventory remain unverified.
- One source's top-level `equity` value is a retrieval snapshot, not valid for historical position weights.
- No raw source file or original 36-wallet cohort was modified.

Reproduce:

```bash
uv run --frozen --group dev python -m copytrade_pm.pm_hl94_audit \
  --data-root /home/quant/dev/copytrade-pm/data \
  --out /home/quant/.local/share/copytrade/reports/hl94-20261102
```

## Blocker recovery path

The existing Q3 `pm_sparse_equity_portfolio` is **not** directly parameterized for this cohort. It is tied to the frozen 36-wallet alias roster, July–October window and nine source-equity files. Existing retrospective official portfolio NAV has sparse prior-only observations for the old nine wallets; that does not establish historical NAV or full books for the new 94.

Continue by acquiring separate source-account equity observations **without querying the official account-fill endpoint**, enforcing address/scope/as-of provenance and partial-book labels; extend cohort and dates in a new versioned engine configuration; then run the actual synchronized PM03/PM04 portfolio comparisons. Do not use today's snapshots or 90-day closed PnL as historical source equity. Do not interpret observed completed-position medians as whole-wallet holding-time estimates.

Do not select or deploy a wallet from this checkpoint. The `W042/W044/W028` Q3 baseline remains a separately evaluated, non-qualified historical proxy, not something this new cohort has beaten.
