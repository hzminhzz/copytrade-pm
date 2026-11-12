# Hyperliquid 94-wallet raw cohort: read-only integrity audit (2026-11-02)

**Status: IMPLEMENTED / ENGINEERING VERIFIED.** Historical partial-source replay now exists separately: [HL94 Gemini-inspired three-pod study](HL94-GEMINI-THREE-POD-20261102.md). This audit does not prove whole-wallet economic returns or first-known observations.

## Scope and immutable evidence

Private source root: `/home/quant/dev/copytrade-pm/data/`. Three independent directories contain 19 primary active roster, 20 Nansen Smart Money, and 55 broader active inventory JSON files. **94 files and 94 unique full wallet addresses**, deduplicated by address rather than label. Original frozen 36-wallet PM-01 cohort unchanged.

**Final read-only audit:** `/home/quant/.local/share/copytrade/reports/hl94-20261102/hl94-audit-fb280b2e1cab827116a9.json`.

**SHA-256:** `fb280b2e1cab827116a93c339aa925cad377b38145c1dcc77fcba4d618e3d9e5`.

| Audit dimension | Observed result |
| --- | ---: |
| Raw 90-day-designated fills (before actual date-window filtering) | 500,168 |
| Distinct valid native fill identities | 500,131 |
| Rejected invalid rows | 37 |
| Distinct wallet addresses | 94 |
| Source-file count by directory | 19 / 20 / 55 |

Both `startPosition`/`closedPnl` and `start_position`/`closed_pnl` are normalized. Native coin names, source timestamps, signed sizes, trade IDs, position-before/after, order IDs and raw SHA are retained. `tid=0` rows are invalid identity evidence, not safe deduplication keys. Source snapshot `equity` was **not used** as a historical as-of equity denominator.

**Audit correction:** A prior report `hl94-audit-84b1c1b344fa03c3df7f.json` reordered same-millisecond fills by exchange `tid`. That ID is not a chronological rank. The current version instead uses stable timestamp sort, preserving original vendor order within each timestamp. This changes measured chain discontinuities/episode holds but **not** the raw/valid fill counts. A dedicated regression test prevents the original sequencing bug. Preserve the original SHA report as superseded history; do not erase it.

Observed source realized PnL, completed-episode median holding times, and gross trade turnover are **descriptive**, not follower PnL, full source equity or complete book coverage. Zero-to-zero episodes cannot recover unknown opening inventory, omitted hedges, omitted subaccounts, funding or collateral.

## Reproduce

```bash
uv run --frozen --group dev python -m copytrade_pm.pm_hl94_audit \
  --data-root /home/quant/dev/copytrade-pm/data \
  --out /home/quant/.local/share/copytrade/reports/hl94-20261102
```

**Research decision (user, 2026-11-02):** Historical-equity recovery is *not required for exploratory wallet-selection experiments*. The successor study uses discovery-calibrated, fixed source-position scale factors and clearly labels them as proxies. This decision does **not** override the exact source-equity sizing contract for any claim of faithful replication or live authorization.

No raw source data, private address map or vendor credentials were committed to Git.
