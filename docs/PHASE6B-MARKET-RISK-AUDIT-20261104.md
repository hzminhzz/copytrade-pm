# Phase 6B — independent market-price audit (2026-11-04)

**Historical v1 snapshot — superseded for further execution.** The source normalization and CLI changed in the independently versioned recovery generation. See [Phase 6B recovery, SHA-bound conditional S1–S8 experiments and final evidence](PHASE6B-RECOVERY-SCENARIOS-20261104.md). Preserve the frozen v1/v2/v3 SHA artifacts; the reproduction commands below describe the original version of the CLI and require the new `--phase4-source` argument on the current branch.

**Status: ENGINEERING VERIFIED preflight; historical follower economics BLOCKED; NOT SCIENTIFICALLY QUALIFIED.** This is research-only. No orders, subscription mutations, data download, or service changes.

## Frozen scope

- Phase 5 study: 2026-08-05 04:30 UTC to 2026-11-03 04:30 UTC (exclusive).
- Portfolios: A 100% / A active 150% (H21,N01,N07,N02,H17); B 100% / B active 160% (N01,N07,N02,N05,ACT08); three-pod C (H21,N01,N07), D (N01,N07,ACT08) equal-capital **diagnostic** controls, **not equal-risk** or Gemini optimized.
- Hypothetical follower initial equity $10,000. P0 account-only, P1 3%-aggregate pod budget, P2 account supervisor; S1–S8 retained only as **unexecuted, blocked scenario contracts**.
- Original Phase 5 PnL and tiny drawdowns remain *Gemini-reported*, not independently validated.

## Verified input evidence

Frozen Phase 5 member identities and weights were compared with its owner-private eligibility manifest. Six New-50 compressed source files match original roster SHA-256 and fill counts. The seven-wallet cohort additionally includes ACT08 from Phase 4: an existing immutable 5,475-row CSV has coin/side/size/price/time but no start_position or TID, so exact source position continuity cannot be reconstructed from that artifact.

The six New-50 source files contain 13,117 in-window fills across 92 distinct instrument labels. First observed positions for these instrument chains are nonzero, so preceding inventory cannot be treated as flat. This diagnostic does **not** establish whole-wallet continuity, full historical source collateral, funding, margin and equity, or first-known follower receipt times. N01 uses unified-account mode; ACT08 uses portfolio-margin. Do not substitute main-perp collateral for compatible account equity.

Exact-minute audit validated the native Hyperliquid Parquet file SHA against sidecar source.json, source identity, timestamp alignment/uniqueness and OHLCV consistency on all available days. Coverage is incomplete. Minute trade-derived close/open is a **valuation proxy**, never the official HL oracle/mark or a verified executable bid/ask.

Evidence retained owner-private under:

- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-coverage-v1/` — original SHA-addressed fill/market-day inventory and frozen assumptions.
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-minute-v2/native_minute_coverage.json` — 92 native instrument 1m audit reports with missing day/minute counts and source SHA.
- `/home/quant/.local/share/copytrade/reports/phase6b-20261104-blocked-scenarios-v3/` — explicit 180 BLOCKED_NOT_RUN scenario rows, and empty typed Parquet results with immutable manifest. **Empty Parquet is missing economic evidence, not zero risk.**

The minute audit recorded 5,111,432 verified instrument-minutes across 92 instruments out of 11,923,200 expected equal-window instrument-minutes; the latter denominator is **not** adjusted for listings/market inactivity. It found 4,755 missing market-day files, 56 partial days, and **zero identified SHA mismatch** among present files inspected. Aggregated across instruments, these are not account PnL and not exposure-weighted coverage; zero instruments provided 100% continuous minute availability over the entire window. See detailed JSON for per-coin explanations.

## What cannot be claimed

N07 0.03% trailing DD, A 1.02%/1.60%, B 0.46% are **UNKNOWN**, neither confirmed nor disproven. All first-passage challenge results, $10,000 follower net PnL, 3-vs-5 risk-normalized economics, P0/P1/P2 kill-switch outcomes and S1–S8 survival are **BLOCKED_NOT_RUN** for lack of source equity, complete position anchors/DEX scope and prospective execution evidence.

A hypothesis of a 5-minute follower is not an as-of causal execution proof: original vendor fill times are ex-post source events. Hypothetical risk rules do not establish actual challenge reset or trailing-floor semantics. The existing PM-03 and PM-04 account and risk modules remain the financial accounting authority; no replacement execution engine was built.

## Reproduce without network mutations

```bash
uv run --extra market --group dev python -m copytrade_pm.pm_phase6b --phase5 /home/quant/dev/copytrade-pm/data/private/gemini/phase5/phase5_portfolio_eligibility_20261104.json --new50 /home/quant/.local/share/copytrade/reports/five-pod-20261029-research/new50_hyperx_90d_full_vendor_v2 --market-root /home/quant/dev/quant/ml4t-data/.data/store --output /home/quant/.local/share/copytrade/reports/phase6b-20261104-coverage-v1
uv run --extra market --group dev python -m copytrade_pm.pm_phase6b_minute --coverage /home/quant/.local/share/copytrade/reports/phase6b-20261104-coverage-v1/source_coverage.json --market-root /home/quant/dev/quant/ml4t-data/.data/store --output /home/quant/.local/share/copytrade/reports/phase6b-20261104-minute-v2
uv run --extra market --group dev python -m copytrade_pm.pm_phase6b_blocked --coverage /home/quant/.local/share/copytrade/reports/phase6b-20261104-coverage-v1/source_coverage.json --exact-minute /home/quant/.local/share/copytrade/reports/phase6b-20261104-minute-v2/native_minute_coverage.json --output /home/quant/.local/share/copytrade/reports/phase6b-20261104-blocked-scenarios-v3
uv run --extra market --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
uv build
```

To extend this generation, first acquire **independent complete source account books with historical account-scope-compatible equity and funding**, and verify all market-mark/first-known availability. Preserve v1/v2/v3 and write a new immutable generation; do not silently rebuild an existing historical metric or promote Gemini's Phase 6A conclusions before reconciliation.
