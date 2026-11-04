# Milestone #2 — audited engineering acceptance, PR #92

**Date:** 2026-11-04 (UTC). **Scope:** one owner-approved
[Option A engineering/science separation](OFFLINE-MILESTONE2-ENGINEERING-ACCEPTANCE-20261104.md)
on [Milestone #2](https://github.com/hzminhzz/copytrade-pm/milestone/2).
Do not merge, deploy or activate this PR without separate authorization.

## Evidence ledger by engineering issue

| Ticket | Engineering verification | Concrete test / artifact |
| --- | --- | --- |
| #80 | Frozen SHA original PM-01 historical oracle benchmark, PM-01/PM-03 contract matrix; CPU, IO and RSS, host capacity; no fabricated speedup | `pm_offline_baseline`, `tests/test_pm_offline_baseline.py`, [baseline](OFFLINE-PIT-BASELINE-20261104.md) |
| #81 | Versioned, sealed manifest-to-report CLI, typed error, path and SHA validation, separate historical vs prospective clock, complete and partial semantics | `pm_offline_manifest`, `pm_offline_job`, `test_pm_offline_sweep_manifest.py`, `test_pm_offline_job.py` |
| #82 | Verified whole-account/DEX opening book and position chain, source-equity backward as-of/freshness, receipt identity, fail-closed missing data; original 36-wallet schema unchanged | `pm_offline_source`, `pm_offline_intents`, `pm_offline_receipts`, source/intents/receipts tests and frozen `test_pm_fill_replay.py` |
| #83 | All five strict event-specific 0/1/2/5/10m next-minute policies; causal whole-book last-state compaction and right-censor; canonical Polars streaming/in-memory SHA | `pm_offline_eligibility`, `pm_offline_intents`, eligibility/intents tests and real oracle tape SHA |
| #84 | SHA-verified exact native minute/DEX join, prior complete minute base volume only, no future/current volume, complete/partial/missing market status; optimized Polars same output SHA as reference | `pm_offline_market`, `pm_offline_oracle_market`, `test_pm_offline_sweep_market.py`, `test_pm_offline_oracle_market.py` |
| #85 | Independently sealed whole-book/equity, source delay, market panel and scenario cache invalidation; precise owner/DEX identity; separate SIGKILL resume and source read-only. Optional SHA-verified 7-day numeric private mmap hot cache shared across processes | `pm_offline_cache`, `pm_offline_derived_cache`, `pm_offline_hot_market`, `test_pm_offline_hot_market.py`, `test_pm_offline_sweep_pipeline.py` |
| #86 | One existing PM-03 Decimal Account; 3/5 pod whole-book sizing, gross-before-net, pod cap, funding/fees/slippage, cross, partial reductions and HALT across midnight; independently calculated two-pod ledger golden and PM-03 snapshot parity | `pm_offline_account`, `pm03_account`, `pm03_execution`, `test_pm_offline_sweep_account.py`, `test_pm03_allocator_rounding.py`, `test_pm03_adversarial.py` |
| #87 | Exact inclusive Decimal floors, day reset/target/breach, screen-only never financially authoritative, confirmed rulebook and explicit funding completeness; UNKNOWN/AMBIGUOUS for censored/unresolved paths; randomized sub-cent boundary checks | `pm_offline_certification`, `test_pm_offline_sweep_certification.py`, `test_pm_offline_sweep_account.py` |
| #88 | One sealed manifest launches independent 3-wallet/5-wallet, five-delay, multiple cost/shock scenarios; stable logical output across workers/input order/process restart; per-scenario typed BLOCKED and partial completion without zero-filling | `pm_offline_job`, `pm_offline_sweep`, `test_pm_offline_sweep_pipeline.py`, `test_pm_offline_job.py` |
| #89 | Runnable baseline and new benchmark CLI, comparable same-input stage parity, 10-run real 90d resource sample including empty app cache + warm, p50/p95/CPU/RSS/disk/IO and explicit scratch uncertainty; bounded hot-week profile | `pm_offline_baseline`, `pm_offline_benchmark`, `test_pm_offline_benchmark.py`, [read-only source benchmark](OFFLINE-PIT-REAL-ORACLE-20261104.md) |
| #90 | Reviewed source boundary, independently calculated PM-03 two-pod economic golden, original PM-01 and PM-03 regressions, no-order import audit, main/optional-market clean environments, GitHub Actions CI, build, Ruff, docs, non-merge release disposition | `test_pm_offline_no_order_boundary.py`, `test_pm_offline_sweep_account.py`, original PM01/PM03 tests, [RUNBOOK](RUNBOOK.md), [QUALIFICATION](QUALIFICATION.md), this record |

## Representative immutable inputs and exact measured boundaries

- 94 original private Hyperliquid JSON files, 500,168 raw fills; **450,172**
  eligible historical perp fills in 90 days; SHA source collection
  `1deefe08279936770e896f0521664cf0ee1976bc0eecec78d5c615cb8799117d`.
- Five-delay 377,130 historical oracle batch candidates, 322,970 native
  SHA-minute/previous-volume screened matches; remaining markets visibly
  `MISSING_NATIVE_DAY`, `PARTIAL_NATIVE_DAY` or `MISSING_COMPLETED_PRIOR_VOLUME`.
- Read-only real public-job report SHA
  `3141e4acb2df842025f880403d9dd4be2702c6811917bcb7949546dbdc6cbd1a`;
  `HISTORICAL_ORACLE`, **financial real=BLOCKED**, science=false,
  authorization=false and deployment=false.
- Same sealed real oracle job with a newly empty application cache:
  first 11.381831s, nine warm wall p50/p95 0.951180/1.042981s,
  CPU p50/p95 1.120042/1.338226s; 835,596 KiB RSS process high-water,
  15,751,252 cache bytes; source days untouched. The CPU and wall p95
  of all ten include the initial scan. No cold-OS-cache claim.
- Optional verified 7-day BTC read-only numeric hot panel:
  10,080 bars in 485,609 bytes, byte SHA
  `5a16af43ee151d6b5d9a44db04830443d9ed1c1e9104d41578ca4e9bc30f347f`;
  initial 0.260344s and cached mapping 0.002481/0.001780s.
- PM-03 independently calculated golden: two opposite source pods
  (+2 BTC and -1 BTC after k sizing), one internal cross, +1 BTC
  externally filled at $100, 10bps fee $0.10, $110 MTM, -$1.25
  funding => exact final cash $9,898.65, equity $10,008.65.
  This is a **synthetic** accounting identity, not follower performance.

## Remaining non-engineering / non-available evidence

`BLOCKED_REAL_WORKLOAD`: independently verified continuous historical
source NAV, native atomic whole-account opening and all-DEX scope,
first-local receipts, true as-of funding, executable depth/latency,
actual account terms and matched prospective follower/control outcomes
are absent. Historical vendor timestamps **cannot** be made PIT first-known
by a green build. Native Float64 OHLCV hot arrays are SCREEN_ONLY.
Whole 90-day PM-03 financial P&L and true performance comparisons are
therefore UNKNOWN, not assumed zero, PASS or alpha.

The original PM-01 36-wallet replay, read-only wallet registry, and
Forward-Paper independent **first-event T+300s** are separate contracts;
PR #73 remains a draft. PR #57 was closed unmerged and superseded by
mainline registry PRs; no source/registry/worker/order gateway was
modified or operated.

**Final close policy:** Use the actual successful HEAD CI commit and
per-issue tests when closing #80–#90 in dependency order. Close no
scientific qualification or account authorization claim. This document
does **not** authorize a PR merge or production deployment.
